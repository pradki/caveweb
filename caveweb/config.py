"""Konfiguracja aplikacji: lokalizacja bazy metrica i parametry serwera HTTP.

Wartości domyślne wystarczają do uruchomienia na stacji deweloperskiej.
Na Raspberry Pi nadpisuje je plik JSON (`--config caveweb.json`) albo zmienna
środowiskowa `CAVE_DB_PATH`.
"""

from __future__ import annotations
__version__ = "0.2"

import json
import os
from pathlib import Path

# Kandydaci na ścieżkę do bazy: zmienna środowiskowa CAVE_DB_PATH ma pierwszeństwo,
# potem typowe lokalizacje na Raspberry Pi i na stacji deweloperskiej.
_CANDIDATES = [
    Path('/home/sqna/cave/raspberry/metrica/measurements.db'),
    # Path('/opt/metrica/measurements.db'),
    Path.home() / 'metrica' / 'measurements.db',
    Path('C:/Projects/metrica/measurements.db'),
]


def resolve_db_path() -> Path:
    env = os.environ.get('CAVE_DB_PATH')
    if env:
        return Path(env)
    for candidate in _CANDIDATES:
        if candidate.exists():
            return candidate
    # żaden plik nie istnieje – zwracamy pierwszą ścieżkę, błąd zgłosi warstwa db
    return _CANDIDATES[0]


DB_PATH = resolve_db_path()

# Co ile sekund wykres sam dociąga nowe dane
REFRESH_SECONDS = 60.0

# Argumenty przekazywane do ui.run(). Klucze są jednocześnie listą tego,
# co wolno ustawić w sekcji "http" pliku konfiguracyjnego.
HTTP = {
    'host': '0.0.0.0',
    'port': 8081,
    'title': 'cave',
    'dark': True,
    'show': False,
    'storage_secret': 'caveweb-dev',
    'favicon': '🚀',
    'reload': False,
}


def load(path=None, db=None, required: bool = True):
    """Wczytuje konfigurację JSON i nadpisuje wartości modułu.

    `required=False` pozwala przejść dalej, gdy plik nie istnieje – tak działa
    domyślna ścieżka `caveweb.json` obok skryptu uruchomieniowego.
    Zwraca ścieżkę wczytanego pliku albo None, jeśli zostały wartości domyślne.
    """
    global DB_PATH, REFRESH_SECONDS

    loaded = None
    if path is not None:
        config_path = Path(path)
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding='utf-8'))
            database = raw.get('database') or {}
            if database.get('path'):
                DB_PATH = Path(database['path'])
            ui_section = raw.get('ui') or {}
            if ui_section.get('refresh_seconds'):
                REFRESH_SECONDS = float(ui_section['refresh_seconds'])
            for key, value in (raw.get('http') or {}).items():
                if key not in HTTP:
                    raise ValueError(f'nieznany klucz http.{key} w {config_path}')
                HTTP[key] = value
            loaded = config_path
        elif required:
            raise FileNotFoundError(f'brak pliku konfiguracji: {config_path}')

    if db is not None:  # --db z linii poleceń wygrywa z plikiem
        DB_PATH = Path(db)
    return loaded
