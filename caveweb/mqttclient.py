# -*- coding: utf-8 -*-
"""Klient MQTT trzymający ostatnią wartość każdego topiku.

Aplikacja tylko słucha - nie publikuje niczego, więc nie może wpłynąć na pracę
kotła, falownika ani przekaźników. Wartości lądują w pamięci procesu (`cache`),
a strony odczytują je w swoich timerach: paho biegnie własnym wątkiem, my tylko
podmieniamy krotki w słowniku pod zamkiem.

Payloady w cave to JSON publikowany zwykle z retain=True, więc po podłączeniu
broker od razu dosyła stan bieżący. Interesujące pole zależy od publishera:
czujniki i falownik dają `{"value": ...}`, brama przekaźników `{"state": ...}`
oraz `{"today_s": ..., "total_s": ...}`. Dlatego cache trzyma sparsowany payload
w całości, a wybór pola zostaje po stronie strony (patrz live.Value.key).
"""

from __future__ import annotations
__version__ = "0.1"

import json
import logging
import threading
import time

LOG = logging.getLogger('caveweb.mqtt')

# Po tym czasie bez nowej wiadomości wartość uznajemy za nieaktualną
STALE_SECONDS = 300.0


class Cache:
    """Ostatnia wartość i czas jej przyjścia, per topic."""

    def __init__(self) -> None:
        self._values = {}
        self._lock = threading.Lock()
        self.connected = False
        self.messages = 0
        self.connects = 0
        self.disconnects = 0
        self.last_error = None

    def put(self, topic: str, value, when: float | None = None) -> None:
        with self._lock:
            self._values[topic] = (value, when if when is not None else time.time())
            self.messages += 1

    def get(self, topic: str):
        """(wartość, znacznik czasu) albo None, jeśli topic jeszcze nie przyszedł."""
        with self._lock:
            return self._values.get(topic)

    def value(self, topic: str, key: str = 'value'):
        entry = self.get(topic)
        return None if entry is None else extract(entry[0], key)

    def age(self, topic: str, now: float | None = None):
        """Wiek wartości w sekundach albo None, gdy nic nie mamy."""
        entry = self.get(topic)
        if entry is None:
            return None
        return (now if now is not None else time.time()) - entry[1]

    def is_stale(self, topic: str, limit: float = STALE_SECONDS,
                 now: float | None = None) -> bool:
        age = self.age(topic, now)
        return age is None or age > limit

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._values)

    def clear(self) -> None:
        with self._lock:
            self._values.clear()


cache = Cache()


def parse_payload(payload):
    """Parsuje payload MQTT do obiektu Pythona (dict, liczba, bool, tekst).

    Standardem w cave jest JSON, ale przyjmujemy też goły tekst z liczbą -
    dzięki temu nowy publisher nie wywala interfejsu. Pusty payload daje None,
    czyli "brak danych".
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = payload.decode('utf-8', 'replace')
    if not isinstance(payload, str):
        return None
    payload = payload.strip()
    if not payload:
        return None

    try:
        return json.loads(payload)
    except ValueError:
        try:
            return float(payload)
        except ValueError:
            return payload


def extract(data, key: str = 'value'):
    """Wyciąga pole z payloadu; payload nie-słownikowy zwracamy bez zmian."""
    value = data.get(key) if isinstance(data, dict) else data
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    return None


def _on_connect(client, userdata, flags, rc, properties=None):
    topics = userdata['topics']
    cache.connected = True
    cache.connects += 1
    for topic in topics:
        client.subscribe(topic)
    LOG.info('Połączony z brokerem (#%d), subskrypcje: %s',
             cache.connects, ', '.join(topics))


def _on_disconnect(client, userdata, disconnect_flags, reason_code, properties=None):
    cache.connected = False
    cache.disconnects += 1
    LOG.warning('Rozłączony (#%d) rc=%s', cache.disconnects, reason_code)


def _on_message(client, userdata, message, properties=None):
    data = parse_payload(message.payload)
    if data is None:
        LOG.debug('Pomijam pusty payload na %s: %r', message.topic, message.payload)
        return
    cache.put(message.topic, data)


def start(host='127.0.0.1', port=1883, client_id='caveweb', topics=('cave/#',),
          keepalive=60, username=None, password=None):
    """Startuje klienta w tle. Zwraca obiekt klienta albo None, gdy brak paho.

    Import paho jest leniwy, żeby testy logiki działały bez tej biblioteki.
    Łączymy się przez connect_async: gdy broker jeszcze nie wstał (typowe przy
    starcie Pi), paho będzie próbować dalej, a aplikacja i tak się podniesie.
    """
    try:
        import paho.mqtt.client as mqtt
    except ImportError as error:
        cache.last_error = f'brak paho-mqtt: {error}'
        LOG.warning('paho-mqtt nie jest zainstalowane - brak wartości bieżących')
        return None

    topics = tuple(topics)
    client = mqtt.Client(
        client_id=client_id,
        protocol=mqtt.MQTTv311,
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata={'topics': topics},
    )
    if username:
        client.username_pw_set(username, password)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)

    try:
        client.connect_async(host, port, keepalive)
        client.loop_start()
    except Exception as error:  # noqa: BLE001 - brak brokera nie może wywalić UI
        cache.last_error = str(error)
        LOG.warning('Nie udało się wystartować klienta MQTT: %s', error)
        return None

    LOG.info('Klient MQTT wystartował: %s:%s jako %s', host, port, client_id)
    return client


def status_text(now: float | None = None) -> str:
    """Krótki opis stanu połączenia do stopki/nagłówka strony."""
    if cache.last_error and not cache.connected:
        return f'MQTT: {cache.last_error}'
    if cache.connected:
        return f'MQTT: połączony · {cache.messages} wiadomości'
    if cache.connects:
        return f'MQTT: rozłączony (było {cache.connects} połączeń)'
    return 'MQTT: łączenie...'
