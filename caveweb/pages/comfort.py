# -*- coding: utf-8 -*-
"""Panel komfortu – temperatura, wilgotność, jakość powietrza i (na razie
uproszczony) harmonogram dzień/noc.

Wszystko z jednego retained topicu (`topics.COMFORT_TOPIC`) - licząca/sterująca
usługa jeszcze nie istnieje, będzie dedykowanym serwisem, tak jak reszta
instalacji (integracja tylko przez MQTT, patrz README). Do tego czasu na
topicu ląduje testowy, losowy payload (`scripts/comfort_stub.py`) - strona
pokazuje cokolwiek tam akurat jest, z "–" przy brakujących polach, identycznie
jak reszta aplikacji. Pola enumeracyjne (tryb, stan, harmonogram...) przychodzą
już jako gotowy do pokazania tekst po polsku - `live.format_value` przepuszcza
string bez zmian, więc nie trzeba osobnego słownika tłumaczeń tutaj; gdy
powstanie prawdziwa usługa, to ona decyduje o treści tych etykiet.
"""

from __future__ import annotations
__version__ = "0.1"

from nicegui import ui

from .. import live, topics
from ..widgets import page_header, section

TOPIC = topics.COMFORT_TOPIC


def v(label: str, key: str, **kwargs) -> live.Value:
    """Pole z payloadu /comfort - bez kolumny awaryjnej w bazie, bo metrica
    tego topiku jeszcze nie zbiera (to nie czujnik, to dopiero przyszła
    usługa)."""
    return live.Value(label, (TOPIC,), key=key, columns=(), **kwargs)


# Aktualna temperatura i zadana, tryb grzania (na razie tylko grzanie, bez
# chłodzenia/auto), stan urządzenia, strefa (na razie zawsze jedna).
COMFORT = [
    v('Temperatura', 'temp_current', unit='°C', digits=1, icon='thermostat'),
    v('Nastawa', 'temp_setpoint', unit='°C', digits=1, icon='flag'),
    v('Tryb', 'mode', icon='tune'),
    v('Stan', 'hvac_state', icon='local_fire_department'),
    v('Strefa', 'zone', icon='home'),
]

# "W praktyce będzie pewnie tylko dzień/noc" - stąd tylko tryb i profil,
# bez edytowalnych godzin pobudki/wyjścia itp. (to już zadanie dedykowanej
# usługi, nie caveweb).
SCHEDULE = [
    v('Harmonogram', 'schedule_mode', icon='schedule'),
    v('Profil', 'schedule_profile', icon='event'),
    v('Nadpisanie', 'override_state', icon='edit_calendar'),
]

# PM2.5/VOC/radon - opcjonalne, zależnie od zamontowanych czujników; brak
# wartości w payloadzie (None) pokazuje się jak wszędzie indziej jako "–".
AIR = [
    v('Temperatura', 'temp_current', unit='°C', digits=1, icon='thermostat'),
    v('Wilgotność', 'humidity', unit='%', digits=0, icon='water_drop'),
    v('CO2', 'co2', unit='ppm', digits=0, icon='co2'),
    v('PM2.5', 'pm25', unit='µg/m³', digits=0, icon='grain'),
    v('VOC', 'voc', unit='ppb', digits=0, icon='science'),
    v('Radon', 'radon', unit='Bq/m³', digits=0, icon='warning'),
    v('Wentylacja', 'ventilation_state', icon='mode_fan'),
    v('Filtr', 'filter_state', icon='filter_alt'),
    v('Zawilgocenie', 'damp_state', icon='water_damage'),
]


@ui.page('/comfort')
def comfort() -> None:
    page_header('Panel komfortu', back=True)

    panels = []
    with ui.column().classes('w-full p-3 gap-2'):
        for title, values in (('Komfort', COMFORT), ('Harmonogram', SCHEDULE),
                              ('Powietrze', AIR)):
            section(title)
            panel = live.LivePanel(values)
            panel.render_cards()
            panels.append(panel)

    for panel in panels:
        panel.start()
    live.mqtt_status_label()
