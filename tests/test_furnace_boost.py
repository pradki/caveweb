# -*- coding: utf-8 -*-
"""Testy "wypalania" - chwilowego +10°C na nastawie pieca, patrz furnace_boost.py.

    python tests/test_furnace_boost.py
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import config, furnace_boost, mqttclient

tmp_dir = Path(tempfile.mkdtemp())
config.FURNACE_BOOST_PATH = tmp_dir / 'furnace_boost.json'


class FakeClient:
    def __init__(self):
        self.calls = []

    def publish(self, topic, payload, qos=0, retain=False):
        self.calls.append((topic, json.loads(payload), qos, retain))
        return 'ok'


def reset():
    config.FURNACE_BOOST_PATH.unlink(missing_ok=True)
    mqttclient.cache.clear()
    mqttclient._client = FakeClient()
    return mqttclient._client


# --- brak nastawy z brokera -> odmowa, nic nie publikuje, nic nie zapisuje ---

fake = reset()
ok, message = furnace_boost.start_boost()
check("brak nastawy w cache -> odmowa", ok is False and 'broker' in message)
check("nic nie opublikowane", fake.calls == [])
check("brak zapisanego stanu", furnace_boost.load_state() is None)

# --- start: podnosi o +10, zapisuje stan, publikuje retained -----------------

fake = reset()
mqttclient.cache.put(furnace_boost.TOPIC, {'value': 60}, when=1_800_000_000.0)
now = datetime(2026, 10, 11, 12, 0, 0)
ok, message = furnace_boost.start_boost(now=now)
check("start zwraca sukces", ok is True)
check("podniesione o +10", fake.calls[0][1] == {'value': 70})
check("nastawa publikowana z retain=True", fake.calls[0][3] is True)
state = furnace_boost.load_state()
check("stan niesie oryginalną i podniesioną wartość",
      state['original_value'] == 60 and state['boosted_value'] == 70)
check("termin to +10 minut", datetime.fromisoformat(state['expires_at']) == now + timedelta(minutes=10))

# --- pompa kopnięta od razu na start, wyższy priorytet niż heating-controller -

check("pompa dostaje osobną komendę na swoim topicu",
      fake.calls[1][0] == furnace_boost.PUMP_TOPIC)
check("flash_on na tyle samo czasu co wypalanie, priorytet wyższy niż 10",
      fake.calls[1][1] == {'cmd': 'flash_on', 'duration': 600.0, 'priority': 20}
      and furnace_boost.PUMP_PRIORITY > 10)
check("komenda pompy z qos=1, nie retained",
      fake.calls[1][2] == 1 and fake.calls[1][3] is False)

# --- druga próba startu, gdy już aktywne -> odmowa, bez podwójnego +10 -------

ok2, message2 = furnace_boost.start_boost(now=now)
check("drugi start odmówiony - wypalanie już trwa", ok2 is False)
check("stan się nie zmienił", furnace_boost.load_state() == state)

# --- clamp do max z heating_params, gdy +10 by je przekroczyło ---------------

fake = reset()
mqttclient.cache.put(furnace_boost.TOPIC, {'value': 65}, when=1_800_000_000.0)  # max=72
ok, message = furnace_boost.start_boost(now=now)
check("ograniczone do maksimum (72), nie 75", fake.calls[0][1] == {'value': 72})
check("komunikat wspomina ograniczenie", 'ograniczone' in message)

# --- anulowanie ręczne: wraca do oryginalnej wartości, czyści stan -----------

fake = reset()
mqttclient.cache.put(furnace_boost.TOPIC, {'value': 60}, when=1_800_000_000.0)
furnace_boost.start_boost(now=now)
fake.calls.clear()
ok, message = furnace_boost.cancel_boost()
check("anulowanie zwraca sukces", ok is True)
check("publikuje powrót do oryginalnej wartości", fake.calls[-1][1] == {'value': 60})
check("stan wyczyszczony", furnace_boost.load_state() is None)

# --- anulowanie bez aktywnego wypalania -> odmowa ----------------------------

ok, message = furnace_boost.cancel_boost()
check("anulowanie bez aktywnego wypalania -> odmowa", ok is False)

# --- check_expired: nic nie robi przed terminem ------------------------------

fake = reset()
mqttclient.cache.put(furnace_boost.TOPIC, {'value': 60}, when=1_800_000_000.0)
furnace_boost.start_boost(now=now)
fake.calls.clear()
acted = furnace_boost.check_expired(now=now + timedelta(minutes=5))
check("przed terminem - nic nie robi", acted is False and fake.calls == [])
check("stan wciąż aktywny", furnace_boost.load_state() is not None)

# --- check_expired: po terminie wraca do oryginalnej wartości i czyści stan --

acted = furnace_boost.check_expired(now=now + timedelta(minutes=10, seconds=1))
check("po terminie - zadziałał", acted is True)
check("publikuje powrót do oryginalnej wartości", fake.calls[-1][1] == {'value': 60})
check("stan wyczyszczony po wygaśnięciu", furnace_boost.load_state() is None)

# --- to samo po "restarcie" - termin miniony w trakcie, gdy usługa nie działała

fake = reset()
mqttclient.cache.put(furnace_boost.TOPIC, {'value': 62}, when=1_800_000_000.0)
furnace_boost.start_boost(now=now)
fake.calls.clear()
acted = furnace_boost.check_expired(now=now + timedelta(hours=2))  # dawno po terminie
check("pierwsze sprawdzenie po starcie też wraca, mimo że minęło dużo czasu",
      acted is True and fake.calls[-1][1] == {'value': 62})

done()
