# -*- coding: utf-8 -*-
"""Chwilowe "wypalanie": +10°C na nastawie pieca na 10 minut, potem sam
powrót do poprzedniej wartości - patrz `/boiler` ("Wypalanie"/"Anuluj").
Razem z nastawą, od razu na start, kopie też pompę pieca na tyle samo czasu -
patrz `_pump_on()` niżej po to, dlaczego to osobna, natychmiastowa komenda, a
nie poleganie na heating-controller.

Jedyna prawdziwa komenda sterująca, jaką ta aplikacja publikuje (reszta to
tylko wyliczony status, patrz `fuel_level.py` i README "Writing data") -
dlatego zawsze samo-odwracalna: stan (oryginalna nastawa + termin powrotu)
jest zapisany na dysku, a `watch_loop()` pilnuje terminu niezależnie od tego,
czy to ta sama sesja przeglądarki, czy nawet ten sam proces caveweb - restart
w trakcie wypalania nie zostawia pieca trwale podgrzanego.

Bezpieczeństwo: `check_and_correct()` w heating-controller/shadow_vault.py
resetuje nastawę do wartości domyślnej (nie: przycina), gdy wartość wykracza
poza [min, max] - stąd clamp do `max` tutaj jest konieczny, nie kosmetyczny,
inaczej "+10" poza zakresem cicho zresetowałoby piec do 60°C zamiast podnieść
go wyżej. Niezależnie od tego, `MAX_FURNACE_TEMP` (heating-controller) to
osobny, twardy limit bezpieczeństwa liczony od rzeczywistej temperatury, nie
od nastawy - wypalanie go nie omija.
"""

from __future__ import annotations
__version__ = "0.1"

import asyncio
import json
import logging
from datetime import datetime, timedelta

from . import config, heating_params, mqttclient, topics

LOG = logging.getLogger('caveweb.furnace_boost')

SETPOINT_NAME = 'furnace_temp_setpoint'
TOPIC = heating_params.PARAMS[SETPOINT_NAME]['topic']
BOOST_DELTA_C = 10
BOOST_DURATION_SECONDS = 600.0

# Pompa pieca: heating-controller (serwis "heating_service", priorytet 10,
# patrz jego config.py) ją też włącza, ale tylko reaktywnie - dopiero gdy
# piec faktycznie przekroczy zadaną+margines (PUMP_BOILER_CTRL w heating.py).
# Przy wypalaniu nie chcemy czekać, aż piec się rozgrzeje - pompa ma ruszyć
# OD RAZU, żeby ciepło zaczęło schodzić do bufora zanim jeszcze zrobi się
# gorąco. Priorytet wyższy niż heating-controller (10) gwarantuje, że to
# roszczenie wygrywa arbitraż gatewaya (leases.ChannelTable.resolve: wyższy
# priorytet wygrywa) na cały czas trwania, niezależnie od tego, co akurat
# robi własna logika progowa heating-controller.
PUMP_ALIAS = 'co_pump_boiler'
PUMP_SERVICE_NAME = 'caveweb'
PUMP_PRIORITY = 20
PUMP_TOPIC = topics.relay_cmd(PUMP_ALIAS, PUMP_SERVICE_NAME)


def _path():
    return config.FURNACE_BOOST_PATH


def load_state() -> dict | None:
    path = _path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def _save_state(state: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding='utf-8')


def _clear_state() -> None:
    path = _path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _publish(value: float) -> None:
    mqttclient.publish(TOPIC, json.dumps({'value': value}), qos=0, retain=True)


