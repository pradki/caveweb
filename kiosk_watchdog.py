#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watchdog pierwszych 5 minut po starcie systemu.

Obserwowany problem: po resecie Raspberry Pi zdarzało się, że kiosk (Chromium)
wstawał w złym stanie - ekran zgaszony, dotyk nieresponsywny - prawdopodobnie
dlatego, że appka/sesja graficzna startowała, zanim wszystko (wayland,
wlr-randr, urządzenia wejścia) było w pełni gotowe.

Ten skrypt czeka do TIMEOUT_SECONDS (domyślnie 300 = 5 minut) na JAKĄKOLWIEK
aktywność wejścia (przez swayidle - ten sam mechanizm co screen_idle_runner.py).
Jeśli nic się nie wydarzy w tym czasie: wymuszamy ekran ON i restartujemy
caveweb-kiosk.service (systemd od nowa odpala Chromium na czysto).

Robimy to TYLKO RAZ na rozruch systemu: znacznik w XDG_RUNTIME_DIR (tmpfs,
czyszczone przy każdym restarcie) pilnuje, żeby kolejne uruchomienie tej
usługi (np. po tym, jak sama zrestartowała kiosk) nic już nie robiło - stąd
nie ma ryzyka nieskończonej pętli restartów, gdyby problem był czymś innym.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

TIMEOUT_SECONDS = 300
OUTPUT = 'HDMI-A-1'
POLL_INTERVAL = 1.0


def marker_path() -> Path:
    runtime_dir = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}'))
    return runtime_dir / 'kiosk-watchdog-done'


def had_activity_within(timeout_seconds: float) -> bool:
    """True, jeśli swayidle zarejestrowało jakąkolwiek aktywność (resume)
    zanim minął `timeout_seconds` bez żadnej (timeout) - w przeciwnym razie
    False. swayidle samo w sobie działa w nieskończonej pętli, więc to my
    musimy je zabić, gdy któryś z dwóch wyników już wiadomy."""
    with tempfile.TemporaryDirectory() as tmp:
        activity_flag = Path(tmp) / 'activity'
        timeout_flag = Path(tmp) / 'timeout'
        proc = subprocess.Popen([
            'swayidle', '-w',
            'timeout', str(int(timeout_seconds)), f'touch {timeout_flag}',
            'resume', f'touch {activity_flag}',
        ])
        try:
            deadline = time.monotonic() + timeout_seconds + 10  # margines na swayidle samo
            while time.monotonic() < deadline:
                if activity_flag.exists():
                    return True
                if timeout_flag.exists():
                    return False
                if proc.poll() is not None:
                    return False  # swayidle padło - traktujemy jak brak aktywności
                time.sleep(POLL_INTERVAL)
            return False
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def force_recover() -> None:
    subprocess.run(['wlr-randr', '--output', OUTPUT, '--on'], check=False)
    subprocess.run(['systemctl', '--user', 'restart', 'caveweb-kiosk.service'], check=False)


def main() -> None:
    marker = marker_path()
    if marker.exists():
        sys.exit(0)  # już sprawdzone przy tym rozruchu
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()  # zaznacz od razu, zanim zaczniemy czekać

    if had_activity_within(TIMEOUT_SECONDS):
        return  # sesja żyje, nic do zrobienia

    force_recover()


if __name__ == '__main__':
    main()
