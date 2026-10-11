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
__version__ = "0.1"

from nicegui import ui

from .. import relay_control
from ..widgets import page_header


def _state_color(state) -> str:
    if state in ('on', 'flash_on'):
        return '#16a34a'  # zielony
    if state in ('off', None):
        return '#6b7280'  # szary
    return '#d97706'  # flash_off/toggle/nieznane - pomarańczowy


@ui.page('/relays')
def relays_page() -> None:
    page_header('Przekaźniki', back='/home')

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

        def open_action_dialog(module: str, row: dict) -> None:
            with ui.dialog() as dialog, ui.card().classes('gap-2 min-w-80'):
                ui.label(f'{row["name"]} (kanał {row["channel"]})').classes('text-base font-medium')
                cmd_select = ui.select(list(relay_control.CMDS), value='on', label='Akcja') \
                    .classes('w-full')
                priority_input = ui.number('Priorytet', value=relay_control.DEFAULT_PRIORITY,
                                           min=0, step=1, format='%.0f').classes('w-full')
                duration_input = ui.number('Czas (s)', value=relay_control.DEFAULT_DURATION,
                                           min=1, step=1, format='%.0f').classes('w-full')
                duration_hint = ui.label('').classes('text-xs text-grey-6')

                def update_hint() -> None:
                    duration_hint.text = (
                        'Czas trwania sprzętowego impulsu' if cmd_select.value == 'flash_on'
                        else 'TTL - jak długo trzymać, zanim trzeba odnowić')

                cmd_select.on_value_change(lambda: update_hint())
                update_hint()

                def confirm() -> None:
                    cmd = cmd_select.value
                    priority = int(priority_input.value or 0)
                    seconds = float(duration_input.value or relay_control.DEFAULT_DURATION)
                    kwargs = ({'duration': seconds} if cmd == 'flash_on' else {'ttl': seconds})
                    ok, message = relay_control.send_command(module, row['name'], cmd,
                                                             priority, **kwargs)
                    ui.notify(message, type='positive' if ok else 'warning')
                    dialog.close()
                    render_table()

                with ui.row().classes('w-full justify-end gap-2'):
                    ui.button('Anuluj', on_click=dialog.close).props('flat')
                    ui.button('Wyślij', icon='send', on_click=confirm).props('color=primary')
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
                        ui.button('Akcja', icon='tune',
                                 on_click=lambda r=row, m=module: open_action_dialog(m, r)) \
                            .props('dense flat')
                if not rows:
                    ui.label('Moduł jeszcze nie opublikował liczby kanałów.') \
                        .classes('text-sm text-grey-6 px-2')

        module_select.on_value_change(lambda: render_table())
        render_table()
        ui.timer(5.0, render_table)
