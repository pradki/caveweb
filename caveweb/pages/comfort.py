# -*- coding: utf-8 -*-
"""Panel komfortu – temperatura, zawór mieszający podłogówki i (na razie
uproszczony) harmonogram dzień/noc. Wilgotność/CO2/jakość powietrza
przeniosły się na `/recuperation` - patrz tamten moduł.

Wszystko z jednego retained topicu (`topics.COMFORT_TOPIC`) - caveweb tylko
prezentuje, licząca/sterująca usługa (`comfort-controller`, osobne repo -
integracja tylko przez MQTT) publikuje tam temperaturę i stan zaworu/pompy
(etap 0: bang-bang dzień/noc, patrz jej README). Strona pokazuje cokolwiek
akurat jest na topicu, z "–" przy brakujących polach, identycznie jak reszta
aplikacji. Pola enumeracyjne (tryb, stan, harmonogram...) przychodzą już jako
gotowy do pokazania tekst po polsku - `live.format_value` przepuszcza string
bez zmian, więc nie trzeba osobnego słownika tłumaczeń tutaj.

Sekcja "Konfiguracja" niżej to jedyne miejsce, gdzie ta strona coś publikuje -
siedem nastaw: temperatura zadana i sześć bang-bang (etap 0), bez których
comfort-controller nie ma jak zdecydować, kiedy jest "dzień" i jak szeroko
otworzyć zawór. `mixing_valve_time` na razie nie ma tu formularza - "na razie
tylko to, co niezbędne do pracy"."""

from __future__ import annotations
__version__ = "0.2"

import json

from nicegui import ui

from .. import live, mqttclient, topics
from ..widgets import number_stepper, page_header, section

TOPIC = topics.COMFORT_TOPIC


def v(label: str, key: str, **kwargs) -> live.Value:
    """Pole z payloadu /comfort - bez kolumny awaryjnej w bazie, bo metrica
    tego topiku jeszcze nie zbiera (to nie czujnik, to dopiero przyszła
    usługa)."""
    return live.Value(label, (TOPIC,), key=key, columns=(), **kwargs)


def config_setpoint_topic(name: str) -> str:
    return f'{TOPIC}/setpoints/{name}'


# Aktualna temperatura i zadana, tryb grzania (na razie tylko grzanie, bez
# chłodzenia/auto), stan urządzenia, strefa (na razie zawsze jedna). Nastawa
# czytana WPROST z cave/comfort/setpoints/inside_temp, nie z pola "temp_setpoint"
# na cave/comfort - to drugie było echem tej samej wartości, które potrafiło
# zostać w tyle do najbliższego ticku comfort-controller (wyglądało jak błąd,
# mimo że sama nastawa na broker już doszła) - usunięte stamtąd właśnie dlatego.
COMFORT = [
    v('Temperatura', 'temp_current', unit='°C', digits=1, icon='thermostat'),
    live.Value('Nastawa', (config_setpoint_topic('inside_temp'),), key='value',
              unit='°C', digits=1, icon='flag', columns=()),
    v('Tryb', 'mode', icon='tune'),
    v('Stan', 'hvac_state', icon='local_fire_department'),
    v('Strefa', 'zone', icon='home'),
    v('Alarm', 'alarm_reason', icon='warning'),
]

# Zawór mieszający podłogówki i jego pompa - z comfort-controller (etap 0:
# bang-bang dzień/noc, patrz jego README). mixing_valve to CEL otwarcia, nie
# pomiar - zawór nie ma czujnika pozycji, usługa tylko pamięta, ile razy i jak
# długo kazała mu jechać.
VALVE = [
    v('Otwarcie zaworu', 'mixing_valve', unit='%', digits=0, icon='tune'),
    v('Próg niski', 'mixing_valve_low', unit='%', digits=0, icon='arrow_downward'),
    v('Próg wysoki', 'mixing_valve_high', unit='%', digits=0, icon='arrow_upward'),
    v('Pełny skok', 'mixing_valve_time', unit='s', digits=0, icon='timer'),
    v('Pompa podłogówki', 'pump_on', kind='bool', icon='water_pump'),
]

# "W praktyce będzie pewnie tylko dzień/noc" - stąd tylko tryb i profil,
# bez edytowalnych godzin pobudki/wyjścia itp. (to już zadanie dedykowanej
# usługi, nie caveweb).
SCHEDULE = [
    v('Harmonogram', 'schedule_mode', icon='schedule'),
    v('Profil', 'schedule_profile', icon='event'),
    v('Nadpisanie', 'override_state', icon='edit_calendar'),
]

