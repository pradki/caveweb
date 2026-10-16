# -*- coding: utf-8 -*-
"""Konfiguracja Panelu komfortu – głębiej niż `/comfort`, tym samym wzorcem co
`/boiler/config` (metadane -> formularz, "Wczytaj"/"Zapisz" całego formularza
na raz, przycinanie do [min, max] przed wysyłką - patrz boiler_config.py
docstring po pełne uzasadnienie przycinania).

Trzy niezależne sekcje (`ui.expansion`), każda z własnym Wczytaj/Zapisz -
"Harmonogram" (dzień/noc, w układzie tabeli Parametr/Dzień/Noc - patrz
`SetpointGroup.render_day_night_table()`) zaczyna rozwinięta, bo to
najczęściej ruszane; "Nieobecność" i "Zaawansowana konfiguracja" (dziś: tylko
pełny skok zaworu) są zwinięte, tak samo jak /boiler/config chowa rzadziej
ruszane nastawy."""

from __future__ import annotations
__version__ = "0.1"

import json
from datetime import datetime

from nicegui import ui

from .. import comfort_params, live, mqttclient, topics
from ..widgets import number_stepper, page_header, section
from .boiler_config import clamp_value, spec_for
from .comfort import format_until

COMFORT_TOPIC = topics.COMFORT_TOPIC


class SetpointGroup:
    """Nastawy jednorodne (bool/liczba) jednej sekcji - ten sam wzorzec co
    `boiler_config.BoilerConfigPage`, tylko parametryzowany listą nazw zamiast
    hardcodowanego `heating_params.SETPOINTS` w całości, żeby dało się go użyć
    trzykrotnie (Harmonogram/Nieobecność/Zaawansowana konfiguracja) bez
    kopiowania."""

    def __init__(self, names: tuple[str, ...]):
        self.meta = {name: comfort_params.SETPOINTS[name] for name in names}
        self.specs = {name: spec_for(name, meta) for name, meta in self.meta.items()}
        self.panel = live.LivePanel(list(self.specs.values()))
        self.inputs = {}

    def render_rows(self) -> None:
        with ui.column().classes('w-full gap-1'):
            for name, meta in self.meta.items():
                self._render_row(name, meta)

    def render_day_night_table(self, rows: tuple) -> None:
        """Układ "Parametr | Dzień | Noc" zamiast jednego wiersza na pole -
        dla par dzień/noc (ten sam parametr, dwie wartości) nazwa nie
        powtarza się w dwóch wierszach, a cały topic (i tak identyczny poza
        `_day`/`_night`) się nie wypisuje - `rows`: (etykieta, nazwa_dnia,
        nazwa_nocy), patrz `comfort_params.SCHEDULE_ROWS`. Bez kolumny "teraz"
        z brokera, którą ma `_render_row()` - w układzie tabelarycznym nie
        mieściłaby się czytelnie obok dwóch już i tak wąskich kolumn liczb;
        "Wczytaj z brokera" wciąż wypełnia pola aktualnymi wartościami."""
        with ui.row().classes('w-full items-center gap-3 no-wrap text-xs text-grey-5 font-medium'):
            ui.label('Parametr').classes('flex-grow')
            ui.label('Dzień').classes('w-40 text-center')
            ui.label('Noc').classes('w-40 text-center')
        for label, day_name, night_name in rows:
            with ui.row().classes('w-full items-center gap-3 no-wrap'):
                ui.label(label).classes('text-sm flex-grow')
                self.inputs[day_name] = self._cell(self.meta[day_name])
                self.inputs[night_name] = self._cell(self.meta[night_name])

    def _cell(self, meta: dict):
        step = 1 if meta['data_type'] == 'int' else 0.1
        digits = 0 if meta['data_type'] == 'int' else 1
        return number_stepper(value=meta['default'], min=meta['min'], max=meta['max'],
                              step=step, suffix=meta['unit'] or None,
                              format=f'%.{digits}f', classes='w-40')

    def render_buttons(self) -> None:
        with ui.row().classes('w-full items-center gap-2'):
            ui.button('Wczytaj z brokera', icon='download',
                      on_click=lambda: self.load(notify=True)).props('outline')
            ui.button('Zapisz', icon='save', on_click=self.save).props('color=primary')

    def start(self) -> None:
        self.panel.start()
        ui.timer(1.0, lambda: self.load(notify=False), once=True)

    def _render_row(self, name: str, meta: dict) -> None:
        with ui.row().classes('w-full items-center gap-3 no-wrap'):
            with ui.column().classes('gap-0 w-64'):
                ui.label(meta['desc'] or name).classes('text-sm')
                ui.label(f"{name} · {meta['topic']}").classes('text-xs text-grey-7')
            current = ui.label('–').classes('text-sm font-medium w-20 text-right')
            caption = ui.label('').classes('text-xs text-grey-7 w-24')
            self.panel.bind(name, current, caption)
            if meta['data_type'] == 'bool':
                self.inputs[name] = ui.switch(value=bool(meta['default']))
            else:
                step = 1 if meta['data_type'] == 'int' else 0.1
                digits = 0 if meta['data_type'] == 'int' else 1
                # `format` jawnie - bez niego ui.number pokazywał więcej miejsc
                # po przecinku niż krok 0.1 sugeruje (dryf float przy +/-
                # wyglądał jak setne stopnia zamiast dziesiątych).
                self.inputs[name] = number_stepper(
                    value=meta['default'], min=meta['min'], max=meta['max'],
                    step=step, suffix=meta['unit'] or None,
                    format=f'%.{digits}f', classes='w-60')
            ui.label(f"{meta['min']} … {meta['max']} {meta['unit']}".strip()) \
                .classes('text-xs text-grey-7 w-28')

    def load(self, notify: bool) -> None:
        filled = 0
        for name, spec in self.specs.items():
            reading = live.read(spec)
            if reading.value is None:
                continue
            widget = self.inputs.get(name)
            if widget is None:
                continue
            meta = self.meta[name]
            if meta['data_type'] == 'bool':
                widget.value = bool(reading.value)
            elif meta['data_type'] == 'int':
                widget.value = int(round(float(reading.value)))
            else:
                widget.value = float(reading.value)
            filled += 1
        if notify:
            ui.notify(f'Wczytano {filled} z {len(self.specs)} nastaw z brokera')

    def save(self) -> None:
        sent, failed = 0, []
        for name, meta in self.meta.items():
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
            ui.notify(f'Wysłano {sent}/{len(self.meta)} nastaw - błąd dla: {", ".join(failed)}',
                      type='warning')
        else:
            ui.notify(f'Wysłano {sent} nastaw do comfort-controller', type='positive')


