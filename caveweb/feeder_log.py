# -*- coding: utf-8 -*-
"""Komentarz o tankowaniu dopisywany do `feeder_log.csv` - tego samego pliku,
w którym heating-controller (`feeder_logger.py`) zlicza godzinowy czas pracy
podajnika. Format zgodny z ręcznie prowadzoną historią w tym pliku:
`# add <kg>kg <ile>x<rozmiar>kg`, np. `# add 200kg 8x25kg`.

Dwa osobne procesy piszą do tego samego pliku. heating-controller robi pełny
odczyt+nadpisanie przy każdej aktualizacji licznika (i blokuje się na czas tej
operacji - patrz jego feeder_logger.py); caveweb bierze tę samą blokadę na
czas dopisania, żeby komentarz nie trafił w środek tamtego nadpisania i nie
zniknął.
"""

from __future__ import annotations
__version__ = "0.1"

import logging

from . import config

LOG = logging.getLogger('caveweb.feeder_log')

try:
    import fcntl
except ImportError:  # Windows (stacja deweloperska) - bez blokady między procesami
    fcntl = None


def append_refuel_comment(total_kg: float, bags: int, bag_size_kg: int) -> None:
    """Dopisuje jedną linię komentarza na końcu pliku. Błąd (np. plik na
    innej maszynie w trybie dev) tylko loguje - to adnotacja do ręcznego
    przeglądu, nie dane, od których cokolwiek zależy."""
    path = config.FEEDER_LOG_PATH
    line = f'# add {total_kg:.0f}kg {bags}x{bag_size_kg}kg\n'
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'a', newline='') as f:
            if fcntl is not None:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(line)
        LOG.info('feeder_log: %s', line.strip())
    except OSError:
        LOG.exception('Nie udało się dopisać komentarza do %s', path)
