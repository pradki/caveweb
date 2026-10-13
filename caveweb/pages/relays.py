# -*- coding: utf-8 -*-
"""Przekaźniki - podgląd i ręczne sterowanie dowolnym kanałem dowolnego
modułu waveshare-mqtt-gateway. Wybór modułu jest tu świadomie pierwszym
krokiem, nie skrótem do jedynego, bo docelowo modułów będzie więcej; tabela
kanałów jest w całości odkrywana z MQTT (patrz `relay_control.py`) - nic tu
nie jest na sztywno wpisane w kodzie caveweb.

Zwykłe wiersze (`ui.row`/`ui.label`), nie `ui.table` - prościej dopiąć
przycisk akcji per wiersz bez szablonów Vue/Quasar, i spójne z resztą
caveweb (`live.render_rows`/`render_device_cards` robią to samo)."""

from __future__ import annotations
__version__ = "0.2"

import time

from nicegui import ui

from .. import relay_control
from ..widgets import number_stepper, page_header

# Czas w dialogu Akcji wpisuje się w jednej z tych jednostek (`duration_unit`
# niżej), ale gateway zawsze dostaje sekundy - stąd ten mnożnik zamiast
# osobnego pola na sekundy, minuty i godziny.
DURATION_UNITS = {'s': 1.0, 'min': 60.0, 'h': 3600.0}


def _state_color(state) -> str:
    if state in ('on', 'flash_on'):
        return '#16a34a'  # zielony
    if state in ('off', None):
        return '#6b7280'  # szary
    return '#d97706'  # flash_off/toggle/nieznane - pomarańczowy


def _format_expiry(expires_at, now: float | None = None) -> str:
    """`expires_at` z `channel_rows()` to już czas ścienny (epoch, patrz
    `relay_control.py`), więc porównanie z `time.time()` jest wprost poprawne.
    Odliczanie, nie data - "za 45 s" czyta się na pierwszy rzut oka szybciej
    niż zegarek, a to i tak odświeża się co 5 s (patrz `ui.timer` niżej)."""
    if expires_at is None:
        return '–'
    now = now if now is not None else time.time()
    remaining = expires_at - now
    if remaining <= 0:
        return 'wygasło'
    if remaining < 90:
        return f'za {remaining:.0f} s'
    if remaining < 3600:
        return f'za {remaining / 60:.0f} min'
    return f'za {remaining / 3600:.1f} h'