def _pump_on(duration: float) -> None:
    """Sprzętowy impuls na pompę pieca, wygasa sam - nie wymaga odnawiania
    ani jawnego wyłączenia (patrz moduł). qos=1, jak każda komenda przekaźnika
    w tej instalacji (cwu-controller, heating-controller) - w odróżnieniu od
    nastawy wyżej, zgubienie tej komendy nie jest samo-korygujące."""
    body = {'cmd': 'flash_on', 'duration': duration, 'priority': PUMP_PRIORITY}
    info = mqttclient.publish(PUMP_TOPIC, json.dumps(body), qos=1, retain=False)
    rc = getattr(info, 'rc', None)
    if rc not in (None, 0):
        LOG.warning('Wypalanie: kopnięcie pompy nieudane (rc=%s)', rc)
    else:
        LOG.info('Wypalanie: pompa pieca włączona na %.0fs (priorytet %d)', duration, PUMP_PRIORITY)


def start_boost(now: datetime | None = None) -> tuple[bool, str]:
    """Podnosi nastawę pieca o BOOST_DELTA_C na BOOST_DURATION_SECONDS.
    Odmawia, gdy wypalanie już trwa (żeby kliknięcie drugi raz nie dołożyło
    kolejnych +10 do już podniesionej wartości) albo gdy nie znamy jeszcze
    bieżącej nastawy z brokera (nie ma do czego potem wrócić)."""
    if load_state() is not None:
        return False, 'Wypalanie już aktywne.'

    current = mqttclient.cache.value(TOPIC)
    if current is None:
        return False, 'Brak aktualnej nastawy pieca z brokera - spróbuj ponownie za chwilę.'

    meta = heating_params.PARAMS[SETPOINT_NAME]
    boosted = min(current + BOOST_DELTA_C, meta['max'])
    now = now or datetime.now()
    expires_at = now + timedelta(seconds=BOOST_DURATION_SECONDS)

    _save_state({
        'original_value': current,
        'boosted_value': boosted,
        'expires_at': expires_at.isoformat(),
    })
    _publish(boosted)
    _pump_on(BOOST_DURATION_SECONDS)

    minutes = int(BOOST_DURATION_SECONDS // 60)
    note = '' if boosted == current + BOOST_DELTA_C else f' (ograniczone do maks. {meta["max"]}°C)'
    LOG.info('Wypalanie: %s°C -> %s°C na %d min%s', current, boosted, minutes, note)
    return True, f'Wypalanie: {boosted:.0f}°C przez {minutes} min{note}, pompa włączona'


def cancel_boost() -> tuple[bool, str]:
    """Natychmiastowy, ręczny powrót do poprzedniej nastawy."""
    state = load_state()
    if state is None:
        return False, 'Wypalanie nie jest aktywne.'
    _publish(state['original_value'])
    _clear_state()
    LOG.info('Wypalanie anulowane ręcznie - powrót do %s°C', state['original_value'])
    return True, f'Anulowano - powrót do {state["original_value"]:.0f}°C'


def check_expired(now: datetime | None = None) -> bool:
    """Woła `watch_loop()` okresowo - jeśli termin minął, wraca do poprzedniej
    nastawy i czyści stan. Działa tak samo zaraz po starcie caveweb, gdyby
    termin minął, kiedy usługa była akurat zatrzymana. Zwraca, czy coś zrobił
    (do testów)."""
    state = load_state()
    if state is None:
        return False
    now = now or datetime.now()
    if now < datetime.fromisoformat(state['expires_at']):
        return False
    _publish(state['original_value'])
    _clear_state()
    LOG.info('Wypalanie: czas minął - powrót do %s°C', state['original_value'])
    return True


async def watch_loop(interval: float = 15.0, startup_delay: float = 5.0) -> None:
    """Startuje z tym samym opóźnieniem co `fuel_level.publish_loop()` - z tego
    samego powodu: nie trafiać na MQTT_ERR_NO_CONN, zanim `connect_async()`
    skończy łączyć się z brokerem."""
    await asyncio.sleep(startup_delay)
    while True:
        try:
            check_expired()
        except Exception:
            LOG.exception('Błąd przy sprawdzaniu wypalania')
        await asyncio.sleep(interval)
