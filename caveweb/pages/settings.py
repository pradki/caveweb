# -*- coding: utf-8 -*-
"""Konfiguracja kiosku - na razie tylko wygaszacz ekranu
(`screen_idle_runner.py` czyta ten sam plik, patrz tam i w README "Kiosk").
"""

from __future__ import annotations
__version__ = "0.1"

import json
import subprocess

from nicegui import run, ui

from .. import config
from ..widgets import page_header, section

DEFAULTS = {'enabled': True, 'timeout_seconds': 30, 'restart_wayvnc_on_wake': True}


def load() -> dict:
    path = config.SCREEN_IDLE_SETTINGS_PATH
    if path.exists():
        try:
            return {**DEFAULTS, **json.loads(path.read_text(encoding='utf-8'))}
        except (json.JSONDecodeError, OSError):
            pass
    return dict(DEFAULTS)


def save(settings: dict) -> None:
    path = config.SCREEN_IDLE_SETTINGS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding='utf-8')


def restart_screen_idle() -> tuple[bool, str]:
    """Restartuje screen-idle.service - potrzebne TYLKO po zmianie
    `timeout_seconds` (jedyna wartość wypieczona w argumentach startowych
    `swayidle`, patrz `screen_idle_runner.py`). `enabled` i
    `restart_wayvnc_on_wake` ten skrypt czyta na żywo przy każdym zdarzeniu,
    więc nie wymagają restartu w ogóle - patrz `confirm()` niżej.

    Błąd (np. uruchomione na stacji deweloperskiej, bez tej usługi) nie ma być
    fatalny - plik ustawień już jest zapisany, usługa i tak go przeczyta przy
    swoim następnym (re)starcie."""
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'restart', 'screen-idle.service'],
            capture_output=True, text=True, timeout=10, check=False)
        if result.returncode == 0:
            return True, 'Zrestartowano wygaszacz - nowe ustawienia działają od razu.'
        return False, f'Zapisano, ale restart się nie udał: {result.stderr.strip()}'
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, f'Zapisano, ale nie udało się zrestartować usługi: {error}'


@ui.page('/settings')
def settings_page() -> None:
    page_header('Konfiguracja', back='/home')

    current = load()

    with ui.column().classes('w-full p-3 gap-3 max-w-md'):
        section('Wygaszacz ekranu')

        enabled_switch = ui.switch('Wygaszacz ekranu', value=current['enabled']) \
            .classes('w-full')
        timeout_number = ui.number('Czas do wygaszenia (s)',
                                   value=current['timeout_seconds'],
                                   min=5, max=3600, step=5, format='%.0f') \
            .classes('w-full')
        wayvnc_switch = ui.switch('Restart wayvnc przy wybudzeniu',
                                  value=current['restart_wayvnc_on_wake']) \
            .classes('w-full')
        ui.label('Wayvnc czasem traci obraz po wygaszeniu ekranu - restart to '
                 'naprawia, ale nie zawsze jest potrzebny.') \
            .classes('text-xs text-grey-6')

        status = ui.label('').classes('text-xs text-grey-6')

        async def confirm() -> None:
            previous = current
            new_settings = {
                'enabled': enabled_switch.value,
                'timeout_seconds': int(timeout_number.value or DEFAULTS['timeout_seconds']),
                'restart_wayvnc_on_wake': wayvnc_switch.value,
            }
            save(new_settings)
            if new_settings['timeout_seconds'] != previous['timeout_seconds']:
                ok, message = await run.io_bound(restart_screen_idle)
                status.text = message
                ui.notify(message, type='positive' if ok else 'warning')
            else:
                # enabled/restart_wayvnc_on_wake screen_idle_runner.py czyta
                # na żywo przy każdym zdarzeniu - bez restartu usługi.
                status.text = 'Zapisano - działa od razu, bez restartu usługi.'
                ui.notify(status.text, type='positive')

        ui.button('Zapisz', icon='save', on_click=confirm) \
            .props('color=primary').classes('w-full')
