# -*- coding: utf-8 -*-
"""Testy wczytywania konfiguracji - bez pytest.

    python tests/test_config.py
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import config


tmp_dir = Path(tempfile.mkdtemp())
DEFAULTS = dict(config.HTTP)


def write_config(payload, name='caveweb.json'):
    path = tmp_dir / name
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def reset():
    """Każdy przypadek startuje od wartości domyślnych modułu."""
    config.DB_PATH = Path('/domyslna/measurements.db')
    config.REFRESH_SECONDS = 60.0
    config.HTTP.clear()
    config.HTTP.update(DEFAULTS)


# 1. plik nadpisuje bazę, interwał i wybrane klucze http
reset()
path = write_config({
    'database': {'path': '/z/pliku/measurements.db'},
    'ui': {'refresh_seconds': 15},
    'http': {'port': 9000, 'storage_secret': 'tajne'},
})
loaded = config.load(path)
check("load zwraca ścieżkę pliku", loaded == path)
check("database.path nadpisane", config.DB_PATH == Path('/z/pliku/measurements.db'))
check("refresh_seconds nadpisane", config.REFRESH_SECONDS == 15.0)
check("http.port nadpisany", config.HTTP['port'] == 9000)
check("http.storage_secret nadpisany", config.HTTP['storage_secret'] == 'tajne')
check("nietknięte klucze zostają domyślne", config.HTTP['host'] == '0.0.0.0')

# 2. --db wygrywa z plikiem
reset()
path = write_config({'database': {'path': '/z/pliku/measurements.db'}})
config.load(path, db='/z/linii/polecen.db')
check("--db wygrywa z plikiem", config.DB_PATH == Path('/z/linii/polecen.db'))

# 3. literówka w sekcji http to błąd startu, nie cicha ignorancja
reset()
path = write_config({'http': {'porrt': 9000}}, name='zla.json')
try:
    config.load(path)
    check("nieznany klucz http podnosi ValueError", False)
except ValueError as error:
    check("nieznany klucz http podnosi ValueError", 'http.porrt' in str(error))

# 4. brak pliku: wymagany podnosi wyjątek, opcjonalny przechodzi
reset()
missing = tmp_dir / 'nie-ma.json'
try:
    config.load(missing)
    check("brak wymaganego pliku -> FileNotFoundError", False)
except FileNotFoundError:
    check("brak wymaganego pliku -> FileNotFoundError", True)

reset()
check("brak opcjonalnego pliku -> None", config.load(missing, required=False) is None)
check("wartości domyślne nietknięte", config.DB_PATH == Path('/domyslna/measurements.db'))

# 5. zmienna środowiskowa ma pierwszeństwo przy szukaniu bazy
old_env = os.environ.get('CAVE_DB_PATH')
os.environ['CAVE_DB_PATH'] = '/ze/srodowiska.db'
try:
    check("CAVE_DB_PATH wygrywa", config.resolve_db_path() == Path('/ze/srodowiska.db'))
finally:
    if old_env is None:
        os.environ.pop('CAVE_DB_PATH', None)
    else:
        os.environ['CAVE_DB_PATH'] = old_env

done()
