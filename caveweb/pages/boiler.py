"""Kocioł CO – bieżące parametry i wejście do konfiguracji.

Czujniki i nastawy bierzemy z metadanych `heating_params` (kopia
PARAMS_HEATING), więc nazwy, jednostki i topiki są zawsze te same co w usłudze
grzewczej. Doszły do tego bufor, temperatura w domu i czas pracy dmuchawy oraz
podajnika z liczników bramy przekaźników.
"""

from __future__ import annotations
__version__ = "0.1"

from nicegui import ui

from .. import heating_params, live, topics
from ..widgets import page_header, section


def param(name: str, label: str, **kwargs) -> live.Value:
    """Wartość z metadanych parametru usługi grzewczej."""
    meta = heating_params.PARAMS[name]
    kind = 'bool' if meta['data_type'] == 'bool' else 'number'
    digits = 0 if meta['data_type'] in ('int', 'bool') else 1
    return live.value_of(label, meta['topic'], unit=meta['unit'],
                         digits=kwargs.pop('digits', digits),
                         kind=kwargs.pop('kind', kind),
                         desc=kwargs.pop('desc', ''), **kwargs)


# Sam kocioł - to, po czym poznaje się, co się w nim dzieje
FURNACE = [
    param('furnace_temp_sensor', 'Piec', icon='local_fire_department'),
    param('flue_gas_temp_sensor', 'Spaliny', icon='air'),
    param('feeder_temp_sensor', 'Podajnik', icon='conveyor_belt'),
    param('return_water_temp_sensor', 'Powrót', icon='u_turn_left'),
    param('dhw_temp_sensor', 'CWU', icon='shower'),
    param('return_fireplace_temp_sensor', 'Powrót kominka', icon='fireplace'),
]

# Gdzie to ciepło trafia
HOUSE = [
    live.value_of('Bufor góra', topics.sensor('buff_top_temp'), unit='°C', icon='vertical_align_top'),
    live.value_of('Bufor dół', topics.sensor('buff_bot_temp'), unit='°C', icon='vertical_align_bottom'),
    live.value_of('Wewnątrz', topics.sensor('inside_temp'), unit='°C', icon='home'),
    live.value_of('Zewnątrz', topics.sensor('outside_temp'), unit='°C', icon='thermostat'),
]

# Praca urządzeń: total i dziś z licznika bramy przekaźników (today_s/total_s
# z cave/relay/relay_heating/<alias>/counters), jedna karta na urządzenie -
# patrz DEVICES niżej, które paruje total+dziś pod wspólnym tytułem/ikoną.
WORK = [
    live.value_of('Dmuchawa total', topics.relay_counters('co_fan'), kind='duration',
                  key='total_s', columns=()),
    live.value_of('Dmuchawa dziś', topics.relay_counters('co_fan'), kind='duration',
                  key='today_s', columns=()),
    live.value_of('Podajnik total', topics.relay_counters('co_feeder'), kind='duration',
                  key='total_s', columns=()),
    live.value_of('Podajnik dziś', topics.relay_counters('co_feeder'), kind='duration',
                  key='today_s', columns=()),
]

# (tytuł, ikona, [(podpis, spec), ...]) - karty w render_device_cards
DEVICES = [
    ('Dmuchawa', 'mode_fan', [('total', WORK[0]), ('dziś', WORK[1])]),
    ('Podajnik', 'conveyor_belt', [('total', WORK[2]), ('dziś', WORK[3])]),
]

# Najważniejsze nastawy - pełna lista jest na stronie konfiguracji
KEY_SETPOINTS = [
    param('furnace_enable_setpoint', 'Sterownik'),
    param('furnace_temp_setpoint', 'Nastawa pieca'),
    param('inside_temp_setpoint', 'Nastawa w domu'),
    param('fan_speed_setpoint', 'Dmuchawa'),
    param('feeding_time_setpoint', 'Czas karmienia'),
    param('pause_time_setpoint', 'Czas pauzy'),
    param('flue_gas_temp_setpoint', 'Nastawa spalin'),
    param('dhw_temp_setpoint', 'Nastawa CWU'),
]


@ui.page('/boiler')
def boiler() -> None:
    page_header('Kocioł CO', back='/home')

    panels = []
    with ui.column().classes('w-full p-3 gap-2'):
        with ui.row().classes('w-full items-center gap-2'):
            ui.button('Konfiguracja', icon='settings',
                      on_click=lambda: ui.navigate.to('/boiler/config')).props('outline')
            ui.button('Tankowanie', icon='local_shipping',
                      on_click=lambda: ui.navigate.to('/boiler/refuel')).props('outline')
            ui.button('Wykres temperatur', icon='show_chart',
                      on_click=lambda: ui.navigate.to('/charts/temperature')).props('flat')

        for title, values in (('Kocioł', FURNACE), ('Bufor i dom', HOUSE)):
            section(title)
            panel = live.LivePanel(values)
            panel.render_cards()
            panels.append(panel)

        section('Praca urządzeń')
        work_panel = live.LivePanel(WORK)
        work_panel.render_device_cards(DEVICES)
        panels.append(work_panel)

        section('Nastawy')
        setpoints = live.LivePanel(KEY_SETPOINTS)
        setpoints.render_rows()
        panels.append(setpoints)

    for panel in panels:
        panel.start()
    live.mqtt_status_label()
