"""Konfiguracja aplikacji: baza metrica, broker MQTT i serwer HTTP.

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

# Dziennik tankowań podajnika (caveweb/refuels.py) - jedyne miejsce, gdzie ta
# aplikacja coś zapisuje zamiast tylko czytać. Mieszka obok feeder_log.csv,
# nie w repo, więc też wymaga rozwiązania ścieżki pod dev/Pi.
_REFUELS_CANDIDATES = [
    Path('/home/sqna/cave/logs/refuels.csv'),
    Path.home() / 'cave_logs' / 'refuels.csv',
]


def resolve_refuels_path() -> Path:
    env = os.environ.get('CAVE_REFUELS_PATH')
    if env:
        return Path(env)
    for candidate in _REFUELS_CANDIDATES:
        if candidate.parent.exists():
            return candidate
    return _REFUELS_CANDIDATES[-1]


REFUELS_PATH = resolve_refuels_path()

# Ustawienia wygaszacza ekranu (caveweb/pages/settings.py <-> screen_idle_runner.py,
# patrz README "Kiosk"). Osobny mały plik, nie sekcja w caveweb.json - zmienia
# się z poziomu UI w działającej aplikacji, nie przy starcie usługi.
_SCREEN_IDLE_CANDIDATES = [
    Path('/home/sqna/cave/logs/screen_idle.json'),
    Path.home() / 'cave_logs' / 'screen_idle.json',
]


def resolve_screen_idle_settings_path() -> Path:
    env = os.environ.get('CAVE_SCREEN_IDLE_SETTINGS')
    if env:
        return Path(env)
    for candidate in _SCREEN_IDLE_CANDIDATES:
        if candidate.parent.exists():
            return candidate
    return _SCREEN_IDLE_CANDIDATES[-1]


SCREEN_IDLE_SETTINGS_PATH = resolve_screen_idle_settings_path()

# feeder_log.csv - NIE własny plik caveweb: to ten sam CSV, w którym
# heating-controller (feeder_logger.py) zlicza godzinowy czas pracy podajnika.
# caveweb tylko dopisuje do niego komentarz o tankowaniu - patrz feeder_log.py.
_FEEDER_LOG_CANDIDATES = [
    Path('/home/sqna/cave/logs/feeder_log.csv'),
    Path.home() / 'cave_logs' / 'feeder_log.csv',
]


def resolve_feeder_log_path() -> Path:
    env = os.environ.get('CAVE_FEEDER_LOG_PATH')
    if env:
        return Path(env)
    for candidate in _FEEDER_LOG_CANDIDATES:
        if candidate.exists():
            return candidate
    return _FEEDER_LOG_CANDIDATES[-1]


FEEDER_LOG_PATH = resolve_feeder_log_path()

# Stan aktywnego "wypalania" (chwilowe +10°C na piecu, patrz furnace_boost.py) -
# osobny mały plik jak screen_idle.json, żeby restart caveweb w trakcie
# wypalania nie zgubił, do czego i kiedy wrócić.
_FURNACE_BOOST_CANDIDATES = [
    Path('/home/sqna/cave/logs/furnace_boost.json'),
    Path.home() / 'cave_logs' / 'furnace_boost.json',
]


def resolve_furnace_boost_path() -> Path:
    env = os.environ.get('CAVE_FURNACE_BOOST_PATH')
    if env:
        return Path(env)
    for candidate in _FURNACE_BOOST_CANDIDATES:
        if candidate.parent.exists():
            return candidate
    return _FURNACE_BOOST_CANDIDATES[-1]


FURNACE_BOOST_PATH = resolve_furnace_boost_path()

# Co ile sekund wykres sam dociąga nowe dane
REFRESH_SECONDS = 60.0

# Broker MQTT - źródło wartości bieżących. Aplikacja głównie subskrybuje, ale
# też pisze: jeden wyliczony status co godzinę (cave/heating/fuel_level, patrz
# fuel_level.py), nastawy kotła wprost z /boiler/config (Zapisz, patrz
# boiler_config.py), chwilowe samo-odwracalne podniesienie nastawy pieca na
# czas wypalania (furnace_boost.py) i ręczne komendy przekaźników z /relays
# (relay_control.py). Patrz README "Writing setpoints"/"Burning off"/"Relays".
MQTT = {
    'host': '127.0.0.1',
    'port': 1883,
    'client_id': 'caveweb',
    'topics': ('cave/#',),
    'keepalive': 60,
    'username': None,
    'password': None,
}

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
    # None = bez TLS (tak jak dotychczas). Ustawiane na Pi przez caveweb.json,
    # żeby serwować po HTTPS na porcie 443 - patrz README, sekcja "HTTPS".
    'ssl_certfile': None,
    'ssl_keyfile': None,
}


def load(path=None, db=None, required: bool = True):
    """Wczytuje konfigurację JSON i nadpisuje wartości modułu.

    `required=False` pozwala przejść dalej, gdy plik nie istnieje – tak działa
    domyślna ścieżka `caveweb.json` obok skryptu uruchomieniowego.
    Zwraca ścieżkę wczytanego pliku albo None, jeśli zostały wartości domyślne.
    """
    global DB_PATH, REFUELS_PATH, REFRESH_SECONDS

    loaded = None
    if path is not None:
        config_path = Path(path)
        if config_path.exists():
            raw = json.loads(config_path.read_text(encoding='utf-8'))
            database = raw.get('database') or {}
            if database.get('path'):
                DB_PATH = Path(database['path'])
            refuels_section = raw.get('refuels') or {}
            if refuels_section.get('path'):
                REFUELS_PATH = Path(refuels_section['path'])
            ui_section = raw.get('ui') or {}
            if ui_section.get('refresh_seconds'):
                REFRESH_SECONDS = float(ui_section['refresh_seconds'])
            for key, value in (raw.get('http') or {}).items():
                if key not in HTTP:
                    raise ValueError(f'nieznany klucz http.{key} w {config_path}')
                HTTP[key] = value
            for key, value in (raw.get('mqtt') or {}).items():
                if key not in MQTT:
                    raise ValueError(f'nieznany klucz mqtt.{key} w {config_path}')
                # topics w JSON to lista - klient oczekuje krotki
                MQTT[key] = tuple(value) if key == 'topics' else value
            loaded = config_path
        elif required:
            raise FileNotFoundError(f'brak pliku konfiguracji: {config_path}')

    if db is not None:  # --db z linii poleceń wygrywa z plikiem
        DB_PATH = Path(db)
    return loaded
