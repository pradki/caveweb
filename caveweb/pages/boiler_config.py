"""Konfiguracja kotła CO – wszystkie nastawy z PARAMS_HEATING.

Strona buduje się sama z metadanych (`heating_params.SETPOINTS`): typ pola,
zakres i jednostka pochodzą z tego samego słownika, którego pilnuje usługa
grzewcza.

**Zapisz** publikuje WSZYSTKIE pola widoczne na stronie na raz, nie tylko to,
co faktycznie ruszono - to prosty model "wyślij cały formularz", zgodny z tym,
jak działa "Wczytaj z brokera" (wypełnia wszystkie pola na raz). Każda
wartość liczbowa jest przed wysyłką przycinana do [min, max] z metadanych -
to konieczne, nie kosmetyczne: `heating-controller`'s `shadow_vault.
check_and_correct()` dla wartości spoza zakresu NIE przycina, tylko resetuje
cały parametr do jego wartości domyślnej (patrz `furnace_boost.py`, ten sam
mechanizm uzasadnił tam samo przycięcie). Bez przycięcia tutaj np. zbyt
entuzjastyczny spinner cicho cofnąłby nastawę do domyślnej zamiast ustawić to,
co było w polu.
"""

from __future__ import annotations
__version__ = "0.1"

import json

from nicegui import ui

from .. import heating_params, live, mqttclient
from ..widgets import number_stepper, page_header, section

# Najczęściej ruszane nastawy - zawsze widoczne. Reszta `heating_params.SETPOINTS`
# (progi bezpieczeństwa, strojenie dmuchawy/zaworu...) trafia do zwijanej sekcji
# "Zaawansowana konfiguracja", żeby ten ekran nie zniechęcał przy pierwszym
# wejściu długą listą rzadko dotykanych pól.
BASIC_SETPOINTS = (
    'furnace_enable_setpoint',
    'furnace_temp_setpoint',
    'feeding_time_setpoint',
    'pause_time_setpoint',
    'keeping_fire_interval_setpoint',
    'keeping_fire_duration_setpoint',
    'multiplicity_setpoint',
)


def spec_for(name: str, meta: dict) -> live.Value:
    """Wartość bieżąca nastawy (to, co faktycznie siedzi na brokerze)."""
    kind = 'bool' if meta['data_type'] == 'bool' else 'number'
    digits = 0 if meta['data_type'] in ('int', 'bool') else 1
    return live.value_of(name, meta['topic'], unit=meta['unit'],
                         digits=digits, kind=kind, columns=())


def clamp_value(meta: dict, value) -> bool | int | float:
    """Wartość pola dociśnięta do typu i zakresu z metadanych - osobno od
    widgetu, żeby dało się to przetestować bez nicegui. Patrz docstring
    modułu po to, dlaczego przycinanie jest konieczne, nie kosmetyczne."""
    if meta['data_type'] == 'bool':
        return bool(value)
    value = float(value)
    if meta['min'] is not None:
        value = max(meta['min'], value)
    if meta['max'] is not None:
        value = min(meta['max'], value)
    if meta['data_type'] == 'int':
        value = int(round(value))
    return value


class BoilerConfigPage:
    def __init__(self) -> None:
        self.specs = {name: spec_for(name, meta)
                      for name, meta in heating_params.SETPOINTS.items()}
        self.panel = live.LivePanel(list(self.specs.values()))
        self.inputs = {}

    def build(self) -> None:
        page_header('Kocioł CO – konfiguracja', back=True)

        with ui.column().classes('w-full p-3 gap-2'):
            with ui.row().classes('w-full items-center gap-2'):
                ui.button('Wczytaj z brokera', icon='download',
                          on_click=lambda: self.load_from_broker()).props('outline')
                ui.button('Zapisz', icon='save', on_click=lambda: self.save_to_broker()) \
                    .props('color=primary')
                ui.space()
                ui.label('Zapisz wysyła WSZYSTKIE pola poniżej, nie tylko zmienione') \
                    .classes('text-xs text-grey-6')

            ui.label('kolumna "teraz" to wartość z brokera, pole obok to wartość '
                     'do wysłania przy Zapisz').classes('text-xs text-grey-7')

            advanced_names = [name for name in heating_params.SETPOINTS
                             if name not in BASIC_SETPOINTS]

            section('Podstawowa konfiguracja')
            with ui.column().classes('w-full gap-1'):
                for name in BASIC_SETPOINTS:
                    self.render_row(name, heating_params.SETPOINTS[name])

            with ui.expansion('Zaawansowana konfiguracja', icon='tune') \
                    .classes('w-full mt-2'):
                with ui.column().classes('w-full gap-1 pt-2'):
                    for name in advanced_names:
                        self.render_row(name, heating_params.SETPOINTS[name])

        self.panel.start()
        ui.timer(1.0, lambda: self.load_from_broker(notify=False), once=True)
        live.mqtt_status_label()

    def render_row(self, name: str, meta: dict) -> None:
        with ui.row().classes('w-full items-center gap-3 no-wrap'):
            with ui.column().classes('gap-0 w-72'):
                ui.label(meta['desc'] or name).classes('text-sm')
                ui.label(f"{name} · {meta['topic']}").classes('text-xs text-grey-7')

            current = ui.label('–').classes('text-sm font-medium w-24 text-right')
            caption = ui.label('').classes('text-xs text-grey-7 w-28')
            self.panel.bind(name, current, caption)

            if meta['data_type'] == 'bool':
                self.inputs[name] = ui.switch(value=bool(meta['default']))
            else:
                step = 1 if meta['data_type'] == 'int' else 0.1
                self.inputs[name] = number_stepper(
                    value=meta['default'], min=meta['min'], max=meta['max'],
                    step=step, suffix=meta['unit'] or None, classes='w-48')

            ui.label(f"{meta['min']} … {meta['max']} {meta['unit']}".strip()) \
                .classes('text-xs text-grey-7 w-32')

    def load_from_broker(self, notify: bool = True) -> None:
        """Wstawia w pola to, co aktualnie leci z brokera (albo domyślne)."""
        filled = 0
        for name, spec in self.specs.items():
            reading = live.read(spec)
            if reading.value is None:
                continue
            widget = self.inputs.get(name)
            if widget is None:
                continue
            meta = heating_params.SETPOINTS[name]
            if meta['data_type'] == 'bool':
                widget.value = bool(reading.value)
            elif meta['data_type'] == 'int':
                widget.value = int(round(float(reading.value)))
            else:
                widget.value = float(reading.value)
            filled += 1
        if notify:
            ui.notify(f'Wczytano {filled} z {len(self.specs)} nastaw z brokera')

    def save_to_broker(self) -> None:
        """Publikuje każde pole na jego topic - patrz docstring modułu po
        uzasadnienie przycinania do [min, max] przed wysyłką."""
        sent = 0
        failed = []
        for name, meta in heating_params.SETPOINTS.items():
            widget = self.inputs.get(name)
            if widget is None or widget.value is None:
                continue
            value = clamp_value(meta, widget.value)

            info = mqttclient.publish(meta['topic'], json.dumps({'value': value}),
                                      qos=0, retain=True)
            rc = getattr(info, 'rc', None)
            if rc not in (None, 0):
                failed.append(name)
            else:
                sent += 1

        if failed:
            ui.notify(f'Wysłano {sent}/{len(self.specs)} nastaw - błąd dla: {", ".join(failed)}',
                      type='warning')
        else:
            ui.notify(f'Wysłano {sent} nastaw do brokera', type='positive')


@ui.page('/boiler/config')
def boiler_config() -> None:
    BoilerConfigPage().build()
