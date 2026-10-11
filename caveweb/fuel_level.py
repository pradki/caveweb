# -*- coding: utf-8 -*-
"""Szacunek poziomu paliwa w zasobniku, publikowany co godzinę na
`cave/heating/fuel_level` (retained) - patrz `refuels.py` dla modelu danych
i README "Writing data" dla uzasadnienia, dlaczego to inny rodzaj zapisu niż
nastawy kotła (to ogłoszenie wyliczonego statusu, nie komenda sterująca).

Model: pełne tankowanie resetuje poziom do pojemności zbiornika; częściowe
dokłada swoją ilość do tego, co zostało. Między dwoma zdarzeniami (i od
ostatniego do teraz) odejmujemy zużycie: sekundy pracy podajnika od
`feeder_total_s` poprzedniego zdarzenia, podzielone przez współczynnik worka,
który się wtedy akurat wypalał (patrz `refuels.coefficient_for`).

Payload niesie też dobowe zużycie (`today_coal_kg`/`today_energy_kwh`), liczone
z pola `today_s` licznika podajnika (ten sam współczynnik, reset o północy po
stronie bramki) i orientacyjnej wartości opałowej węgla (`ENERGY_MJ_PER_KG`) -
w kWh, bo to łatwiej porównać z resztą instalacji niż kg. Do tego
`projected_daily_kwh` - to samo zużycie wyciągnięte liniowo na całą dobę wg
pory dnia (np. 15 kWh do południa -> ~30 kWh/24h), czyli odpowiedź na pytanie
"ile węgla pójdzie dzisiaj w sumie", a nie tylko "ile poszło do tej pory".
"""

from __future__ import annotations
__version__ = "0.1"

import asyncio
import json
import logging
from datetime import datetime

from . import mqttclient, refuels, topics

LOG = logging.getLogger('caveweb.fuel_level')

TOPIC = 'cave/heating/fuel_level'
TANK_CAPACITY_KG = 200.0
PUBLISH_INTERVAL_SECONDS = 3600.0
FEEDER_COUNTERS_TOPIC = topics.relay_counters('co_feeder')

# Węgiel ~27 MJ/kg (wartość orientacyjna, nie zależy od worka) - tyle
# wystarczy, żeby dobowe zużycie pokazać w kWh zamiast samych kg.
ENERGY_MJ_PER_KG = 27.0
MJ_PER_KWH = 3.6


def _burn(level: float | None, baseline_s: float | None, bag_size_kg: int | None,
         target_s: float | None) -> float | None:
    """Poziom po odjęciu zużycia między `baseline_s` a `target_s`, wg
    współczynnika `bag_size_kg`. Brak któregokolwiek z wejść - bez zmian,
    zamiast zgadywać."""
    if level is None or baseline_s is None or target_s is None:
        return level
    elapsed = max(0.0, target_s - baseline_s)
    coef = refuels.coefficient_for(bag_size_kg) if bag_size_kg is not None else None
    if not coef:
        return level
    return max(0.0, level - elapsed / coef)


def _daily_coal(bag_size_kg: int | None, today_s: float | None) -> tuple[float | None, float | None]:
    """Węgiel spalony dzisiaj (kg, kWh) z `today_s` podajnika i współczynnika
    worka, który akurat się pali - `None, None`, gdy brak któregoś wejścia."""
    if today_s is None or bag_size_kg is None:
        return None, None
    coef = refuels.coefficient_for(bag_size_kg)
    if not coef:
        return None, None
    kg = today_s / coef
    kwh = kg * ENERGY_MJ_PER_KG / MJ_PER_KWH
    return kg, kwh


