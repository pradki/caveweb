# -*- coding: utf-8 -*-
"""Testy dziennika tankowań - bez pytest, bez żywego pliku na Pi.

    python tests/test_refuels.py
"""

import dataclasses
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import config, refuels

tmp_dir = Path(tempfile.mkdtemp())
config.REFUELS_PATH = tmp_dir / 'refuels.csv'

# --- append + read_all odczytuje to, co zapisano -----------------------------

check("brak pliku -> pusta lista", refuels.read_all() == [])
check("last() na pustym dzienniku -> None", refuels.last() is None)

def without_subseconds(record):
    """CSV trzyma czas z dokładnością do sekundy - do porównań z tym, co
    append() zwraca w pamięci (pełna precyzja datetime.now())."""
    return dataclasses.replace(record, timestamp=record.timestamp.replace(microsecond=0))


r1 = refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=1000.0)
check("append zwraca zapisany rekord", r1.total_kg == 200.0)
check("plik ma nagłówek i jeden wiersz", refuels.read_all() == [without_subseconds(r1)])
check("last() widzi ten jeden wpis", refuels.last() == without_subseconds(r1))

r2 = refuels.append(bags=3, bag_size_kg=20, filled_to_full=False, feeder_total_s=None)
check("drugi wpis dopisany, nie nadpisał pierwszego",
      refuels.read_all() == [without_subseconds(r1), without_subseconds(r2)])
check("last() to teraz drugi wpis", refuels.last() == without_subseconds(r2))
check("brak total_s zapisuje się i czyta jako None", r2.feeder_total_s is None)

# --- coefficient_for: tylko pary "do pełna", przypisane do worka na starcie --

config.REFUELS_PATH = tmp_dir / 'coef.csv'
# cztery tankowania "do pełna" worków 25kg, kolejne total_s różnią się o znane
# wartości - sprawdzamy, że każdy interwał liczy total_kg NASTĘPNEGO wpisu
# podzielone przez różnicę feeder_total_s, i że to się uśrednia poprawnie.
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=0.0)       # 200 kg
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=61600.0)   # 200 kg / 61600s = 308 s/kg
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=123200.0)  # drugi interwał też 308 s/kg
check("współczynnik 25kg z czystych danych = 308 s/kg",
      abs(refuels.coefficient_for(25) - 308.0) < 0.01)
check("brak danych 20kg -> wartość startowa przeskalowana z 25kg (246.4 s/kg)",
      abs(refuels.coefficient_for(20) - 246.4) < 0.01)

config.REFUELS_PATH = tmp_dir / 'mixed.csv'
# worek na STARCIE interwału decyduje o przypisaniu, nie worek na końcu
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=0.0)
refuels.append(bags=10, bag_size_kg=20, filled_to_full=True, feeder_total_s=61600.0)  # spalono 25kg -> 200kg/61600s
check("interwał liczony do worka, który się wypalał (25kg), nie do tego co dosypano (20kg)",
      abs(refuels.coefficient_for(25) - 308.0) < 0.01
      and abs(refuels.coefficient_for(20) - 246.4) < 0.01)  # 20kg wciąż na wartości startowej

config.REFUELS_PATH = tmp_dir / 'skip.csv'
# "nie do pełna" zrywa parę - interwał obejmujący taki wpis jest pomijany
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=0.0)
refuels.append(bags=2, bag_size_kg=25, filled_to_full=False, feeder_total_s=10000.0)
refuels.append(bags=8, bag_size_kg=25, filled_to_full=True, feeder_total_s=70000.0)
check("tankowanie nie do pełna pomijane w obu sąsiadujących interwałach",
      refuels.coefficient_for(25) == 308.0)  # domyślna, bo żadna czysta para nie przeszła

config.REFUELS_PATH = tmp_dir / 'default.csv'
check("25kg bez żadnych danych -> wartość startowa 308 s/kg",
      refuels.coefficient_for(25) == 308.0)
check("20kg bez żadnych danych -> wartość startowa 246.4 s/kg",
      refuels.coefficient_for(20) == 246.4)

# --- raz zmierzona para 20kg nadpisuje wartość startową ----------------------

config.REFUELS_PATH = tmp_dir / 'measured20.csv'
refuels.append(bags=10, bag_size_kg=20, filled_to_full=True, feeder_total_s=0.0)       # 200 kg
refuels.append(bags=10, bag_size_kg=20, filled_to_full=True, feeder_total_s=40000.0)   # 200 kg / 40000s = 200 s/kg
check("realna para 20kg wygrywa z wartością startową",
      abs(refuels.coefficient_for(20) - 200.0) < 0.01)

done()
