# -*- coding: utf-8 -*-
"""Rekuperacja – wilgotność, jakość powietrza i wentylacja. Przeniesione tu z
`/comfort` (ta strona była o temperaturze/zaworze podłogówki, nie o
powietrzu - inny temat, inna przyszła usługa).

Wciąż ten sam retained topic (`topics.COMFORT_TOPIC`) co `/comfort` - żaden z
tych czujników (wilgotność, CO2, PM2.5...) nie ma jeszcze realnego publishera,
tylko testowy losowy payload (`scripts/comfort_stub.py`). Gdy powstanie
dedykowana usługa rekuperacji, naturalnym krokiem będzie osobny topic (np.
`cave/recuperation`) - ta strona wtedy tylko zmieni źródło, nie kształt."""

from __future__ import annotations
__version__ = "0.1"

from nicegui import ui

from .. import live, topics
from ..widgets import page_header, section

TOPIC = topics.COMFORT_TOPIC


def v(label: str, key: str, **kwargs) -> live.Value:
    return live.Value(label, (TOPIC,), key=key, columns=(), **kwargs)


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


@ui.page('/recuperation')
def recuperation() -> None:
    page_header('Rekuperacja', back=True)

    with ui.column().classes('w-full p-3 gap-2'):
        section('Powietrze')
        panel = live.LivePanel(AIR)
        panel.render_cards()

    panel.start()
    live.mqtt_status_label()
