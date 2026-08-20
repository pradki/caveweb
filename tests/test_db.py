"""Testy warstwy odczytu bazy – na tymczasowej bazie o schemacie metriki."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from caveweb import config, db  # noqa: E402

COLUMNS = [
    'inside_temp_avg', 'inside_temp_min', 'inside_temp_max',
    'outside_temp_avg', 'outside_temp_min', 'outside_temp_max',
    'load_energy_total_delta',
]

QUARTER = 900


def make_db(path: Path, rows_15m):
    """Buduje bazę z podzbiorem kolumn metriki i wstawia podane wiersze."""
    con = sqlite3.connect(path)
    columns = ', '.join(f'{name} REAL' for name in COLUMNS)
    for table in ('measurements_15m', 'measurements_6h', 'measurements_1d'):
        con.execute(f'CREATE TABLE {table} (ts INTEGER PRIMARY KEY, '
                    f'ts_local TEXT NOT NULL, samples INTEGER DEFAULT 0, {columns})')
    con.execute('CREATE TABLE signal_state (name TEXT PRIMARY KEY, '
                'last_value REAL, updated_at INTEGER)')
    placeholders = ', '.join('?' * (2 + len(COLUMNS)))
    for row in rows_15m:
        con.execute(f'INSERT INTO measurements_15m (ts, ts_local, '
                    f'{", ".join(COLUMNS)}) VALUES ({placeholders})', row)
    con.commit()
    con.close()


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    """Baza z czterema kubełkami 15-minutowymi kończącymi się "teraz"."""
    now = 1_800_000_000
    now -= now % QUARTER
    rows = []
    for index, offset in enumerate([3, 2, 1, 0]):
        ts = now - offset * QUARTER
        inside = 20.0 + index
        rows.append((ts, 'x', inside, inside - 0.5, inside + 0.5,
                     10.0 + index, 9.0, 11.0, 0.25))
    # najnowszy wiersz bez temperatury wewnętrznej - latest() ma cofnąć się dalej
    rows.append((now + QUARTER, 'x', None, None, None, 13.0, 9.0, 11.0, None))

    path = tmp_path / 'measurements.db'
    make_db(path, rows)
    monkeypatch.setattr(config, 'DB_PATH', path)
    db._columns_cache.clear()

    class Frozen:
        """Zamiast prawdziwego zegara – "teraz" to najnowszy kubełek."""
        @staticmethod
        def now():
            import datetime
            return datetime.datetime.fromtimestamp(now + QUARTER)

    return Frozen.now()


def test_series_reads_known_columns_and_skips_unknown(prepared):
    data = db.series(['inside_temp_avg', 'nie_ma_takiej'], db.RANGES['day'],
                     now=prepared)
    assert [value for _, value in data['inside_temp_avg']] == [20.0, 21.0, 22.0, 23.0]
    assert data['nie_ma_takiej'] == []


def test_series_skips_nulls(prepared):
    data = db.series(['inside_temp_avg', 'outside_temp_avg'], db.RANGES['day'],
                     now=prepared)
    # najnowszy kubełek ma NULL w inside_temp, ale wartość w outside_temp
    assert len(data['inside_temp_avg']) == 4
    assert len(data['outside_temp_avg']) == 5


def test_series_uses_timestamps_in_milliseconds(prepared):
    data = db.series(['inside_temp_avg'], db.RANGES['day'], now=prepared)
    first, second = data['inside_temp_avg'][0][0], data['inside_temp_avg'][1][0]
    assert second - first == QUARTER * 1000


def test_series_window_cuts_older_buckets(prepared):
    """Zakres roczny czyta inną tabelę - tu pustą, więc serie są puste."""
    data = db.series(['inside_temp_avg'], db.RANGES['year'], now=prepared)
    assert data['inside_temp_avg'] == []


def test_latest_falls_back_to_older_bucket(prepared):
    latest = db.latest(['inside_temp_avg', 'outside_temp_avg'])
    assert latest['inside_temp_avg'][0] == 23.0     # ostatni niepusty
    assert latest['outside_temp_avg'][0] == 13.0    # najnowszy wiersz


def test_stats_of_empty_series():
    assert db.stats([]) == {'min': None, 'max': None, 'avg': None, 'last': None}


def test_stats_values():
    result = db.stats([[1, 1.0], [2, 2.0], [3, 6.0]])
    assert result == {'min': 1.0, 'max': 6.0, 'avg': 3.0, 'last': 6.0}


def test_ranges_point_at_expected_tables():
    assert db.RANGES['day'].table == 'measurements_15m'
    assert db.RANGES['week'].table == 'measurements_6h'
    assert db.RANGES['month'].table == 'measurements_6h'
    assert db.RANGES['year'].table == 'measurements_1d'
    assert db.RANGES['day'].bucket == QUARTER
