# -*- coding: utf-8 -*-
"""Testy dopisywania komentarza o tankowaniu do feeder_log.csv.

    python tests/test_feeder_log.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import config, feeder_log

tmp_dir = Path(tempfile.mkdtemp())

# --- dopisuje linię w uzgodnionym formacie, tworząc plik, gdy go nie ma ------

config.FEEDER_LOG_PATH = tmp_dir / 'feeder_log.csv'
feeder_log.append_refuel_comment(total_kg=200.0, bags=8, bag_size_kg=25)
content = config.FEEDER_LOG_PATH.read_text(encoding='utf-8')
check("linia w formacie '# add <kg>kg <n>x<rozmiar>kg'",
      content == '# add 200kg 8x25kg\n')

# --- kolejne wywołanie dopisuje, nie nadpisuje --------------------------------

feeder_log.append_refuel_comment(total_kg=40.0, bags=2, bag_size_kg=20)
lines = config.FEEDER_LOG_PATH.read_text(encoding='utf-8').splitlines()
check("dwie linie po dwóch tankowaniach", lines == [
    '# add 200kg 8x25kg', '# add 40kg 2x20kg',
])

# --- istniejąca zawartość (np. wiersze godzinowe heating-controllera) zostaje -

config.FEEDER_LOG_PATH = tmp_dir / 'with_history.csv'
config.FEEDER_LOG_PATH.write_text('hour,seconds_on\n2026-10-11T10:00:00,70\n',
                                  encoding='utf-8')
feeder_log.append_refuel_comment(total_kg=100.0, bags=4, bag_size_kg=25)
lines = config.FEEDER_LOG_PATH.read_text(encoding='utf-8').splitlines()
check("komentarz dopisany na końcu, historia nietknięta", lines == [
    'hour,seconds_on', '2026-10-11T10:00:00,70', '# add 100kg 4x25kg',
])

# --- brak katalogu docelowego nie wywraca strony - tylko loguje --------------

config.FEEDER_LOG_PATH = tmp_dir / 'nested' / 'feeder_log.csv'
feeder_log.append_refuel_comment(total_kg=50.0, bags=2, bag_size_kg=25)
check("katalog dotworzony, plik powstał", config.FEEDER_LOG_PATH.exists())

done()
