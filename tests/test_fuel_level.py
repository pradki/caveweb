# -*- coding: utf-8 -*-
"""Testy szacunku poziomu paliwa - bez pytest, bez żywego dziennika na Pi.

    python tests/test_fuel_level.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import config, fuel_level, mqttclient, refuels, topics

tmp_dir = Path(tempfile.mkdtemp())
FEEDER_TOPIC = topics.relay_counters('co_feeder')


def set_current_total_s(value):
    mqttclient.cache.clear()
    mqttclient.cache.put(FEEDER_TOPIC, {'total_s': value}, when=1_800_000_000.0)


# --- brak dziennika -> nic do oszacowania ------------------------------------

config.REFUELS_PATH = tmp_dir / 'empty.csv'
check("brak tankowań -> None", fuel_level.estimate() is None)

# --- jedno tankowanie do pełna, zużycie liczone wg startowego 308 s/kg -------

config.REFUELS_PATH = tmp_dir / 'one.csv'
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=1000.0)
set_current_total_s(1000.0 + 15400.0)  # 15400s / 308 s/kg = 50 kg spalone
payload = fuel_level.estimate()
check("poziom po jednym tankowaniu: 200-50=150 kg", abs(payload['kg'] - 150.0) < 0.5)
check("procent liczony z pojemności 200 kg", abs(payload['value'] - 75.0) < 0.5)
check("payload niesie dane ostatniego tankowania",
      payload['last_refuel_bag_size_kg'] == 25
      and payload['last_refuel_filled_to_full'] is True
      and payload['last_refuel_total_s'] == 1000.0)
check("współczynnik w payloadzie to wartość startowa (brak jeszcze pomiaru)",
      abs(payload['coefficient_s_per_kg'] - 308.0) < 0.01)

# --- druga para "do pełna" nadpisuje współczynnik zmierzoną wartością --------

config.REFUELS_PATH = tmp_dir / 'two.csv'
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=0.0)
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=100000.0)
# zmierzony współczynnik: 200 kg / 100000 s = 500 s/kg (inny niż startowe 308)
set_current_total_s(100000.0 + 50000.0)  # 50000s / 500 s/kg = 100 kg spalone
payload = fuel_level.estimate()
check("po zmierzeniu współczynnika zużycie liczy się wg niego, nie startowej wartości",
      abs(payload['kg'] - 100.0) < 0.5)
check("coefficient_s_per_kg w payloadzie to zmierzona wartość",
      abs(payload['coefficient_s_per_kg'] - 500.0) < 0.1)

# --- tankowanie "nie do pełna" dokłada swoją ilość zamiast resetować --------

config.REFUELS_PATH = tmp_dir / 'partial.csv'
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=0.0)
set_current_total_s(0.0)  # żadnego zużycia jeszcze - zostaje 200 kg
refuels.append(bags=2, bag_size_kg=25, filled_to_full=False, feeder_total_s=0.0)
check("dołożenie bez 'do pełna' nie przekracza pojemności (już było 200)",
      fuel_level.estimate(current_total_s=0.0)['kg'] <= 200.0)

config.REFUELS_PATH = tmp_dir / 'partial2.csv'
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=0.0)
# 61600s przy 308 s/kg = 200 kg spalone -> tuż przed zera
refuels.append(bags=2, bag_size_kg=25, filled_to_full=False, feeder_total_s=61600.0)
# dołożone 50 kg (2 x 25kg) do czegoś bliskiego zeru
check("częściowe tankowanie dokłada swoją ilość, nie resetuje do pełna",
      abs(fuel_level.estimate(current_total_s=61600.0)['kg'] - 50.0) < 1.0)

done()
