#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wrapper na swayidle, konfigurowalny z poziomu caveweb (kafelek
Konfiguracja -> /settings) bez przepisywania jednostki systemd. Ustawienia
czytane z JSON pod ścieżką poniżej (ta sama, której używa caveweb/config.py -
patrz tam komentarz).

`swayidle` sam zawsze działa, z `timeout` wziętym z ustawień w chwili startu -
to jedyna wartość "wypieczona" w argumentach procesu, więc tylko jej zmiana
wymaga restartu usługi (caveweb robi to sam po zapisaniu /settings, patrz
`pages/settings.py::confirm`). `enabled` i `restart_wayvnc_on_wake` są
czytane na nowo przy KAŻDYM zdarzeniu (`--off`/`--resume` niżej), więc
przełączenie ich w UI działa od razu, bez restartu czegokolwiek - stąd ten
skrypt wywołuje sam siebie jako polecenia swayidle zamiast gołych `wlr-randr`.

Samodzielny skrypt (bez zależności od pakietu caveweb/nicegui) - prościej go
uruchamiać z dowolnego Pythona bez aktywowania venv, gdyby kiedyś było trzeba.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_SETTINGS_PATH = Path('/home/sqna/cave/logs/screen_idle.json')
OUTPUT = 'HDMI-A-1'
DEFAULTS = {'enabled': True, 'timeout_seconds': 30, 'restart_wayvnc_on_wake': True}


def settings_path() -> Path:
    env = os.environ.get('CAVE_SCREEN_IDLE_SETTINGS')
    return Path(env) if env else DEFAULT_SETTINGS_PATH


def load_settings() -> dict:
    path = settings_path()
    if path.exists():
        try:
            return {**DEFAULTS, **json.loads(path.read_text(encoding='utf-8'))}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def do_off() -> None:
    """Wywoływane przez swayidle po `timeout` - no-op, gdy wygaszacz jest
    aktualnie wyłączony w ustawieniach (sprawdzane na żywo, nie przy starcie)."""
    if load_settings()['enabled']:
        subprocess.run(['wlr-randr', '--output', OUTPUT, '--off'], check=False)


def do_resume() -> None:
    """Wywoływane przez swayidle po wykryciu ruchu - ekran wraca ZAWSZE,
    niezależnie od `enabled`: inaczej dotyk po zmianie ustawienia w trakcie
    wygaszenia zostawiałby ekran czarny bez wyjścia."""
    subprocess.run(['wlr-randr', '--output', OUTPUT, '--on'], check=False)
    if load_settings()['restart_wayvnc_on_wake']:
        subprocess.run(['sudo', '-n', 'systemctl', 'restart', 'wayvnc.service'], check=False)


def main() -> None:
    if len(sys.argv) > 1:
        {'--off': do_off, '--resume': do_resume}[sys.argv[1]]()
        return

    timeout = int(load_settings()['timeout_seconds'])
    python = sys.executable
    script = str(Path(__file__).resolve())
    os.execvp('swayidle', [
        'swayidle', '-w',
        'timeout', str(timeout), f'{python} {script} --off',
        'resume', f'{python} {script} --resume',
    ])


if __name__ == '__main__':
    main()
