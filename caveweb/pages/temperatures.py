# -*- coding: utf-8 -*-
"""Czujniki temperatur – tabela na żywo z wyborem do wykresu.

Zaznaczenie przechowujemy w `app.storage.user`, tym samym mechanizmem co
`ChartPage` swoje przełączniki (patrz `chartpage.py`) – więc nie trzeba za
każdym razem klikać od nowa, które sygnały interesują.
"""

from __future__ import annotations
__version__ = "0.1"

from nicegui import app, ui

from .. import live, topics
from ..chartpage import ChartPage, Signal
from ..widgets import page_header

# (nazwa w topicu, etykieta) – kolejność ustala kolejność wierszy i kolorów
SENSORS = [
    ('outside_temp', 'Zewnątrz'),
    ('inside_temp', 'Wewnątrz'),
    ('floor_temp', 'Podłoga'),
    ('furnace_temp', 'Piec'),
    ('buff_top_temp', 'Bufor góra'),
    ('buff_upmid_temp', 'Bufor środek góra'),
    ('buff_lowmid_temp', 'Bufor środek dół'),
    ('buff_bot_temp', 'Bufor dół'),
    ('return_water_temp', 'Powrót'),
    ('feeder_temp', 'Podajnik'),
]
LABELS = dict(SENSORS)

# Kolory serii na wykresie – powtarzają się dopiero po wyczerpaniu listy
COLORS = ['#3DF06C', '#DBEB6F', '#6FD8EB', '#ED4040', '#F485BD',
          '#F0A63D', '#6F8FEB', '#C56FEB', '#6FEBC2', '#EB6F6F']

STORAGE_KEY = 'temperatures_selected'


@ui.page('/temperatures')
def temperatures() -> None:
    page_header('Temperatury', back='/home')

    selected = set(app.storage.user.get(STORAGE_KEY, []))

    def on_toggle(name: str, value: bool) -> None:
        if value:
            selected.add(name)
        else:
            selected.discard(name)
        app.storage.user[STORAGE_KEY] = list(selected)

    def show_chart() -> None:
        if not selected:
            ui.notify('Zaznacz co najmniej jeden parametr')
            return
        names = ','.join(name for name, _ in SENSORS if name in selected)
        ui.navigate.to(f'/temperatures/chart?params={names}')

    values = [live.value_of(label, topics.sensor(name), unit='°C', digits=1)
              for name, label in SENSORS]
    panel = live.LivePanel(values)

    with ui.column().classes('w-full p-3 gap-2'):
        ui.button('Pokaż na wykresie', icon='show_chart', on_click=show_chart) \
            .props('color=primary')

        with ui.column().classes('w-full gap-0'):
            for (name, label), spec in zip(SENSORS, values):
                with ui.row().classes(
                        'w-full items-center gap-3 py-1 border-b border-grey-8'):
                    ui.checkbox(value=name in selected,
                               on_change=lambda e, n=name: on_toggle(n, e.value))
                    ui.label(label).classes('text-sm w-48')
                    value_label = ui.label('–').classes('text-sm font-medium')
                    panel.bind(spec.label, value_label)

    panel.start()
    live.mqtt_status_label()


class TemperaturesChartPage(ChartPage):
    title = 'Temperatury'
    back = '/temperatures'
    key = 'temperatures'
    y_axes = [{'name': '°C'}]


@ui.page('/temperatures/chart')
def temperatures_chart(params: str = '') -> None:
    names = [name for name in params.split(',') if name in LABELS]
    page = TemperaturesChartPage()
    page.signals = [Signal(name, LABELS[name], COLORS[i % len(COLORS)], unit='°C')
                    for i, name in enumerate(names)]
    page.build()
