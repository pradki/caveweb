"""Wykres energii: zużycie z licznika load_energy_total."""

from __future__ import annotations

__version__ = "0.1"

from nicegui import ui

from ..chartpage import COUNTER, ChartPage, Signal


class EnergyPage(ChartPage):
    title = 'Energia'
    key = 'energy'
    y_axes = [{'name': 'kWh'}]
    has_minmax = False  # licznik ma tylko przyrost, nie ma min/max
    signals = [
        Signal('load_energy_total', 'Zużycie', '#4dd0e1',
               kind=COUNTER, unit='kWh'),
    ]


@ui.page('/charts/energy')
def energy() -> None:
    EnergyPage().build()
