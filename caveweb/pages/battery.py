"""Wykres baterii: SOC oraz energia ładowania / rozładowania."""

from __future__ import annotations

__version__ = "0.1"

from nicegui import ui

from ..chartpage import COUNTER, ChartPage, Signal


class BatteryPage(ChartPage):
    title = 'Bateria'
    key = 'battery'
    # Oś lewa: stan ładowania w procentach, oś prawa: energia w kubetku
    y_axes = [
        {'name': '%', 'min': 0, 'max': 100},
        {'name': 'kWh'},
    ]
    signals = [
        Signal('battery_soc', 'SOC', '#81c784', unit='%'),
        # Rozładowanie rysujemy pod osią (sign=-1), żeby słupki się nie nakładały
        Signal('battery_charge_total', 'Ładowanie', '#66bb6a',
               kind=COUNTER, unit='kWh', axis=1),
        Signal('battery_discharge_total', 'Rozładowanie', '#ef5350',
               kind=COUNTER, unit='kWh', axis=1, sign=-1),
    ]


@ui.page('/charts/battery')
def battery() -> None:
    BatteryPage().build()
