# -*- coding: utf-8 -*-
"""Testy warstwy odczytu bazy - bez pytest i bez żywych danych.

    python tests/test_db.py

Buduje tymczasową bazę o schemacie metriki (kubełki 15m/6h/1d) i sprawdza
dobór kolumn, pomijanie NULL-i, okno czasu, latest() oraz stats().
"""

import sqlite3
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()  # pakiet caveweb importuje nicegui, sama warstwa db - nie

from caveweb import config, db


COLUMNS = [
    'inside_temp_avg', 'inside_temp_min', 'inside_temp_max',
    'outside_temp_avg', 'outside_temp_min', 'outside_temp_max',
    'load_energy_total_delta',
]
QUARTER = 900


def make_db(path, rows):
    """Baza z podzbiorem kolumn metriki; dane wstawiamy tylko do tabeli 15m."""
    con = sqlite3.connect(path)
    columns = ', '.join(f'{name} REAL' for name in COLUMNS)
    for table in ('measurements_15m', 'measurements_6h', 'measurements_1d'):
        con.execute(f'CREATE TABLE {table} (ts INTEGER PRIMARY KEY, '
                    f'ts_local TEXT NOT NULL, samples INTEGER DEFAULT 0, {columns})')
    con.execute('CREATE TABLE signal_state (name TEXT PRIMARY KEY, '
                'last_value REAL, updated_at INTEGER)')
    placeholders = ', '.join('?' * (2 + len(COLUMNS)))
    for row in rows:
        con.execute(f'INSERT INTO measurements_15m (ts, ts_local, '
                    f'{", ".join(COLUMNS)}) VALUES ({placeholders})', row)
    con.commit()
    con.close()


# --- przygotowanie: cztery kubełki z temperaturą + jeden najnowszy bez niej ---

NOW = 1_800_000_000
NOW -= NOW % QUARTER

rows = []
for index, offset in enumerate([3, 2, 1, 0]):
    inside = 20.0 + index
    rows.append((NOW - offset * QUARTER, 'x', inside, inside - 0.5, inside + 0.5,
                 10.0 + index, 9.0, 11.0, 0.25))
# najnowszy wiersz bez inside_temp - latest() ma cofnąć się do starszego kubełka
rows.append((NOW + QUARTER, 'x', None, None, None, 13.0, 9.0, 11.0, None))

tmp_dir = Path(tempfile.mkdtemp())
make_db(tmp_dir / 'measurements.db', rows)
config.DB_PATH = tmp_dir / 'measurements.db'
db._columns_cache.clear()

now = datetime.fromtimestamp(NOW + QUARTER)

# 1. znane kolumny czytamy, nieznane dają pustą serię (bez wyjątku)
data = db.series(['inside_temp_avg', 'nie_ma_takiej'], db.RANGES['day'], now=now)
check("czyta kolumnę _avg", [v for _, v in data['inside_temp_avg']] == [20.0, 21.0, 22.0, 23.0])
check("nieznana kolumna -> pusta seria", data['nie_ma_takiej'] == [])

# 2. NULL to nie zero - kubełek bez wartości wypada z serii
data = db.series(['inside_temp_avg', 'outside_temp_avg'], db.RANGES['day'], now=now)
check("NULL pomijany w inside_temp", len(data['inside_temp_avg']) == 4)
check("outside_temp ma wszystkie punkty", len(data['outside_temp_avg']) == 5)

# 3. znaczniki czasu w milisekundach, w kolejności rosnącej
points = data['outside_temp_avg']
check("timestamp w ms", points[1][0] - points[0][0] == QUARTER * 1000)
check("posortowane rosnąco", [p[0] for p in points] == sorted(p[0] for p in points))

# 4. okno czasu: kubełki starsze niż zakres nie wchodzą
old = db.series(['inside_temp_avg'], db.RANGES['day'],
                now=datetime.fromtimestamp(NOW + 3 * 86400))
check("stare kubełki poza oknem", old['inside_temp_avg'] == [])

# 5. zakres roczny czyta inną tabelę - tu pustą
year = db.series(['inside_temp_avg'], db.RANGES['year'], now=now)
check("zakres roczny czyta measurements_1d", year['inside_temp_avg'] == [])

# 6. latest() cofa się, dopóki nie znajdzie wartości
latest = db.latest(['inside_temp_avg', 'outside_temp_avg'])
check("latest cofa się przez NULL", latest['inside_temp_avg'][0] == 23.0)
check("latest bierze najnowszy wiersz", latest['outside_temp_avg'][0] == 13.0)

# 7. statystyki
check("stats pustej serii", db.stats([]) ==
      {'min': None, 'max': None, 'avg': None, 'last': None})
check("stats wartości", db.stats([[1, 1.0], [2, 2.0], [3, 6.0]]) ==
      {'min': 1.0, 'max': 6.0, 'avg': 3.0, 'last': 6.0})

# 8. zakresy wskazują właściwe tabele i kubełki
check("day -> 15m", db.RANGES['day'].table == 'measurements_15m' and
      db.RANGES['day'].bucket == QUARTER)
check("week -> 6h", db.RANGES['week'].table == 'measurements_6h')
check("month -> 6h", db.RANGES['month'].table == 'measurements_6h')
check("year -> 1d", db.RANGES['year'].table == 'measurements_1d')

done()
