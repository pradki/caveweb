# -*- coding: utf-8 -*-
"""Odkrywanie modułów/kanałów przekaźników i ręczne komendy z `/relays` -
wszystko czytane z już płynącego MQTT (caveweb subskrybuje `cave/#`), bez
hardkodowania listy modułów, aliasów czy liczby kanałów: gateway publikuje
retained status każdego kanału (alias/numer, state, by, priorytet, termin
wygaśnięcia leasingu) i bitmaskę modułu (z liczbą kanałów) zaraz po starcie -
to wystarczy do zbudowania tabeli i znajdzie też kolejne moduły, gdy ktoś je
doda, bez zmiany kodu.

Jedyna rzecz, jakiej nie da się tak wyczytać: kanał, który nigdy nie dostał
ŻADNEGO statusu (np. zaraz po pierwszym starcie gatewaya, zanim zdążył
opublikować) - taki wiersz pokazuje się jako "brak danych", nie zgadujemy
stanu.

`send_command()` publikuje dokładnie ten sam schemat komendy, co każdy inny
serwis tej instalacji (`{"cmd", "priority", "duration"|"ttl"}` - patrz
heating-controller/relay_client.py albo cwu-controller/relay_client.py), więc
gateway traktuje ręczną akcję z tej strony tak samo jak komendę usługi.
"""

from __future__ import annotations
__version__ = "0.1"

import json
import logging

from . import mqttclient, topics

LOG = logging.getLogger('caveweb.relays')

SERVICE_NAME = 'caveweb'
CMDS = ('on', 'off', 'flash_on')
# Wyraźnie wyżej niż priorytet, jakiego używają heating-controller i
# cwu-controller (10 u obu) - ręczna akcja z tej strony ma domyślnie wygrywać
# arbitraż gatewaya, a nie przegrać po cichu z automatyką.
DEFAULT_PRIORITY = 50
DEFAULT_DURATION = 60.0  # s - domyślny czas dla ręcznej akcji (impuls albo TTL)


def discover_modules() -> list[str]:
    """Moduły, dla których widzieliśmy bitmaskę statusu
    (`cave/relay/<module>/status`, 4 segmenty - nie mylić z per-kanałowym
    `cave/relay/<module>/<alias>/status`, 5 segmentów)."""
    modules = set()
    for topic in mqttclient.cache.snapshot():
        parts = topic.split('/')
        if len(parts) == 4 and parts[0] == 'cave' and parts[1] == 'relay' and parts[3] == 'status':
            modules.add(parts[2])
    return sorted(modules)


def channel_count(module: str) -> int | None:
    value = mqttclient.cache.value(f'cave/relay/{module}/status', 'channels')
    return int(value) if value is not None else None


def discover_channel_names(module: str) -> dict[int, str]:
    """{numer_kanału: alias_albo_chN} - z payloadów retained per-kanał."""
    names = {}
    prefix = f'cave/relay/{module}/'
    for topic, entry in mqttclient.cache.snapshot().items():
        if not topic.startswith(prefix) or not topic.endswith('/status'):
            continue
        parts = topic.split('/')
        if len(parts) != 5:
            continue
        payload = entry[0]
        channel = payload.get('channel') if isinstance(payload, dict) else None
        if channel is not None:
            names[int(channel)] = parts[3]
    return names


def channel_rows(module: str) -> list[dict]:
    """Jeden wiersz na kanał 1..channel_count - pusta lista, gdy nie znamy
    jeszcze liczby kanałów tego modułu (bitmaska jeszcze nie przyszła)."""
    count = channel_count(module)
    if count is None:
        return []
    names = discover_channel_names(module)
    rows = []
    for ch in range(1, count + 1):
        name = names.get(ch, f'ch{ch}')
        entry = mqttclient.cache.get(f'cave/relay/{module}/{name}/status')
        payload = entry[0] if entry and isinstance(entry[0], dict) else {}
        rows.append({
            'channel': ch,
            'name': name,
            'state': payload.get('state'),
            'by': payload.get('by'),
            'priority': payload.get('priority'),
            # Epoch (time.time()), nie monotonic - gateway już przelicza
            # lease.expires_at (monotonic) na czas ścienny przed publikacją,
            # patrz reconciler.py:_publish_status - więc porównanie z
            # time.time() tutaj jest wprost poprawne, bez własnej konwersji.
            'expires_at': payload.get('expires_at'),
        })
    return rows


def send_command(module: str, name: str, cmd: str, priority: int,
                 duration: float | None = None, ttl: float | None = None) -> tuple[bool, str]:
    """Ręczna komenda na `cave/relay/<module>/<name>/cmd/caveweb`. `duration`
    dla `flash_on` (sprzętowy impuls, wymagany przez gateway - bez niego
    komenda jest po cichu ignorowana); `ttl` dla `on`/`off` (jak długo
    trzymać, zanim trzeba odnowić - bez podania gateway i tak przyjmuje
    własny domyślny TTL, ale tu zawsze wysyłamy jawną wartość)."""
    if cmd not in CMDS:
        return False, f'Nieznana komenda: {cmd}'

    body = {'cmd': cmd, 'priority': priority}
    if cmd == 'flash_on':
        body['duration'] = DEFAULT_DURATION if duration is None else duration
    else:
        body['ttl'] = DEFAULT_DURATION if ttl is None else ttl

    topic = topics.relay_cmd(name, SERVICE_NAME, module=module)
    info = mqttclient.publish(topic, json.dumps(body), qos=1, retain=False)
    rc = getattr(info, 'rc', None)
    if rc not in (None, 0):
        LOG.warning('Ręczna komenda nieudana (rc=%s): %s %s', rc, topic, body)
        return False, f'Publikacja nieudana (rc={rc}).'
    LOG.info('Ręczna komenda %s/%s <- %s', module, name, body)
    return True, f'Wysłano: {cmd} (priorytet {priority})'
