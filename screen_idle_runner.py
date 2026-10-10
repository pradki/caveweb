#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wrapper na swayidle, konfigurowalny z poziomu caveweb (kafelek
Konfiguracja -> /settings) bez przepisywania jednostki systemd za każdym
razem ustawienia się zmienią. Ustawienia czytane z JSON pod ścieżką poniżej
(ta sama, której używa caveweb/config.py - patrz tam komentarz); caveweb po
zapisaniu zmiany sam robi `systemctl --user restart screen-idle.service`,
więc nowe ustawienia działają od razu, nie dopiero od następnego rozruchu.

Samodzielny skrypt (bez zależności od pakietu caveweb/nicegui) - prościej go
uruchamiać z dowolnego Pythona bez aktywowania venv, gdyby kiedyś było trzeba.
"""
from __future__ import annotations

import json
import os
import signal
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


def main() -> None:
    settings = load_settings()

    if not settings['enabled']:
        # Wygaszacz wyłączony - usługa ma zostać "aktywna" (systemd nie
        # potraktuje jej jako awarii), ale nic nie robi, dopóki ktoś nie
        # włączy go z powrotem (co i tak restartuje tę usługę).
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        signal.pause()
        return

    resume_cmd = f'wlr-randr --output {OUTPUT} --on'
    if settings['restart_wayvnc_on_wake']:
        resume_cmd += '; sudo -n systemctl restart wayvnc.service'

    os.execvp('swayidle', [
        'swayidle', '-w',
        'timeout', str(int(settings['timeout_seconds'])),
        f'wlr-randr --output {OUTPUT} --off',
        'resume', resume_cmd,
    ])


if __name__ == '__main__':
    main()
