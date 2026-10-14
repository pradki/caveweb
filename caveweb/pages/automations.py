# -*- coding: utf-8 -*-
"""Automatyzacje – małe, niezależne zadania z `cave-service-manager` (osobne
repo - integracja tylko przez MQTT), każde obserwujące parę
czujników/nastaw i włączające jakiś przekaźnik, gdy jego własny warunek jest
spełniony (dziś: wszystkie trzy współdzielą pompę pieca `co_pump_boiler`).

`TASKS` niżej to KOPIA metadanych z tamtego repo (`tasks/*.py` - NAME/LABEL/
DESC/CONFIG), tak samo jak `heating_params.py` jest kopią `PARAMS_HEATING` z
heating-controller - caveweb nie importuje tamtego kodu (osobne repo, tylko
MQTT), więc nowe zadanie tam = ręczna aktualizacja tej listy tutaj."""

from __future__ import annotations
__version__ = "0.1"

import json

from nicegui import ui

from .. import live, mqttclient
from ..widgets import number_stepper, page_header

STATUS_ROOT = 'cave/service-manager'

# (nazwa, etykieta, opis, [(klucz, etykieta, typ, min, max, domyślna, jednostka, krok), ...])
TASKS = [
    ('buffer_top_redistribute', 'Bufor góra',
     'Gdy góra bufora przekroczy próg, włącza pompę pieca, żeby rozprowadzić '
     'ciepło na niższe warstwy zamiast grzać tylko górną partię.',
     [('threshold', 'Próg', 'float', 40.0, 90.0, 65.0, '°C', 1)]),
    ('furnace_overheat_protect', 'Przegrzanie pieca',
     'Gdy piec przekroczy zadaną o margines (typowo zaraz po dorzuceniu drewna), '
     'włącza pompę, żeby odprowadzić nadmiar do bufora.',
     [('margin', 'Margines', 'float', 0.0, 30.0, 10.0, '°C', 1)]),
    ('cwu_reserve_protect', 'Rezerwa CWU',
     'Gdy oba górne czujniki bufora spadną poniżej minimum, a piec ma jeszcze '
     'czym grzać, włącza pompę, żeby dogrzać górę bufora (rezerwę CWU).',
     [('furnace_min', 'Piec min.', 'float', 30.0, 80.0, 55.0, '°C', 1),
      ('reserve_min', 'Rezerwa min.', 'float', 30.0, 70.0, 45.0, '°C', 1)]),
]


def status_topic(name: str) -> str:
    return f'{STATUS_ROOT}/tasks/{name}/status'


def setpoint_topic(name: str, key: str) -> str:
    return f'{STATUS_ROOT}/tasks/{name}/setpoints/{key}'


def clamp_config_value(data_type: str, min_v: float, max_v: float, value) -> int | float:
    """Przycięcie do typu i zakresu - ten sam powód co boiler_config/comfort:
    usługa, która dostanie wartość spoza zakresu, nie przytnie jej sama,
    tylko zresetuje do swojego configu."""
    value = max(min_v, min(max_v, float(value)))
    return int(round(value)) if data_type == 'int' else value


def _config_summary(name: str, fields: list) -> str:
    """Skrócona konfiguracja do kolumny tabeli - aktualne wartości z własnego
    statusu zadania (to, co ono faktycznie używa), nie z tego, co ostatnio
    wysłaliśmy - różnica ma znaczenie, gdyby ktoś zmienił coś z innego miejsca."""
    status = mqttclient.cache.value(status_topic(name), 'config')
    if not isinstance(status, dict):
        return '–'
    parts = []
    for key, label, _data_type, _min_v, _max_v, _default, unit, _step in fields:
        value = status.get(key)
        parts.append(f'{label}: –' if value is None else f'{label}: {value:.0f}{unit}')
    return ' · '.join(parts)


