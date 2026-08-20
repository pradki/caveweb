"""Konfiguracja kotła CO – wszystkie nastawy z PARAMS_HEATING.

Strona buduje się sama z metadanych (`heating_params.SETPOINTS`): typ pola,
zakres i jednostka pochodzą z tego samego słownika, którego pilnuje usługa
grzewcza, więc nie da się tu wpisać wartości poza jej zakresem.

Zapis jest na razie wyłączony: publikacja na `cave/heating/setpoints/#` zmienia
pracę kotła, a caveweb do tej pory tylko słucha. Wystarczy jedno wywołanie
publish, ale to decyzja do podjęcia świadomie - patrz README.
"""

from __future__ import annotations
__version__ = "0.1"

from nicegui import ui

from .. import heating_params, live
from ..widgets import page_header, section


def spec_for(name: str, meta: dict) -> live.Value:
    """Wartość bieżąca nastawy (to, co faktycznie siedzi na brokerze)."""
    kind = 'bool' if meta['data_type'] == 'bool' else 'number'
    digits = 0 if meta['data_type'] in ('int', 'bool') else 1
    return live.value_of(name, meta['topic'], unit=meta['unit'],
                         digits=digits, kind=kind, columns=())


class BoilerConfigPage:
    def __init__(self) -> None:
        self.specs = {name: spec_for(name, meta)
                      for name, meta in heating_params.SETPOINTS.items()}
        self.panel = live.LivePanel(list(self.specs.values()))
        self.inputs = {}

    def build(self) -> None:
        page_header('Kocioł CO – konfiguracja', back='/boiler')

        with ui.column().classes('w-full p-3 gap-2'):
            with ui.row().classes('w-full items-center gap-2'):
                ui.button('Wczytaj z brokera', icon='download',
                          on_click=lambda: self.load_from_broker()).props('outline')
                save = ui.button('Zapisz', icon='save').props('disable')
                with save:
                    ui.tooltip('Publikowanie nastaw jeszcze nie jest włączone')
                ui.space()
                ui.label('podgląd nastaw – zmiany nie są wysyłane') \
                    .classes('text-xs text-orange-6')

            section('Nastawy kotła')
            ui.label('kolumna "teraz" to wartość z brokera, pole obok to wartość '
                     'do wysłania po włączeniu zapisu').classes('text-xs text-grey-7')

            with ui.column().classes('w-full gap-1'):
                for name, meta in heating_params.SETPOINTS.items():
                    self.render_row(name, meta)

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
                self.inputs[name] = ui.number(
                    value=meta['default'], min=meta['min'], max=meta['max'],
                    step=step, suffix=meta['unit'] or None,
                ).props('dense outlined').classes('w-32')

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


@ui.page('/boiler/config')
def boiler_config() -> None:
    BoilerConfigPage().build()
