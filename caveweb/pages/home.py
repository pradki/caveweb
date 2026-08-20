"""Ekran główny – kafelki najwyższego poziomu z wartościami bieżącymi."""

from __future__ import annotations
__version__ = "0.2"

from nicegui import ui

from .. import live, topics
from ..widgets import page_header, tile, tile_grid

# Wartości pokazywane wprost na kafelkach - tyle, żeby jednym spojrzeniem
# wiedzieć, czy warto wchodzić głębiej.
BOILER_TILE = [
    live.value_of('piec', topics.sensor('furnace_temp'), unit='°C', digits=1),
]

PV_TILE = [
    live.sum_of('moc PV', [topics.deye('pv1_power'), topics.deye('pv2_power')],
                unit='W', digits=0),
    live.value_of('bateria', topics.deye('battery_soc'), unit='%', digits=0),
    live.sum_of('obciążenie', [topics.deye('load_power_l1'),
                               topics.deye('load_power_l2'),
                               topics.deye('load_power_l3')], unit='W', digits=0),
]


@ui.page('/home')
def home() -> None:
    page_header('cave')

    boiler = live.LivePanel(BOILER_TILE)
    pv = live.LivePanel(PV_TILE)

    with tile_grid():
        tile('insert_chart', 'Wykresy', target='/charts',
             subtitle='temperatury, moc, energia')
        tile('local_fire_department', 'Kocioł CO', target='/boiler',
             body=boiler.render_compact)
        tile('solar_power', 'PV', target='/pv', body=pv.render_compact)
        tile('blinds', 'Rolety', subtitle='w przygotowaniu',
             on_click=lambda: ui.notify('Sterowanie roletami – wkrótce'))
        tile('water_drop', 'Nawadnianie', subtitle='w przygotowaniu',
             on_click=lambda: ui.notify('Nawadnianie ogrodu – wkrótce'))

    boiler.start()
    pv.start()
    live.mqtt_status_label()
