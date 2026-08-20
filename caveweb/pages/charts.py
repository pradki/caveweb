"""Kafelki wykresów – wybór grupy sygnałów."""

from __future__ import annotations

__version__ = "0.2"

from nicegui import ui

from ..widgets import page_header, tile, tile_grid


@ui.page('/charts')
def charts() -> None:
    page_header('Wykresy', back='/home')
    with tile_grid():
        tile('thermostat', 'Temperatury', target='/charts/temperature',
             subtitle='wewnątrz / zewnątrz')
        tile('battery_charging_full', 'Bateria', target='/charts/battery',
             subtitle='SOC / ładowanie')
        tile('bolt', 'Moc', target='/charts/power',
             subtitle='PV / obciążenie faz')
        tile('electric_meter', 'Energia', target='/charts/energy',
             subtitle='zużycie')
