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
"""

from __future__ import annotations
__version__ = "0.1"

import asyncio
import json
import logging

from . import mqttclient, refuels, topics

LOG = logging.getLogger('caveweb.fuel_level')

TOPIC = 'cave/heating/fuel_level'
TANK_CAPACITY_KG = 200.0
PUBLISH_INTERVAL_SECONDS = 3600.0
FEEDER_COUNTERS_TOPIC = topics.relay_counters('co_feeder')


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


def estimate(current_total_s: float | None = None) -> dict | None:
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
    }


def publish_once() -> dict | None:
    payload = estimate()
    if payload is not None:
        mqttclient.publish(TOPIC, json.dumps(payload), qos=0, retain=True)
        LOG.info('fuel_level: %.1f%% (%.1f kg)', payload['value'], payload['kg'])
    return payload


async def publish_loop(interval: float = PUBLISH_INTERVAL_SECONDS) -> None:
    while True:
        try:
            publish_once()
        except Exception:
            LOG.exception('Błąd publikacji fuel_level')
        await asyncio.sleep(interval)
