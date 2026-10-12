# -*- coding: utf-8 -*-
"""Topiki MQTT instalacji cave w jednym miejscu.

Konwencja publisherów:
    cave/sensors/temperature/<nazwa>      {"value": 21.5}
    cave/deye/params/<nazwa>              {"value": 1234}
    cave/relay/<modul>/<alias>/status     {"state": true}
    cave/relay/<modul>/<alias>/counters   {"today_s": 0, "total_s": 0, ...}
"""

from __future__ import annotations
__version__ = "0.1"

# Moduł przekaźników, na którym wiszą dmuchawa i podajnik kotła - musi się
# zgadzać z waveshare-mqtt-gateway/config.py (MODULES), inaczej karty
# "Praca urządzeń" milcząco pokazują "brak danych" (nie błąd - po prostu
# nikt nigdy nie publikuje pod źle nazwanym topikiem).
RELAY_MODULE = 'relay_heating'

# Komfort w domu (/comfort) - jeden retained JSON ze wszystkimi polami naraz
# (temperatura, wilgotność, CO2, stan ogrzewania/wentylacji...), bo publisher
# to dopiero przyszła, dedykowana usługa - do tego czasu ląduje tu testowy,
# losowy payload (patrz scripts/comfort_stub.py). caveweb tylko prezentuje.
COMFORT_TOPIC = 'cave/comfort'


def sensor(name: str, kind: str = 'temperature') -> str:
    return f'cave/sensors/{kind}/{name}'


def deye(name: str) -> str:
    return f'cave/deye/params/{name}'


def relay_status(alias: str, module: str = RELAY_MODULE) -> str:
    return f'cave/relay/{module}/{alias}/status'


def relay_counters(alias: str, module: str = RELAY_MODULE) -> str:
    return f'cave/relay/{module}/{alias}/counters'


def relay_cmd(alias: str, service: str, module: str = RELAY_MODULE) -> str:
    """Topic komendy do gatewaya - patrz furnace_boost.py, jedyne miejsce,
    gdzie caveweb steruje przekaźnikiem wprost (poza publikowaniem statusu)."""
    return f'cave/relay/{module}/{alias}/cmd/{service}'
