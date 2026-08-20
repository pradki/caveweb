"""PV – bieżące parametry falownika: produkcja, bateria, obciążenie."""

from __future__ import annotations
__version__ = "0.1"

from nicegui import ui

from .. import live, topics
from ..widgets import page_header, section

PV_TOPICS = [topics.deye('pv1_power'), topics.deye('pv2_power')]
LOAD_TOPICS = [topics.deye('load_power_l1'), topics.deye('load_power_l2'),
               topics.deye('load_power_l3')]

# Produkcja: suma i osobno każdy string, żeby było widać, gdy jeden odstaje
PRODUCTION = [
    live.sum_of('Moc PV', PV_TOPICS, unit='W', digits=0, icon='solar_power'),
    live.value_of('PV1', topics.deye('pv1_power'), unit='W', digits=0),
    live.value_of('PV2', topics.deye('pv2_power'), unit='W', digits=0),
]

# Bateria: stan i znak mocy (dodatnia = ładowanie, ujemna = rozładowanie)
BATTERY = [
    live.value_of('Bateria SOC', topics.deye('battery_soc'), unit='%', digits=0,
                  icon='battery_charging_full'),
    live.value_of('Moc baterii', topics.deye('battery_power'), unit='W', digits=0,
                  icon='bolt', desc='dodatnia = ładowanie'),
]

# Zużycie: suma i rozbicie na fazy
LOAD = [
    live.sum_of('Obciążenie', LOAD_TOPICS, unit='W', digits=0, icon='power'),
    live.value_of('L1', topics.deye('load_power_l1'), unit='W', digits=0),
    live.value_of('L2', topics.deye('load_power_l2'), unit='W', digits=0),
    live.value_of('L3', topics.deye('load_power_l3'), unit='W', digits=0),
]

# Liczniki dobowe i całkowite falownika. W bazie metriki liczniki nie mają
# kolumny _avg, więc awaryjne źródło wskazujemy wprost jako _end.
TODAY = [
    live.value_of('Naładowano dziś', topics.deye('battery_charge_today'),
                  unit='kWh', digits=1, columns=('battery_charge_today_end',),
                  icon='battery_5_bar'),
    live.value_of('Oddano dziś', topics.deye('battery_discharge_today'),
                  unit='kWh', digits=1, columns=('battery_discharge_today_end',),
                  icon='battery_2_bar'),
    live.value_of('Licznik zużycia', topics.deye('load_energy_total'),
                  unit='kWh', digits=1, columns=('load_energy_total_end',),
                  icon='electric_meter', desc='od uruchomienia falownika'),
]


@ui.page('/pv')
def pv() -> None:
    page_header('PV', back='/home')

    panels = []
    with ui.column().classes('w-full p-3 gap-2'):
        with ui.row().classes('w-full items-center gap-2'):
            ui.button('Wykres mocy', icon='show_chart',
                      on_click=lambda: ui.navigate.to('/charts/power')).props('outline')
            ui.button('Wykres baterii', icon='battery_charging_full',
                      on_click=lambda: ui.navigate.to('/charts/battery')).props('flat')
            ui.button('Wykres energii', icon='electric_meter',
                      on_click=lambda: ui.navigate.to('/charts/energy')).props('flat')

        for title, values in (('Produkcja', PRODUCTION), ('Bateria', BATTERY),
                              ('Obciążenie', LOAD), ('Dziś', TODAY)):
            section(title)
            panel = live.LivePanel(values)
            panel.render_cards()
            panels.append(panel)

    for panel in panels:
        panel.start()
    live.mqtt_status_label()