def _projected_daily(today_kwh: float | None, now: datetime) -> float | None:
    """Dzisiejsze zużycie wyciągnięte liniowo na całą dobę wg aktualnej pory
    dnia - `None` bez danych o dzisiejszym zużyciu albo dokładnie o północy
    (dzielenie przez zero; i tak wtedy today_kwh też dopiero startuje od zera)."""
    if today_kwh is None:
        return None
    elapsed_fraction = (now.hour * 3600 + now.minute * 60 + now.second) / 86400.0
    if elapsed_fraction <= 0:
        return None
    return today_kwh / elapsed_fraction


def estimate(current_total_s: float | None = None, now: datetime | None = None) -> dict | None:
    """Payload do opublikowania, albo None gdy nie ma jeszcze żadnego
    tankowania w dzienniku (nic do szacowania)."""
    records = refuels.read_all()
    if not records:
        return None

    level = None
    baseline_s = None
    active_bag_size = None

    for record in records:
        level = _burn(level, baseline_s, active_bag_size, record.feeder_total_s)
        if record.filled_to_full:
            level = TANK_CAPACITY_KG
        else:
            level = min(TANK_CAPACITY_KG, (level or 0.0) + record.total_kg)
        baseline_s = record.feeder_total_s
        active_bag_size = record.bag_size_kg

    if current_total_s is None:
        current_total_s = mqttclient.cache.value(FEEDER_COUNTERS_TOPIC, 'total_s')
    level = _burn(level, baseline_s, active_bag_size, current_total_s)

    if level is None:
        return None

    today_s = mqttclient.cache.value(FEEDER_COUNTERS_TOPIC, 'today_s')
    today_kg, today_kwh = _daily_coal(active_bag_size, today_s)
    projected_kwh = _projected_daily(today_kwh, now or datetime.now())

    last = records[-1]
    return {
        'value': round(100.0 * level / TANK_CAPACITY_KG, 1),  # % - pole "value" jak inne sensory
        'kg': round(level, 1),
        'tank_capacity_kg': TANK_CAPACITY_KG,
        'last_refuel_timestamp': last.timestamp.isoformat(timespec='seconds'),
        'last_refuel_total_s': last.feeder_total_s,
        'last_refuel_filled_to_full': last.filled_to_full,
        'last_refuel_bag_size_kg': last.bag_size_kg,
        'coefficient_s_per_kg': refuels.coefficient_for(active_bag_size),
        'today_coal_kg': None if today_kg is None else round(today_kg, 1),
        'today_energy_kwh': None if today_kwh is None else round(today_kwh, 1),
        'projected_daily_kwh': None if projected_kwh is None else round(projected_kwh, 1),
    }


def publish_once() -> dict | None:
    payload = estimate()
    if payload is None:
        LOG.info('fuel_level: brak tankowań w dzienniku, nic do publikacji')
        return None
    info = mqttclient.publish(TOPIC, json.dumps(payload), qos=0, retain=True)
    rc = getattr(info, 'rc', None)
    if rc not in (None, 0):
        # QoS 0 + niepołączony klient = wiadomość po prostu ginie, bez wyjątku -
        # stąd jawne sprawdzenie, inaczej ten brak jest niewidoczny jak dzisiaj.
        LOG.warning('fuel_level: publish nieudany (rc=%s) - %.1f%% (%.1f kg) zgubione',
                   rc, payload['value'], payload['kg'])
    else:
        LOG.info('fuel_level: %.1f%% (%.1f kg)', payload['value'], payload['kg'])
    return payload


async def publish_loop(interval: float = PUBLISH_INTERVAL_SECONDS,
                       startup_delay: float = 5.0) -> None:
    """Startuje z opóźnieniem: ten task rusza w tej samej chwili, co
    mqttclient.start(), ale połączenie z brokerem (connect_async) kończy się
    chwilę później - bez tego opóźnienia pierwsza próba potrafi trafić na
    MQTT_ERR_NO_CONN i przepaść bez śladu aż do następnej, godzinę później."""
    await asyncio.sleep(startup_delay)
    while True:
        try:
            publish_once()
        except Exception:
            LOG.exception('Błąd publikacji fuel_level')
        await asyncio.sleep(interval)
