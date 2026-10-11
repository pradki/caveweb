# -*- coding: utf-8 -*-
"""Dziennik tankowań podajnika - jedyne miejsce, gdzie caveweb coś zapisuje
zamiast tylko czytać MQTT/metrica (patrz boiler_config.py: publikowanie
nastaw jest celowo nie wpięte, bo zmieniłoby pracę pieca - zapisywanie, kiedy
i ile węgla wsypano, nie wpływa na sterowanie, więc nie ma tego problemu).

Każdy wiersz to jedno zatwierdzone tankowanie: ile worków, jakich (20/25 kg),
czy do pełna, i wartość `total_s` z `cave/relay/relay_heating/co_feeder/counters`
w tamtej chwili. Różnica `total_s` między dwoma kolejnymi tankowaniami "do
pełna" mówi, ile sekund podajnik pracował, żeby spalić to, co dowieziono przy
drugim z nich - stąd współczynnik [s podajnika / kg] per rozmiar worka.

Dla worków 25 kg startowy współczynnik (308 s/kg, do czasu świeższej
kalibracji) policzono ręcznie z historycznego `feeder_log.csv` (sezon
2025/26: 2140 kg / 183:23:54 pracy podajnika). Dla 20 kg nie było żadnych
danych - stąd prowizoryczna wartość przeskalowana wagowo z 25 kg (308 * 20/25
= 246.4 s/kg): worki 20 kg to inny węgiel (gęstszy, per wcześniejszą obserwację),
więc to zgadywanie, nie pomiar - `coefficient_for()` i tak zawsze przedkłada
realną parę tankowań "do pełna" nad tę wartość startową, więc zniknie samo,
gdy tylko taka para 20 kg się pojawi.
"""

from __future__ import annotations
__version__ = "0.1"

import csv
from dataclasses import dataclass
from datetime import datetime

from . import config

HEADER = ['timestamp', 'bags', 'bag_size_kg', 'total_kg', 'filled_to_full', 'feeder_total_s']

DEFAULT_COEFFICIENTS = {25: 308.0, 20: 246.4}  # s/kg, patrz docstring modułu


@dataclass(frozen=True)
class Refuel:
    timestamp: datetime
    bags: int
    bag_size_kg: int
    total_kg: float
    filled_to_full: bool
    feeder_total_s: float | None


def _path():
    return config.REFUELS_PATH


def append(bags: int, bag_size_kg: int, filled_to_full: bool,
          feeder_total_s: float | None) -> Refuel:
    """Dopisuje jedno tankowanie. Nigdy nie nadpisuje istniejących wierszy."""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    record = Refuel(datetime.now(), bags, bag_size_kg, bags * bag_size_kg,
                    filled_to_full, feeder_total_s)
    with path.open('a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(HEADER)
        writer.writerow([
            record.timestamp.isoformat(timespec='seconds'),
            record.bags, record.bag_size_kg, record.total_kg,
            record.filled_to_full,
            '' if record.feeder_total_s is None else record.feeder_total_s,
        ])
    return record


def read_all() -> list[Refuel]:
    path = _path()
    if not path.exists():
        return []
    out = []
    with path.open(newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            out.append(Refuel(
                timestamp=datetime.fromisoformat(row['timestamp']),
                bags=int(row['bags']),
                bag_size_kg=int(row['bag_size_kg']),
                total_kg=float(row['total_kg']),
                filled_to_full=row['filled_to_full'].strip().lower() in ('true', '1'),
                feeder_total_s=float(row['feeder_total_s']) if row['feeder_total_s'] else None,
            ))
    return out


def last() -> Refuel | None:
    records = read_all()
    return records[-1] if records else None


def coefficient_for(bag_size_kg: int) -> float | None:
    """Współczynnik [s podajnika / kg] dla danego rozmiaru worka: średnia ze
    wszystkich par kolejnych tankowań "do pełna", gdzie worek NA POCZĄTKU
    interwału (ten, który się właśnie wypalał) miał ten rozmiar - worek na
    końcu może być inny, to nie ma znaczenia dla tego, co płonęło w trakcie.
    Bez żadnych pasujących par - wartość startowa z DEFAULT_COEFFICIENTS, jeśli
    jest (25 i 20 kg), inaczej None."""
    records = [r for r in read_all() if r.feeder_total_s is not None]
    samples = []
    for prev, curr in zip(records, records[1:]):
        if not (prev.filled_to_full and curr.filled_to_full):
            continue
        if prev.bag_size_kg != bag_size_kg:
            continue
        elapsed = curr.feeder_total_s - prev.feeder_total_s
        if elapsed > 0 and curr.total_kg > 0:
            samples.append(elapsed / curr.total_kg)
    if samples:
        return sum(samples) / len(samples)
    return DEFAULT_COEFFICIENTS.get(bag_size_kg)