def _to_datetime_local(iso_str) -> str:
    """Wartość do pola `type=datetime-local` ("YYYY-MM-DDTHH:MM", bez sekund -
    niektóre przeglądarki przycinają pole wyświetlania do minut mimo że w
    ogóle akceptują sekundy w `value`, więc dla pewności ładujemy bez nich)."""
    if not iso_str:
        return ''
    try:
        return datetime.fromisoformat(str(iso_str)).strftime('%Y-%m-%dT%H:%M')
    except ValueError:
        return ''


class AbsenceSection:
    """Nieobecność zaplanowana (switch + zakres dat + temperatura) i "tylko
    dziś" (switch) - pięć nastaw razem w jednym Wczytaj/Zapisz, bo to jedna
    spójna decyzja użytkownika, nie zestaw niezależnych pokręteł. `enabled`/
    `temp` idą przez `SetpointGroup` (jednorodne); start/end/today mają własny
    kształt widgetu (patrz comfort_params.py docstring) i są dopisane ręcznie."""

    def __init__(self) -> None:
        self.plain = SetpointGroup(comfort_params.ABSENCE_FIELDS)
        self.start_input = None
        self.end_input = None
        self.today_switch = None
        self.status_label = None
        self.today_caption = None

    def render(self) -> None:
        self.status_label = ui.label('–').classes('text-sm text-grey-7')

        section('Zaplanowana')
        self.plain.render_rows()
        with ui.row().classes('w-full items-center gap-3 no-wrap'):
            ui.label('Od').classes('text-sm w-16')
            self.start_input = ui.input().props('type=datetime-local').classes('w-56')
            ui.label('Do').classes('text-sm w-16')
            self.end_input = ui.input().props('type=datetime-local').classes('w-56')

        section('Tylko dziś')
        with ui.row().classes('items-center gap-2'):
            self.today_switch = ui.switch('Nieobecność tylko dziś')
            self.today_caption = ui.label('').classes('text-xs text-grey-7')

        with ui.row().classes('w-full items-center gap-2 pt-2'):
            ui.button('Wczytaj z brokera', icon='download',
                      on_click=lambda: self.load(notify=True)).props('outline')
            ui.button('Zapisz', icon='save', on_click=self.save).props('color=primary')

    def start(self) -> None:
        self.plain.panel.start()
        ui.timer(1.0, lambda: self.load(notify=False), once=True)
        ui.timer(0.1, self._refresh_status, once=True)
        ui.timer(5.0, self._refresh_status)

    def _refresh_status(self) -> None:
        active = mqttclient.cache.value(COMFORT_TOPIC, 'absence_active')
        source = mqttclient.cache.value(COMFORT_TOPIC, 'absence_source')
        until = mqttclient.cache.value(COMFORT_TOPIC, 'absence_until')
        if active:
            label = 'zaplanowana' if source == 'scheduled' else 'tylko dziś'
            self.status_label.text = f'Aktywna nieobecność ({label}), {format_until(until)}'
        else:
            self.status_label.text = 'Nieobecność nieaktywna - obowiązuje harmonogram'
        self.today_caption.text = (
            f'aktywne, {format_until(until)}' if source == 'today' and active else '')

    def load(self, notify: bool) -> None:
        self.plain.load(notify=False)
        start = mqttclient.cache.value(comfort_params.ABSENCE_START_TOPIC)
        end = mqttclient.cache.value(comfort_params.ABSENCE_END_TOPIC)
        today = mqttclient.cache.value(comfort_params.ABSENCE_TODAY_TOPIC)
        self.start_input.value = _to_datetime_local(start)
        self.end_input.value = _to_datetime_local(end)
        self.today_switch.value = bool(today)
        if notify:
            ui.notify('Wczytano nieobecność z brokera')

    def save(self) -> None:
        start_text = (self.start_input.value or '').strip()
        end_text = (self.end_input.value or '').strip()
        start_dt = datetime.fromisoformat(start_text) if start_text else None
        end_dt = datetime.fromisoformat(end_text) if end_text else None
        if start_dt and end_dt and start_dt >= end_dt:
            ui.notify('Data początku musi być wcześniejsza niż data końca - nic nie wysłano',
                      type='negative')
            return

        self.plain.save()
        mqttclient.publish(comfort_params.ABSENCE_START_TOPIC,
                          json.dumps({'value': start_text or None}), qos=0, retain=True)
        mqttclient.publish(comfort_params.ABSENCE_END_TOPIC,
                          json.dumps({'value': end_text or None}), qos=0, retain=True)
        mqttclient.publish(comfort_params.ABSENCE_TODAY_TOPIC,
                          json.dumps({'value': bool(self.today_switch.value)}), qos=0, retain=True)
        ui.notify('Wysłano nieobecność do comfort-controller', type='positive')


