"""Ekran główny – kafelki najwyższego poziomu z wartościami bieżącymi."""

from __future__ import annotations
__version__ = "0.2"

from nicegui import ui

from .. import fuel_level, live, topics
from ..widgets import page_header, tile, tile_grid

# Wartości pokazywane wprost na kafelkach - tyle, żeby jednym spojrzeniem
# wiedzieć, czy warto wchodzić głębiej.
BOILER_TILE = [
    live.value_of('piec', topics.sensor('furnace_temp'), unit='°C', digits=1),
]

TEMPERATURES_TILE = [
    live.value_of('zewnątrz', topics.sensor('outside_temp'), unit='°C', digits=1),
    live.value_of('wewnątrz', topics.sensor('inside_temp'), unit='°C', digits=1),
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
    page_header('cave', right=live.clock_label)

    boiler = live.LivePanel(BOILER_TILE)
    pv = live.LivePanel(PV_TILE)
    temperatures = live.LivePanel(TEMPERATURES_TILE)

    def boiler_body() -> None:
        # Jeden wiersz, nie `render_compact` (dwie kolumny z podpisami pod
        # spodem) - inaczej temperatura i węgiel łamią się na dwa rzędy i
        # kafelek rośnie wyżej niż reszta. "~" zamiast podpisów - w jednym
        # wierszu nie ma miejsca na opis, pełne wyjaśnienie w tooltipach.
        # Dwie liczby: ile węgla poszło dziś DO TEJ PORY -> ile pójdzie
        # szacunkowo przez CAŁĄ dobę (ekstrapolacja liniowa z obecnego tempa).
        with ui.row().classes('items-baseline gap-1 justify-center flex-nowrap'):
            temp_label = ui.label('–').classes('text-lg font-medium leading-tight')
            ui.label('·').classes('text-xs text-grey-6')
            live.inline_topic_field(fuel_level.TOPIC, 'today_energy_kwh', prefix='~') \
                .tooltip('Zużycie węgla dzisiaj do tej pory')
            ui.label('→').classes('text-xs text-grey-6')
            live.inline_topic_field(fuel_level.TOPIC, 'projected_daily_kwh',
                                    prefix='~', suffix='kWh', digits=0) \
                .tooltip('Szacowane zużycie całej doby (z dzisiejszego tempa)')
        boiler.bind('piec', temp_label)

    with tile_grid():
        tile('insert_chart', 'Wykresy', target='/charts',
             subtitle='temperatury, moc, energia')
        tile('local_fire_department', 'Kocioł CO', target='/boiler',
             header_body=lambda: live.live_fuel_indicator(fuel_level.TOPIC),
             body=boiler_body)
        tile('solar_power', 'PV', target='/pv',
             header_body=pv.render_header_value,
             body=lambda: pv.render_compact(skip=1))
        tile('thermostat', 'Temperatury', target='/temperatures',
             body=temperatures.render_compact)
        tile('blinds', 'Rolety', subtitle='w przygotowaniu',
             on_click=lambda: ui.notify('Sterowanie roletami – wkrótce'))
        tile('water_drop', 'Nawadnianie', subtitle='w przygotowaniu',
             on_click=lambda: ui.notify('Nawadnianie ogrodu – wkrótce'))
        tile('settings', 'Konfiguracja', target='/settings',
             subtitle='wygaszacz ekranu')

    boiler.start()
    pv.start()
    temperatures.start()
    live.mqtt_status_label()