@ui.page('/relays')
def relays_page() -> None:
    page_header('Przekaźniki', back=True)

    with ui.column().classes('w-full p-3 gap-3'):
        modules = relay_control.discover_modules()
        empty_label = ui.label(
            'Brak modułów - gateway jeszcze nie opublikował statusu.'
        ).classes('text-sm text-grey-6')
        empty_label.visible = not modules

        module_select = ui.select(modules, value=(modules[0] if modules else None),
                                  label='Moduł').classes('w-64')
        module_select.visible = bool(modules)

        table_container = ui.column().classes('w-full gap-0')

        # Jeden, trwały dialog zamiast tworzenia nowego przy każdym kliknięciu
        # "Akcja" - render_table() co kilka sekund czyści table_container
        # (timer niżej), a dialog stworzony W TRAKCIE obsługi kliknięcia
        # przycisku Z TEJ tabeli dziedziczyłby jej slot jako rodzica, więc
        # znikałby razem z nią przy najbliższym odświeżeniu (obserwowane na
        # żywo: "RuntimeError: parent slot of the element has been deleted",
        # okienko gasło samo po 1-3 s). Dialog żyje poza table_container,
        # więc żadne jej czyszczenie go nie dotyka - klik tylko podmienia,
        # czego dotyczy, i otwiera ten sam dialog na nowo.
        target = {'module': None, 'row': None}
        duration_unit_state = {'value': 's'}  # poprzednia jednostka - do przeliczenia przy zmianie

        with ui.dialog() as dialog, ui.card().classes('gap-2 min-w-80'):
            dialog_title = ui.label('').classes('text-base font-medium')
            cmd_select = ui.select(list(relay_control.CMDS), value='on', label='Akcja') \
                .classes('w-full')
            priority_input = number_stepper('Priorytet', value=relay_control.DEFAULT_PRIORITY,
                                           min=0, step=1, format='%.0f', classes='w-full')
            with ui.row().classes('w-full items-center gap-2 no-wrap'):
                duration_input = number_stepper('Czas', value=relay_control.DEFAULT_DURATION,
                                               min=1, step=1, format='%.0f', classes='flex-grow')
                duration_unit = ui.select(list(DURATION_UNITS), value='s', label='Jedn.') \
                    .classes('w-20 shrink-0')
            duration_hint = ui.label('').classes('text-xs text-grey-6')

            def update_hint() -> None:
                duration_hint.text = (
                    'Czas trwania sprzętowego impulsu' if cmd_select.value == 'flash_on'
                    else 'TTL - jak długo trzymać, zanim trzeba odnowić')

            def on_unit_change(e) -> None:
                # Przelicza wpisaną liczbę tak, żeby reprezentowała ten sam
                # czas w nowej jednostce - inaczej "60" zamienione z sekund na
                # godziny po cichu zmieniłoby czas 60x, nie tylko etykietę.
                old_seconds = (duration_input.value or 0) * DURATION_UNITS[duration_unit_state['value']]
                duration_unit_state['value'] = e.value
                duration_input.value = round(old_seconds / DURATION_UNITS[e.value], 3)

            cmd_select.on_value_change(lambda: update_hint())
            duration_unit.on_value_change(on_unit_change)

            def confirm() -> None:
                cmd = cmd_select.value
                priority = int(priority_input.value or 0)
                raw = duration_input.value
                seconds = (relay_control.DEFAULT_DURATION if not raw
                          else float(raw) * DURATION_UNITS[duration_unit.value])
                kwargs = ({'duration': seconds} if cmd == 'flash_on' else {'ttl': seconds})
                ok, message = relay_control.send_command(
                    target['module'], target['row']['name'], cmd, priority, **kwargs)
                ui.notify(message, type='positive' if ok else 'warning')
                dialog.close()
                render_table()

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Anuluj', on_click=dialog.close).props('flat')
                ui.button('Wyślij', icon='send', on_click=confirm).props('color=primary')

        def open_action_dialog(module: str, row: dict) -> None:
            target['module'] = module
            target['row'] = row
            dialog_title.text = f'{row["name"]} (kanał {row["channel"]})'
            cmd_select.value = 'on'
            priority_input.value = relay_control.DEFAULT_PRIORITY
            duration_input.value = relay_control.DEFAULT_DURATION
            duration_unit.value = 's'
            duration_unit_state['value'] = 's'
            update_hint()
            dialog.open()

        def render_table() -> None:
            table_container.clear()
            module = module_select.value
            if not module:
                return
            rows = relay_control.channel_rows(module)
            with table_container:
                with ui.row().classes('w-full items-center gap-2 text-xs text-grey-5 '
                                      'font-medium px-2 pb-1'):
                    ui.label('Nr').classes('w-10')
                    ui.label('Nazwa').classes('w-44')
                    ui.label('Stan').classes('w-24')
                    ui.label('By').classes('w-32')
                    ui.label('Priorytet').classes('w-20')
                    ui.label('Wygasa').classes('w-24')
                    ui.label('')
                for row in rows:
                    with ui.row().classes('w-full items-center gap-2 px-2 py-1 border-t '
                                          'border-grey-800'):
                        ui.label(str(row['channel'])).classes('w-10')
                        ui.label(row['name']).classes('w-44')
                        ui.label(row['state'] or '–') \
                            .classes('w-24').style(f'color: {_state_color(row["state"])}')
                        ui.label(row['by'] or '–').classes('w-32 text-grey-6')
                        ui.label('–' if row['priority'] is None else str(row['priority'])) \
                            .classes('w-20')
                        ui.label(_format_expiry(row['expires_at'])).classes('w-24 text-grey-6')
                        ui.button('Akcja', icon='tune',
                                 on_click=lambda r=row, m=module: open_action_dialog(m, r)) \
                            .props('dense flat')
                if not rows:
                    ui.label('Moduł jeszcze nie opublikował liczby kanałów.') \
                        .classes('text-sm text-grey-6 px-2')

        module_select.on_value_change(lambda: render_table())
        render_table()
        ui.timer(5.0, render_table)
