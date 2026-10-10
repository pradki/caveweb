# -*- coding: utf-8 -*-
"""Testy ustawień wygaszacza ekranu (/settings) - bez pytest.

    python tests/test_settings.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import config
from caveweb.pages import settings

tmp_dir = Path(tempfile.mkdtemp())

# --- brak pliku -> wartości domyślne -----------------------------------------

config.SCREEN_IDLE_SETTINGS_PATH = tmp_dir / 'nie-ma.json'
check("brak pliku -> domyślne", settings.load() == settings.DEFAULTS)

# --- zapis i odczyt z powrotem ------------------------------------------------

config.SCREEN_IDLE_SETTINGS_PATH = tmp_dir / 'screen_idle.json'
settings.save({'enabled': False, 'timeout_seconds': 45, 'restart_wayvnc_on_wake': False})
check("zapisane ustawienia wracają takie same", settings.load() == {
    'enabled': False, 'timeout_seconds': 45, 'restart_wayvnc_on_wake': False,
})

# --- plik częściowy uzupełnia się domyślnymi (np. po dodaniu nowego klucza) --

config.SCREEN_IDLE_SETTINGS_PATH.write_text(json.dumps({'enabled': False}), encoding='utf-8')
loaded = settings.load()
check("częściowy plik dziedziczy resztę z domyślnych",
      loaded['enabled'] is False
      and loaded['timeout_seconds'] == settings.DEFAULTS['timeout_seconds']
      and loaded['restart_wayvnc_on_wake'] == settings.DEFAULTS['restart_wayvnc_on_wake'])

# --- zepsuty JSON nie wywraca strony, tylko wraca do domyślnych --------------

config.SCREEN_IDLE_SETTINGS_PATH.write_text('{nie-json', encoding='utf-8')
check("zepsuty plik -> domyślne, bez wyjątku", settings.load() == settings.DEFAULTS)

# --- restart_screen_idle() nie rzuca, gdy systemctl/usługa niedostępne ------

ok, message = settings.restart_screen_idle()
check("restart_screen_idle zwraca (bool, opis), nawet gdy usługa nie istnieje tu lokalnie",
      isinstance(ok, bool) and isinstance(message, str) and message != '')

done()
