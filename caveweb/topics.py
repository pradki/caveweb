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

# Moduł przekaźników, na którym wiszą dmuchawa i podajnik kotła.
# Zmieni się, jeśli w bramie przekaźników przemianujesz moduł.
RELAY_MODULE = 'wsdev186'


def sensor(name: str, kind: str = 'temperature') -> str:
    return f'cave/sensors/{kind}/{name}'


def deye(name: str) -> str:
    return f'cave/deye/params/{name}'


def relay_status(alias: str, module: str = RELAY_MODULE) -> str:
    return f'cave/relay/{module}/{alias}/status'


def relay_counters(alias: str, module: str = RELAY_MODULE) -> str:
    return f'cave/relay/{module}/{alias}/counters'
