"""Wykres temperatur: inside_temp / outside_temp."""

from __future__ import annotations

__version__ = "0.2"

from nicegui import ui

from ..chartpage import ChartPage, Signal


class TemperaturePage(ChartPage):
    title = 'Temperatury'
    key = 'temp'
    y_axes = [{'name': '°C'}]
    signals = [
        Signal('inside_temp', 'Wewnątrz', '#3DF06C', unit='°C'),
        Signal('outside_temp', 'Zewnątrz', '#DBEB6F', unit='°C'),
        Signal('buff_top_temp', 'bufor', '#F485BD', unit='°C'),
        Signal('furnace_temp', 'piec', '#ED4040', unit='°C'),
    ]


@ui.page('/charts/temperature')
def temperature() -> None:
    TemperaturePage().build()
