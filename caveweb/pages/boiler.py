"""Kocioł CO – bieżące parametry i wejście do konfiguracji.

Czujniki i nastawy bierzemy z metadanych `heating_params` (kopia
PARAMS_HEATING), więc nazwy, jednostki i topiki są zawsze te same co w usłudze
grzewczej. Doszły do tego bufor, temperatura w domu i czas pracy dmuchawy oraz
podajnika z liczników bramy przekaźników.
"""

from __future__ import annotations
__version__ = "0.1"

from datetime import datetime

from nicegui import ui

from .. import fuel_level, furnace_boost, heating_params, live, topics
from ..widgets import number_stepper, page_header, section


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

# Gdzie to ciepło trafia - bufor ma 4 czujniki po wysokości, nie tylko góra/dół
HOUSE = [
    live.value_of('Bufor góra', topics.sensor('buff_top_temp'), unit='°C', icon='vertical_align_top'),
    live.value_of('Bufor śr. góra', topics.sensor('buff_upmid_temp'), unit='°C', icon='expand_less'),
    live.value_of('Bufor śr. dół', topics.sensor('buff_lowmid_temp'), unit='°C', icon='expand_more'),
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
    # Nie z licznika przekaźnika - z wyliczonego statusu paliwa (fuel_level.py),
    # ten sam today_s przeliczony na kg/kWh wg współczynnika aktualnego worka.
    live.value_of('Podajnik dziś (węgiel)', fuel_level.TOPIC, key='today_coal_kg',
                  unit='kg', digits=1, columns=()),
    live.value_of('Podajnik dziś (energia)', fuel_level.TOPIC, key='today_energy_kwh',
                  unit='kWh', digits=1, columns=()),
]

# (tytuł, ikona, [(podpis, spec), ...]) - karty w render_device_cards
DEVICES = [
    ('Dmuchawa', 'mode_fan', [('total', WORK[0]), ('dziś', WORK[1])]),
    ('Podajnik', 'conveyor_belt', [('total', WORK[2]), ('dziś', WORK[3]),
                                   ('dziś (kg)', WORK[4]), ('dziś (kWh)', WORK[5])]),
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


def furnace_boost_controls() -> None:
    """Przycisk "Wypalanie" otwiera potwierdzenie (ile stopni, ile minut -
    patrz furnace_boost.py) zamiast działać od razu - łatwo go kliknąć przez
    przypadek, a to prawdziwa komenda na piec i pompę, nie tylko podgląd.
    Po starcie zamienia się w "Anuluj", z odliczaniem."""
    with ui.row().classes('w-full items-center gap-2'):
        start_btn = ui.button('Wypalanie', icon='whatshot',
                              on_click=lambda: open_confirm()).props('outline color=orange')
        cancel_btn = ui.button('Anuluj wypalanie', icon='close',
                               on_click=lambda: do_cancel()).props('outline color=negative')
        status = ui.label('').classes('text-xs text-grey-6')

    with ui.dialog() as confirm_dialog, ui.card().classes('gap-2 min-w-80'):
        ui.label('Wypalanie pieca').classes('text-base font-medium')
        ui.label('Czasowo podnosi nastawę pieca i włącza pompę - potwierdź, '
                 'żeby uniknąć przypadkowego kliknięcia.').classes('text-xs text-grey-6')
        delta_input = number_stepper('O ile stopni podnieść (°C)',
                                    value=furnace_boost.BOOST_DELTA_C,
                                    min=1, max=20, step=1, format='%.0f', classes='w-full')
        duration_input = number_stepper('Czas trwania (minuty)',
                                       value=furnace_boost.BOOST_DURATION_SECONDS / 60,
                                       min=1, max=60, step=1, format='%.0f', classes='w-full')

        def do_start() -> None:
            delta = float(delta_input.value or furnace_boost.BOOST_DELTA_C)
            minutes = float(duration_input.value or furnace_boost.BOOST_DURATION_SECONDS / 60)
            ok, message = furnace_boost.start_boost(delta=delta, duration=minutes * 60)
            ui.notify(message, type='positive' if ok else 'warning')
            confirm_dialog.close()
            refresh()

        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Anuluj', on_click=confirm_dialog.close).props('flat')
            ui.button('Wypalaj', icon='whatshot', on_click=do_start).props('color=orange')

    def open_confirm() -> None:
        delta_input.value = furnace_boost.BOOST_DELTA_C
        duration_input.value = furnace_boost.BOOST_DURATION_SECONDS / 60
        confirm_dialog.open()

    def refresh() -> None:
        state = furnace_boost.load_state()
        start_btn.visible = state is None
        cancel_btn.visible = state is not None
        if state is None:
            status.text = ''
            return
        remaining = max(0, int((datetime.fromisoformat(state['expires_at'])
                               - datetime.now()).total_seconds()))
        status.text = (f'Aktywne: {state["boosted_value"]:.0f}°C, '
                      f'jeszcze {remaining // 60}:{remaining % 60:02d}')

    def do_cancel() -> None:
        ok, message = furnace_boost.cancel_boost()
        ui.notify(message, type='positive' if ok else 'warning')
        refresh()

    refresh()
    ui.timer(5.0, refresh)


@ui.page('/boiler')
def boiler() -> None:
    page_header('Kocioł CO', back=True)

    panels = []
    with ui.column().classes('w-full p-3 gap-2'):
        with ui.row().classes('w-full items-center gap-2'):
            ui.button('Konfiguracja', icon='settings',
                      on_click=lambda: ui.navigate.to('/boiler/config')).props('outline')
            ui.button('Tankowanie', icon='local_shipping',
                      on_click=lambda: ui.navigate.to('/boiler/refuel')).props('outline')
            ui.button('Wykres temperatur', icon='show_chart',
                      on_click=lambda: ui.navigate.to('/temperatures')).props('flat')

        furnace_boost_controls()

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