# (nazwa pola w cave/comfort/setpoints/<nazwa> - UWAGA, "setpoints" w liczbie
# mnogiej, tak jak cave/heating/setpoints/* - etykieta, typ, min, max,
# domyślna, jednostka, krok) - nastawa temperatury i sześć bang-bang etapu 0
# w comfort-controller (patrz jego config.example.py - te same domyślne).
CONFIG_FIELDS = [
    ('inside_temp', 'Nastawa temperatury', 'float', 15.0, 28.0, 21.0, '°C', 0.1),
    ('day_start_hour', 'Dzień od (godz.)', 'int', 0, 23, 6, '', 1),
    ('day_end_hour', 'Dzień do (godz.)', 'int', 0, 23, 20, '', 1),
    ('mixing_valve_low_day', 'Próg niski - dzień', 'float', 0, 100, 20.0, '%', 1),
    ('mixing_valve_high_day', 'Próg wysoki - dzień', 'float', 0, 100, 25.0, '%', 1),
    ('mixing_valve_low_night', 'Próg niski - noc', 'float', 0, 100, 15.0, '%', 1),
    ('mixing_valve_high_night', 'Próg wysoki - noc', 'float', 0, 100, 20.0, '%', 1),
]


def clamp_config_value(data_type: str, min_v: float, max_v: float, value) -> int | float:
    """Przycięcie do typu i zakresu - patrz boiler_config.clamp_value po
    uzasadnienie (ten sam powód: usługa, która dostanie wartość spoza
    zakresu, nie przytnie jej sama, tylko zresetuje do swojego configu)."""
    value = max(min_v, min(max_v, float(value)))
    return int(round(value)) if data_type == 'int' else value


def config_section() -> None:
    """Nastawa temperatury i sześć bang-bang etapu 0 (patrz CONFIG_FIELDS) -
    "Wczytaj" wypełnia pola aktualnymi wartościami z brokera (albo domyślnymi,
    gdy jeszcze nic tam nie ma), "Zapisz" publikuje WSZYSTKIE na raz, tak samo
    jak /boiler/config robi to dla nastaw kotła."""
    inputs = {}

    def load_from_broker(notify: bool = True) -> None:
        filled = 0
        for name, _, data_type, _, _, default, _, _ in CONFIG_FIELDS:
            value = mqttclient.cache.value(config_setpoint_topic(name))
            widget = inputs.get(name)
            if widget is None:
                continue
            if value is None:
                widget.value = default
                continue
            widget.value = int(round(value)) if data_type == 'int' else float(value)
            filled += 1
        if notify:
            ui.notify(f'Wczytano {filled} z {len(CONFIG_FIELDS)} nastaw z brokera')

    def save_to_broker() -> None:
        sent = 0
        for name, _, data_type, min_v, max_v, _, _, _ in CONFIG_FIELDS:
            widget = inputs.get(name)
            if widget is None or widget.value is None:
                continue
            value = clamp_config_value(data_type, min_v, max_v, widget.value)
            mqttclient.publish(config_setpoint_topic(name), json.dumps({'value': value}),
                              qos=0, retain=True)
            sent += 1
        ui.notify(f'Wysłano {sent} nastaw do comfort-controller', type='positive')

    with ui.row().classes('w-full items-center gap-2'):
        ui.button('Wczytaj z brokera', icon='download',
                  on_click=lambda: load_from_broker()).props('outline')
        ui.button('Zapisz', icon='save', on_click=save_to_broker).props('color=primary')

    with ui.column().classes('w-full gap-1'):
        for name, label, data_type, min_v, max_v, default, unit, step in CONFIG_FIELDS:
            with ui.row().classes('w-full items-center gap-3 no-wrap'):
                ui.label(label).classes('text-sm w-44')
                # Krok całkowity (godziny, %) -> bez miejsc po przecinku;
                # krok ułamkowy (0.1°C temperatury) -> jedno miejsce.
                digits = 0 if float(step).is_integer() else 1
                inputs[name] = number_stepper(
                    value=default, min=min_v, max=max_v, step=step,
                    suffix=unit or None, format=f'%.{digits}f',
                    classes='w-48')

    ui.timer(1.0, lambda: load_from_broker(notify=False), once=True)


@ui.page('/comfort')
def comfort() -> None:
    page_header('Panel komfortu', back=True)

    panels = []
    with ui.column().classes('w-full p-3 gap-2'):
        for title, values in (('Komfort', COMFORT), ('Zawór mieszający', VALVE),
                              ('Harmonogram', SCHEDULE)):
            section(title)
            panel = live.LivePanel(values)
            panel.render_cards()
            panels.append(panel)

        section('Konfiguracja')
        ui.label('Nastawy niezbędne comfort-controller do pracy (etap 0) - '
                 'reszta nastaw tej usługi (np. mixing_valve_time) nie ma tu '
                 'jeszcze formularza.') \
            .classes('text-xs text-grey-7')
        config_section()

    for panel in panels:
        panel.start()
    live.mqtt_status_label()