@ui.page('/automations')
def automations() -> None:
    page_header('Automatyzacje', back=True)

    with ui.column().classes('w-full p-3 gap-3'):
        ui.label('Każde zadanie obserwuje własne czujniki/nastawy i włącza pompę pieca, '
                 'gdy jego warunek jest spełniony - niezależnie od pozostałych.') \
            .classes('text-xs text-grey-7')

        table_container = ui.column().classes('w-full gap-0')

        # Jeden, trwały dialog (patrz /relays - render_table() niżej czyści
        # table_container co kilka sekund; dialog stworzony W TRAKCIE obsługi
        # kliknięcia Z TEJ tabeli dziedziczyłby jej slot jako rodzica i
        # znikałby przy najbliższym odświeżeniu).
        target = {'name': None, 'fields': None}
        inputs = {}

        with ui.dialog() as dialog, ui.card().classes('gap-2 min-w-80'):
            dialog_title = ui.label('').classes('text-base font-medium')
            dialog_fields = ui.column().classes('w-full gap-1')

            def save() -> None:
                name = target['name']
                sent = 0
                for key, _label, data_type, min_v, max_v, _default, _unit, _step in target['fields']:
                    widget = inputs.get(key)
                    if widget is None or widget.value is None:
                        continue
                    value = clamp_config_value(data_type, min_v, max_v, widget.value)
                    mqttclient.publish(setpoint_topic(name, key), json.dumps({'value': value}),
                                      qos=0, retain=True)
                    sent += 1
                ui.notify(f'Wysłano {sent} nastaw do cave-service-manager', type='positive')
                dialog.close()

            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('Anuluj', on_click=dialog.close).props('flat')
                ui.button('Zapisz', icon='save', on_click=save).props('color=primary')

        def open_edit_dialog(name: str, label: str, fields: list) -> None:
            target['name'] = name
            target['fields'] = fields
            dialog_title.text = label
            dialog_fields.clear()
            inputs.clear()
            status = mqttclient.cache.value(status_topic(name), 'config')
            current = status if isinstance(status, dict) else {}
            with dialog_fields:
                for key, field_label, data_type, min_v, max_v, default, unit, step in fields:
                    value = current.get(key, default)
                    digits = 0 if float(step).is_integer() else 1
                    with ui.row().classes('w-full items-center gap-2 no-wrap'):
                        ui.label(field_label).classes('text-sm w-28')
                        inputs[key] = number_stepper(
                            value=value, min=min_v, max=max_v, step=step,
                            suffix=unit or None, format=f'%.{digits}f', classes='flex-grow')
            dialog.open()

        def set_enabled(name: str, value: bool) -> None:
            mqttclient.publish(setpoint_topic(name, 'enabled'), json.dumps({'value': value}),
                              qos=0, retain=True)

        def render_table() -> None:
            table_container.clear()
            with table_container:
                with ui.row().classes('w-full items-center gap-2 text-xs text-grey-5 '
                                      'font-medium px-2 pb-1'):
                    ui.label('Wł.').classes('w-12')
                    ui.label('Zadanie').classes('w-40')
                    ui.label('Status').classes('flex-grow')
                    ui.label('Konfiguracja').classes('w-64')
                    ui.label('')
                for name, label, desc, fields in TASKS:
                    enabled = mqttclient.cache.value(status_topic(name), 'enabled')
                    triggered = mqttclient.cache.value(status_topic(name), 'triggered')
                    reason = mqttclient.cache.value(status_topic(name), 'reason') or '–'
                    driving = bool(enabled) and bool(triggered)
                    color = '#16a34a' if driving else ('#6b7280' if enabled else '#dc2626')
                    with ui.row().classes('w-full items-center gap-2 px-2 py-1 border-t '
                                          'border-grey-800'):
                        ui.switch(value=bool(enabled),
                                 on_change=lambda e, n=name: set_enabled(n, e.value)) \
                            .classes('w-12').tooltip('Włącz/wyłącz to zadanie')
                        ui.label(label).classes('w-40')
                        ui.label(reason).classes('flex-grow text-sm').style(f'color: {color}')
                        ui.label(_config_summary(name, fields)).classes('w-64 text-xs text-grey-6')
                        with ui.row().classes('items-center gap-1 no-wrap'):
                            ui.button(icon='tune', on_click=lambda n=name, lbl=label, f=fields:
                                     open_edit_dialog(n, lbl, f)).props('dense flat')
                            ui.icon('info', size='18px').classes('text-grey-6').tooltip(desc)

        render_table()
        ui.timer(5.0, render_table)
    live.mqtt_status_label()
