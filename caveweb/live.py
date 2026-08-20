# -*- coding: utf-8 -*-
"""Wartości bieżące: definicja, odczyt i widgety.

Źródłem pierwszego wyboru jest broker (`mqttclient.cache`). Gdy topic jeszcze
nie przyszedł - bo publisher nie używa retain albo aplikacja właśnie wstała -
sięgamy po ostatni kubełek 15-minutowy z bazy metriki. Wtedy wartość jest
opisana jako pochodząca z bazy, żeby nikt nie wziął jej za odczyt na żywo.
"""

from __future__ import annotations
__version__ = "0.1"

import time
from dataclasses import dataclass

from nicegui import run, ui

from . import db, mqttclient

# Po tym czasie bez świeżej wiadomości wartość pokazujemy na szaro
STALE_SECONDS = mqttclient.STALE_SECONDS


@dataclass(frozen=True)
class Value:
    """Jedna pozycja na ekranie.

    Kilka topików znaczy sumę (moc PV = PV1 + PV2). `columns` to odpowiedniki
    w bazie metriki, używane tylko awaryjnie i sumowane tak samo.
    """
    label: str
    topics: tuple[str, ...]
    unit: str = ''
    digits: int = 1
    columns: tuple[str, ...] = ()
    kind: str = 'number'          # 'number' | 'bool' | 'seconds'
    key: str = 'value'            # pole w payloadzie JSON (patrz mqttclient)
    icon: str = ''
    desc: str = ''


@dataclass
class Reading:
    value: object = None
    source: str = 'brak'          # 'broker' | 'baza' | 'brak'
    age: float | None = None
    text: str = '–'
    stale: bool = True
    present: int = 0              # ile topików sumy faktycznie mamy
    expected: int = 0


def signal_column(topic: str) -> str:
    """Kolumna metriki dla topiku: ostatni segment + '_avg'."""
    return f'{topic.rsplit("/", 1)[-1]}_avg'


def value_of(label, topic, **kwargs) -> Value:
    """Skrót dla pojedynczego topiku - kolumnę w bazie zgadujemy z nazwy."""
    columns = kwargs.pop('columns', (signal_column(topic),))
    return Value(label, (topic,), columns=columns, **kwargs)


def sum_of(label, topics, **kwargs) -> Value:
    columns = kwargs.pop('columns', tuple(signal_column(t) for t in topics))
    return Value(label, tuple(topics), columns=columns, **kwargs)


def db_columns(values) -> list:
    """Wszystkie kolumny potrzebne do awaryjnego odczytu z bazy."""
    columns = []
    for value in values:
        for column in value.columns:
            if column not in columns:
                columns.append(column)
    return columns


def format_value(spec: Value, value) -> str:
    if value is None:
        return '–'
    if spec.kind == 'bool':
        return 'wł.' if value else 'wył.'
    if spec.kind == 'seconds':
        minutes = float(value) / 60.0
        return f'{minutes:.0f} min' if minutes < 600 else f'{minutes / 60:.1f} h'
    if isinstance(value, str):
        return value
    text = f'{float(value):.{spec.digits}f}'
    return f'{text} {spec.unit}'.strip()


def read(spec: Value, db_values=None, now: float | None = None) -> Reading:
    """Składa wartość z brokera, a w razie potrzeby z bazy."""
    now = now if now is not None else time.time()

    parts, ages = [], []
    for topic in spec.topics:
        entry = mqttclient.cache.get(topic)
        if entry is None:
            continue
        value = mqttclient.extract(entry[0], spec.key)
        if value is not None:
            parts.append(value)
            ages.append(now - entry[1])

    if parts:
        value = parts[0] if len(spec.topics) == 1 else sum(parts)
        age = max(ages) if ages else None
        return Reading(value=value, source='broker', age=age,
                       text=format_value(spec, value),
                       stale=age is not None and age > STALE_SECONDS,
                       present=len(parts), expected=len(spec.topics))

    # awaryjnie: ostatni kubełek z metriki
    db_values = db_values or {}
    parts = [db_values[column][0] for column in spec.columns
             if db_values.get(column) is not None]
    if parts:
        value = parts[0] if len(spec.columns) == 1 else sum(parts)
        return Reading(value=value, source='baza', age=None,
                       text=format_value(spec, value), stale=True,
                       present=len(parts), expected=len(spec.columns))

    return Reading(expected=len(spec.topics))


