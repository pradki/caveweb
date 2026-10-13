# -*- coding: utf-8 -*-
"""Testy odkrywania modułów/kanałów przekaźników i ręcznych komend (relay_control.py).

    python tests/test_relay_control.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import mqttclient, relay_control
from caveweb.pages import relays


def reset():
    mqttclient.cache.clear()


# --- discover_modules: tylko bitmaska (4 segmenty), nie per-kanał (5) -------

reset()
mqttclient.cache.put('cave/relay/relay_heating/status', {'channels': 30})
mqttclient.cache.put('cave/relay/relay_heating/co_fan/status', {'channel': 1, 'state': 'off'})
mqttclient.cache.put('cave/relay/relay_cwu/status', {'channels': 8})
mqttclient.cache.put('cave/sensors/temperature/furnace_temp', {'value': 60})
check("tylko moduły z bitmaską, posortowane",
      relay_control.discover_modules() == ['relay_cwu', 'relay_heating'])

# --- channel_count: z pola 'channels' bitmaski, None gdy brak --------------

check("channel_count czyta pole 'channels'", relay_control.channel_count('relay_heating') == 30)
check("channel_count nieznanego modułu -> None", relay_control.channel_count('relay_unknown') is None)

# --- discover_channel_names: {kanał: alias_albo_chN} z payloadów per-kanał --

reset()
mqttclient.cache.put('cave/relay/relay_heating/status', {'channels': 30})
mqttclient.cache.put('cave/relay/relay_heating/co_fan/status',
                     {'channel': 1, 'state': 'off', 'by': None, 'priority': None})
mqttclient.cache.put('cave/relay/relay_heating/co_pump_boiler/status',
                     {'channel': 3, 'state': 'flash_on', 'by': 'caveweb', 'priority': 20,
                      'expires_at': 1_800_000_600.0})
mqttclient.cache.put('cave/relay/relay_heating/ch5/status',
                     {'channel': 5, 'state': 'on', 'by': 'heating_service', 'priority': 10})
mqttclient.cache.put('cave/relay/relay_cwu/cwu_l1/status', {'channel': 1, 'state': 'off'})
names = relay_control.discover_channel_names('relay_heating')
check("mapuje kanał -> nazwa (alias albo chN)",
      names == {1: 'co_fan', 3: 'co_pump_boiler', 5: 'ch5'})
check("nie miesza kanałów z innego modułu", 1 not in [c for c in names if names[c] == 'cwu_l1'])

# --- channel_rows: pełny wiersz na kanał, nieznane -> ch<N> i puste pola ----

rows = relay_control.channel_rows('relay_heating')
check("tyle wierszy, ile 'channels' w bitmasce", len(rows) == 30)
row1 = next(r for r in rows if r['channel'] == 1)
check("wiersz znanego kanału niesie state/by/priority",
      row1 == {'channel': 1, 'name': 'co_fan', 'state': 'off', 'by': None,
              'priority': None, 'expires_at': None})
row3 = next(r for r in rows if r['channel'] == 3)
check("inny znany kanał, z terminem wygaśnięcia leasingu",
      row3 == {'channel': 3, 'name': 'co_pump_boiler', 'state': 'flash_on',
              'by': 'caveweb', 'priority': 20, 'expires_at': 1_800_000_600.0})
row2 = next(r for r in rows if r['channel'] == 2)
check("kanał bez żadnego statusu -> ch<N>, puste pola",
      row2 == {'channel': 2, 'name': 'ch2', 'state': None, 'by': None,
              'priority': None, 'expires_at': None})

reset()
check("brak bitmaski -> pusta lista wierszy", relay_control.channel_rows('relay_heating') == [])


# --- send_command: schemat payloadu, jak każdy inny serwis ------------------

class FakeClient:
    def __init__(self):
        self.calls = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.calls.append((topic, json.loads(payload), qos, retain))
        return self


class FakeClientFail(FakeClient):
    rc = 4

    def publish(self, topic, payload, qos=0, retain=False):
        super().publish(topic, payload, qos, retain)
        return self


mqttclient._client = FakeClient()
ok, message = relay_control.send_command('relay_heating', 'co_fan', 'flash_on', 50, duration=30.0)
check("flash_on: sukces", ok is True)
check("flash_on: topic adresuje właściwy moduł/kanał/serwis",
      mqttclient._client.calls[-1][0] == 'cave/relay/relay_heating/co_fan/cmd/caveweb')
check("flash_on: payload niesie cmd/priority/duration",
      mqttclient._client.calls[-1][1] == {'cmd': 'flash_on', 'priority': 50, 'duration': 30.0})
check("komendy przekaźnika idą z qos=1", mqttclient._client.calls[-1][2] == 1)
check("komenda nie jest retained", mqttclient._client.calls[-1][3] is False)

mqttclient._client = FakeClient()
ok, _ = relay_control.send_command('relay_heating', 'co_fan', 'on', 50)
check("on bez podanego ttl dostaje domyślny DEFAULT_DURATION",
      mqttclient._client.calls[-1][1] == {'cmd': 'on', 'priority': 50,
                                          'ttl': relay_control.DEFAULT_DURATION})

mqttclient._client = FakeClient()
relay_control.send_command('relay_heating', 'co_fan', 'off', 50, ttl=120.0)
check("off z jawnym ttl", mqttclient._client.calls[-1][1] == {'cmd': 'off', 'priority': 50, 'ttl': 120.0})

ok, message = relay_control.send_command('relay_heating', 'co_fan', 'toggle', 50)
check("nieznana/nieobsługiwana komenda -> odmowa", ok is False)

mqttclient._client = FakeClientFail()
ok, message = relay_control.send_command('relay_heating', 'co_fan', 'on', 50)
check("błąd publikacji (rc != 0) -> odmowa z komunikatem", ok is False and 'rc=4' in message)


# --- _format_expiry: odliczanie do wygaśnięcia leasingu, na stronie /relays -

check("brak terminu -> myślnik", relays._format_expiry(None) == '–')
check("już minęło -> 'wygasło'", relays._format_expiry(100.0, now=200.0) == 'wygasło')
check("sekundy", relays._format_expiry(145.0, now=100.0) == 'za 45 s')
check("minuty", relays._format_expiry(100.0 + 300.0, now=100.0) == 'za 5 min')
check("godziny", relays._format_expiry(100.0 + 7200.0, now=100.0) == 'za 2.0 h')

check("DURATION_UNITS: sekundy/minuty/godziny względem sekund",
      relays.DURATION_UNITS == {'s': 1.0, 'min': 60.0, 'h': 3600.0})

done()
