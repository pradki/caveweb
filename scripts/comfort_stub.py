#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tymczasowy generator danych na `cave/comfort` - zanim powstanie prawdziwa,
dedykowana usługa licząca komfort (patrz caveweb/topics.py:COMFORT_TOPIC i
caveweb/pages/comfort.py). caveweb tylko prezentuje to, co znajdzie na tym
topicu - ten skrypt tylko po to, żeby strona /comfort miała co pokazać, zanim
tamta usługa powstanie. Niezależny od pakietu caveweb (sam paho-mqtt), do
ręcznego odpalenia przy testowaniu - nie jest usługą systemd.

    python scripts/comfort_stub.py --host 127.0.0.1
    python scripts/comfort_stub.py --host 127.0.0.1 --once
"""

from __future__ import annotations

import argparse
import json
import random
import time
from datetime import datetime

import paho.mqtt.client as mqtt

TOPIC = 'cave/comfort'


def random_payload(previous: dict | None = None) -> dict:
    """Losowe, ale wiarygodne wartości - lekki dryf od poprzednich zamiast
    pełnego szumu co iterację, żeby wartości na stronie nie skakały bez sensu."""
    prev = previous or {}

    def drift(key, low, high, step):
        base = prev.get(key, (low + high) / 2)
        return round(min(high, max(low, base + random.uniform(-step, step))), 1)

    now = datetime.now()
    temp = drift('temp_current', 17.0, 26.0, 0.3)
    setpoint = 21.0
    return {
        'temp_current': temp,
        'temp_setpoint': setpoint,
        'humidity': drift('humidity', 30.0, 65.0, 2.0),
        'co2': int(drift('co2', 450, 1400, 60)),
        'pm25': None,   # brak czujnika na razie - strona pokaże "–"
        'voc': None,
        'radon': None,
        'mode': 'grzanie',  # etap 1: tylko grzanie, bez chłodzenia/auto
        'hvac_state': 'grzeje' if temp < setpoint else 'czeka',
        'zone': 'Dom',  # jedna strefa na razie
        'schedule_profile': 'dzień roboczy' if now.weekday() < 5 else 'weekend',
        'schedule_mode': 'dzień' if 6 <= now.hour < 22 else 'noc',
        'override_state': 'brak',
        'ventilation_state': 'auto',
        'filter_state': 'brak',
        'damp_state': 'brak',
        'updated_at': now.isoformat(timespec='seconds'),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=1883)
    parser.add_argument('--interval', type=float, default=30.0,
                        help='sekund między publikacjami (domyślnie 30)')
    parser.add_argument('--once', action='store_true',
                        help='publikuj raz i zakończ, zamiast pętli')
    args = parser.parse_args()

    client = mqtt.Client(client_id='comfort-stub', protocol=mqtt.MQTTv311,
                        callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
    client.connect(args.host, args.port, keepalive=30)
    client.loop_start()

    payload = None
    try:
        while True:
            payload = random_payload(payload)
            client.publish(TOPIC, json.dumps(payload), qos=0, retain=True)
            print(f'{payload["updated_at"]}  {TOPIC}  {payload}')
            if args.once:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == '__main__':
    main()