class LivePanel:
    """Zestaw wartości odświeżanych jednym timerem.

    Panel sam decyduje, czy sięgać do bazy: robi to tylko wtedy, gdy po stronie
    brokera brakuje jakiegoś topiku, więc przy działającym MQTT odświeżanie nie
    dotyka dysku.
    """

    def __init__(self, values, interval: float = 5.0) -> None:
        self.values = list(values)
        self.interval = interval
        self._labels = {}
        self._captions = {}

    # ------------------------------------------------------------- rysowanie

    def render_compact(self) -> None:
        """Wiersze etykieta - wartość, do kafelka na ekranie głównym."""
        with ui.column().classes('w-full gap-0 items-center'):
            for spec in self.values:
                self._labels[spec.label] = ui.label('–').classes(
                    'text-xl font-medium leading-tight')
                ui.label(spec.label).classes('text-xs text-grey-6 leading-tight')

    def render_cards(self, columns: str = 'w-40') -> None:
        """Kafelki z dużą wartością - do stron szczegółowych."""
        with ui.row().classes('w-full gap-3 flex-wrap'):
            for spec in self.values:
                with ui.card().classes(f'{columns} p-3 gap-1'):
                    with ui.row().classes('items-center gap-1 no-wrap'):
                        if spec.icon:
                            ui.icon(spec.icon).classes('text-sm text-blue-4')
                        ui.label(spec.label).classes('text-xs text-grey-5')
                    self._labels[spec.label] = ui.label('–').classes('text-2xl font-medium')
                    self._captions[spec.label] = ui.label('').classes('text-xs text-grey-7')
                    if spec.desc:
                        ui.label(spec.desc).classes('text-xs text-grey-8')

    def render_rows(self) -> None:
        """Zwarta lista wiersz po wierszu - do nastaw i długich zestawów."""
        with ui.column().classes('w-full gap-1'):
            for spec in self.values:
                with ui.row().classes('w-full items-baseline gap-2'):
                    ui.label(spec.label).classes('text-sm text-grey-5 w-56')
                    self._labels[spec.label] = ui.label('–').classes('text-sm font-medium')
                    self._captions[spec.label] = ui.label('').classes('text-xs text-grey-7')

    def bind(self, label: str, value_label, caption=None) -> None:
        """Rejestruje etykiety narysowane przez stronę (własny układ)."""
        self._labels[label] = value_label
        if caption is not None:
            self._captions[label] = caption

    def start(self) -> None:
        ui.timer(0.1, self.refresh, once=True)
        ui.timer(self.interval, self.refresh)

    # ------------------------------------------------------------ odświeżanie

    async def refresh(self) -> None:
        now = time.time()
        missing = [spec for spec in self.values
                   if all(mqttclient.cache.value(topic, spec.key) is None
                          for topic in spec.topics)]
        db_values = {}
        if missing:
            columns = db_columns(missing)
            try:
                db_values = await run.io_bound(db.latest, columns)
            except Exception:  # baza może być niedostępna – zostaje broker
                db_values = {}

        for spec in self.values:
            reading = read(spec, db_values, now=now)
            label = self._labels.get(spec.label)
            if label is not None:
                label.text = reading.text
                label.classes(remove='text-grey-6 text-grey-7')
                if reading.stale:
                    label.classes(add='text-grey-6')
            caption = self._captions.get(spec.label)
            if caption is not None:
                caption.text = caption_text(reading)


def mqtt_status_label(interval: float = 5.0):
    """Stopka ze stanem połączenia z brokerem - widać, czy dane są na żywo."""
    label = ui.label(mqttclient.status_text()).classes('text-xs text-grey-7 px-3 pb-2')

    def tick() -> None:
        label.text = mqttclient.status_text()

    ui.timer(interval, tick)
    return label


def caption_text(reading: Reading) -> str:
    if reading.source == 'brak':
        return 'brak danych'
    # niepełna suma to nie to samo co pełna - inaczej moc PV cicho zaniża wynik
    partial = ('' if reading.present == reading.expected
               else f' · tylko {reading.present}/{reading.expected}')
    if reading.source == 'baza':
        return f'z bazy (ostatni kubełek){partial}'
    if reading.age is None:
        return f'broker{partial}'
    if reading.age < 90:
        return f'{reading.age:.0f} s temu{partial}'
    return f'{reading.age / 60:.0f} min temu{partial}'
