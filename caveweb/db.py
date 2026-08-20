"""Warstwa dostępu do bazy metrica – tylko czytanie gotowych rollupów.

Baza `measurements.db` zawiera trzy tabele zagregowane po czasie:
    measurements_15m – kubełki 15-minutowe
    measurements_6h  – kubełki 6-godzinne
    measurements_1d  – kubełki dobowe
Każda tabela ma kolumny `<sygnał>_avg` / `_min` / `_max` (dla typu gauge)
oraz `_start` / `_end` / `_delta` (dla liczników).
"""

from __future__ import annotations
__version__ = "0.2"

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import config


@dataclass(frozen=True)
class Range:
    """Definicja zakresu wykresu: która tabela, jak szeroko i jak podpisać oś."""
    key: str
    label: str
    table: str
    span: timedelta
    bucket: int  # długość kubełka w sekundach


RANGES: dict[str, Range] = {
    'day':   Range('day',   'Doba',    'measurements_15m', timedelta(days=1),     900),
    'week':  Range('week',  'Tydzień', 'measurements_6h',  timedelta(days=7),   21600),
    'month': Range('month', 'Miesiąc', 'measurements_6h',  timedelta(days=30),  21600),
    'year':  Range('year',  'Rok',     'measurements_1d',  timedelta(days=365), 86400),
}

DEFAULT_RANGE = 'day'

# cache nazw kolumn – nie chcemy pytać bazy o schemat przy każdym odświeżeniu
_columns_cache: dict[str, set[str]] = {}


@contextmanager
def _connect():
    """Połączenie tylko do czytania (zamykane po wyjściu z bloku).

    Metrica pisze do bazy w trybie WAL. Otwarcie `mode=ro` jest bezpieczne,
    ale gdy w katalogu zostanie osierocony plik -wal, SQLite musi go odtworzyć,
    a tego w trybie ro nie zrobi – wtedy wracamy do zwykłego otwarcia.
    """
    db_path = config.DB_PATH
    uri = f'file:{db_path.as_posix()}?mode=ro'
    con = sqlite3.connect(uri, uri=True, timeout=5.0)
    try:
        con.execute('SELECT count(*) FROM sqlite_master').fetchone()
    except sqlite3.DatabaseError:
        con.close()
        con = sqlite3.connect(str(db_path), timeout=5.0)
        # w trybie awaryjnym baza jest otwarta do zapisu – blokujemy go pragmą
        con.execute('PRAGMA query_only = 1')
    try:
        yield con
    finally:
        con.close()


def table_columns(table: str) -> set[str]:
    """Zbiór kolumn tabeli (z cache) – używany do walidacji nazw serii."""
    if table not in _columns_cache:
        with _connect() as con:
            rows = con.execute(f'PRAGMA table_info({table})').fetchall()
        _columns_cache[table] = {row[1] for row in rows}
    return _columns_cache[table]


def series(columns: list[str], rng: Range, now: datetime | None = None) -> dict[str, list[list]]:
    """Odczytuje wskazane kolumny z tabeli zakresu.

    Zwraca słownik {nazwa_kolumny: [[timestamp_ms, wartość], ...]}.
    Punkty bez wartości (NULL) są pomijane, więc przerwy w danych zostają
    przerwami na wykresie.
    """
    available = table_columns(rng.table)
    wanted = [c for c in columns if c in available]
    result: dict[str, list[list]] = {c: [] for c in columns}
    if not wanted:
        return result

    now = now or datetime.now()
    ts_to = int(now.timestamp())
    ts_from = ts_to - int(rng.span.total_seconds())

    sql = (
        f'SELECT ts, {", ".join(wanted)} FROM {rng.table} '
        'WHERE ts >= ? AND ts <= ? ORDER BY ts'
    )
    with _connect() as con:
        rows = con.execute(sql, (ts_from, ts_to)).fetchall()

    for row in rows:
        ts_ms = row[0] * 1000
        for idx, name in enumerate(wanted, start=1):
            value = row[idx]
            if value is not None:
                result[name].append([ts_ms, round(value, 2)])
    return result


def latest(columns: list[str], table: str = 'measurements_15m',
           lookback: int = 8) -> dict[str, tuple[float, int]]:
    """Ostatnia znana wartość kolumn – z kilku najświeższych kubełków 15-minutowych.

    Tabela `signal_state` trzyma tylko liczniki, więc bieżące odczyty gauge
    bierzemy z najnowszego wiersza rollupu (z pominięciem NULL-i).
    """
    available = table_columns(table)
    wanted = [c for c in columns if c in available]
    if not wanted:
        return {}
    sql = (
        f'SELECT ts, {", ".join(wanted)} FROM {table} '
        'ORDER BY ts DESC LIMIT ?'
    )
    with _connect() as con:
        rows = con.execute(sql, (lookback,)).fetchall()

    result: dict[str, tuple[float, int]] = {}
    for row in rows:  # wiersze od najnowszego
        for idx, name in enumerate(wanted, start=1):
            if name not in result and row[idx] is not None:
                result[name] = (row[idx], row[0])
    return result


def last_values(names: list[str]) -> dict[str, tuple[float, int] | None]:
    """Ostatnie wartości sygnałów z tabeli `signal_state` (nazwa -> (wartość, ts))."""
    if not names:
        return {}
    placeholders = ', '.join('?' * len(names))
    sql = (
        'SELECT name, last_value, updated_at FROM signal_state '
        f'WHERE name IN ({placeholders})'
    )
    with _connect() as con:
        rows = con.execute(sql, names).fetchall()
    found = {row[0]: (row[1], row[2]) for row in rows}
    return {name: found.get(name) for name in names}


def stats(points: list[list]) -> dict[str, float | None]:
    """Prosta statystyka serii (min / max / średnia / ostatnia wartość)."""
    values = [p[1] for p in points]
    if not values:
        return {'min': None, 'max': None, 'avg': None, 'last': None}
    return {
        'min': min(values),
        'max': max(values),
        'avg': round(sum(values) / len(values), 2),
        'last': values[-1],
    }