@ui.page('/comfort/config')
def comfort_config() -> None:
    page_header('Panel komfortu – konfiguracja', back=True)

    schedule = SetpointGroup(comfort_params.SCHEDULE_FIELDS)
    absence = AbsenceSection()
    advanced = SetpointGroup(comfort_params.ADVANCED_FIELDS)

    with ui.column().classes('w-full p-3 gap-2'):
        ui.label('kolumna "teraz" (gdzie widoczna) to wartość z brokera, pole obok to '
                 'wartość do wysłania przy Zapisz').classes('text-xs text-grey-7')

        with ui.expansion('Harmonogram', icon='schedule', value=True).classes('w-full'):
            with ui.column().classes('w-full gap-2 pt-2'):
                schedule.render_buttons()
                schedule.render_day_night_table(comfort_params.SCHEDULE_ROWS)

        with ui.expansion('Nieobecność', icon='flight_takeoff').classes('w-full mt-2'):
            with ui.column().classes('w-full gap-2 pt-2'):
                absence.render()

        with ui.expansion('Zaawansowana konfiguracja', icon='tune').classes('w-full mt-2'):
            with ui.column().classes('w-full gap-2 pt-2'):
                advanced.render_buttons()
                advanced.render_rows()

    schedule.start()
    absence.start()
    advanced.start()
    live.mqtt_status_label()
