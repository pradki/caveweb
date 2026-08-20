"""Wspólna baza stron z wykresami.

Strona pochodna deklaruje tylko sygnały, osie i opcjonalne grupy sumowania –
cała mechanika (zakresy czasu, min/max, odświeżanie, podpisy) jest tutaj.
"""

from __future__ import annotations

__version__ = "0.2"

from dataclasses import dataclass
from datetime import datetime

from nicegui import app, run, ui

from . import db
from . import config
from .widgets import page_header

# Format etykiet osi czasu zależy od zakresu (składnia formatera ECharts)
AXIS_LABELS = {
    'day':   {'minute': '{HH}:{mm}', 'hour': '{HH}:{mm}', 'day': '{dd}.{MM}'},
    'week':  {'hour': '{HH}:{mm}', 'day': '{dd}.{MM}', 'month': '{dd}.{MM}'},
    'month': {'hour': '{dd}.{MM}', 'day': '{dd}.{MM}', 'month': '{dd}.{MM}'},
    'year':  {'day': '{dd}.{MM}', 'month': '{MMM}', 'year': '{yyyy}'},
}

# Rodzaje sygnałów: gauge rysujemy linią z kolumn _avg/_min/_max,
# counter słupkami z kolumny _delta (przyrost w kubełku).
GAUGE = 'gauge'
COUNTER = 'counter'


@dataclass(frozen=True)
class Signal:
    name: str                    # prefiks kolumn w bazie, np. 'inside_temp'
    label: str
    color: str
    kind: str = GAUGE
    unit: str = ''
    axis: int = 0                # indeks osi Y
    group: str | None = None     # klucz grupy dla przełącznika sumowania
    sign: int = 1               # -1 rysuje słupki pod osią (np. rozładowanie)


@dataclass(frozen=True)
class Group:
    key: str
    label: str
    color: str
    members: tuple[str, ...]     # nazwy sygnałów wchodzących do sumy
    unit: str = ''
    axis: int = 0


class ChartPage:
    """Strona z jednym wykresem i przełącznikami zakresu."""

    title = 'Wykres'
    back = '/charts'
    key = 'chart'                       # prefiks kluczy w app.storage.user
    signals: list = []
    groups: list = []
    y_axes: list = []
    has_minmax = True
    group_label = 'grupuj'

    def __init__(self) -> None:
        self.range_key = app.storage.user.get(f'{self.key}_range', db.DEFAULT_RANGE)
        if self.range_key not in db.RANGES:
            self.range_key = db.DEFAULT_RANGE
        self.show_minmax = app.storage.user.get(f'{self.key}_minmax', False)
        self.group_on = app.storage.user.get(f'{self.key}_group', False)
        self.chart = None
        self.info = None
        self.stats_container = None

    # ---------------------------------------------------------------- budowa

    def build(self) -> None:
        page_header(self.title, back=self.back)

        with ui.column().classes('w-full p-2 gap-2'):
            with ui.row().classes('w-full items-center gap-4'):
                ui.toggle({key: rng.label for key, rng in db.RANGES.items()},
                          value=self.range_key,
                          on_change=self.on_range).props('dense')
                if self.has_minmax:
                    ui.switch('min / max', value=self.show_minmax,
                              on_change=self.on_minmax)
                if self.groups:
                    ui.switch(self.group_label, value=self.group_on,
                              on_change=self.on_group)
                ui.space()
                self.info = ui.label('').classes('text-xs text-grey-6')

            self.chart = ui.echart(self.options()).classes('w-full').style('height: 56vh')
            self.stats_container = ui.row().classes('w-full gap-6 px-2 flex-wrap')

        ui.timer(0.1, self.refresh, once=True)
        ui.timer(config.REFRESH_SECONDS, self.refresh)

    def options(self) -> dict:
        """Bazowa konfiguracja wykresu (bez danych)."""
        rng = db.RANGES[self.range_key]
        now = datetime.now().timestamp()
        y_axes = []
        for index, override in enumerate(self.y_axes or [{}]):
            axis = {
                'type': 'value',
                'scale': True,
                'splitLine': {'show': index == 0,
                              'lineStyle': {'color': '#37474f'}},
            }
            if index:
                axis['position'] = 'right'
            axis.update(override)
            y_axes.append(axis)
        return {
            'animation': False,
            'backgroundColor': 'transparent',
            'textStyle': {'color': '#cfd8dc'},
            'grid': {'left': 56, 'right': 56, 'top': 34, 'bottom': 30},
            'legend': {'textStyle': {'color': '#cfd8dc'}, 'type': 'scroll'},
            'tooltip': {'trigger': 'axis'},
            'dataZoom': [{'type': 'inside'}],
            'xAxis': {
                'type': 'time',
                'min': int((now - rng.span.total_seconds()) * 1000),
                'max': int(now * 1000),
                'axisLabel': {'formatter': AXIS_LABELS[self.range_key],
                              'hideOverlap': True},
                'splitLine': {'show': False},
            },
            'yAxis': y_axes,
            'series': [],
        }

    # -------------------------------------------------------------- zdarzenia

    def on_range(self, event) -> None:
        self.range_key = event.value
        app.storage.user[f'{self.key}_range'] = self.range_key
        ui.timer(0.01, self.refresh, once=True)

    def on_minmax(self, event) -> None:
        self.show_minmax = event.value
        app.storage.user[f'{self.key}_minmax'] = self.show_minmax
        ui.timer(0.01, self.refresh, once=True)

    def on_group(self, event) -> None:
        self.group_on = event.value
        app.storage.user[f'{self.key}_group'] = self.group_on
        ui.timer(0.01, self.refresh, once=True)

    # ------------------------------------------------------------ odświeżanie

    def columns(self) -> list[str]:
        """Kolumny potrzebne przy obecnych ustawieniach przełączników."""
        columns = []
        for signal in self.signals:
            if signal.kind == COUNTER:
                columns.append(f'{signal.name}_delta')
                continue
            columns.append(f'{signal.name}_avg')
            if self.show_minmax:
                columns += [f'{signal.name}_min', f'{signal.name}_max']
        return columns

    async def refresh(self) -> None:
        rng = db.RANGES[self.range_key]
        gauges = [s.name for s in self.signals if s.kind == GAUGE]
        try:
            data = await run.io_bound(db.series, self.columns(), rng)
            current = await run.io_bound(db.latest, [f'{n}_avg' for n in gauges])
        except Exception as error:  # baza może być chwilowo niedostępna
            if self.info is not None:
                self.info.text = f'błąd odczytu bazy: {error}'
            return

        options = self.options()
        options['series'] = self.build_series(data)
        if self.chart is not None:
            self.chart.options.clear()
            self.chart.options.update(options)
            self.chart.update()

        self.update_stats(data, current)

    # -------------------------------------------------------------- serie

    def build_series(self, data) -> list:
        series = []
        grouped = self.grouped_names() if self.group_on else set()

        for signal in self.signals:
            if signal.kind == COUNTER:
                series.append(self.bar(signal, data.get(f'{signal.name}_delta', [])))
            elif signal.name not in grouped:
                series += self.lines(signal.label, signal.color, signal.axis, {
                    suffix: data.get(f'{signal.name}_{suffix}', [])
                    for suffix in ('avg', 'min', 'max')
                })

        if self.group_on:
            for group in self.groups:
                summed = {
                    suffix: sum_points([data.get(f'{name}_{suffix}', [])
                                        for name in group.members])
                    for suffix in ('avg', 'min', 'max')
                }
                series += self.lines(group.label, group.color, group.axis, summed)
        return series

    def lines(self, label: str, color: str, axis: int, points: dict) -> list:
        """Linia średniej i – gdy włączone – cienkie linie min/max."""
        series = [{
            'name': label,
            'type': 'line',
            'yAxisIndex': axis,
            'data': points.get('avg', []),
            'showSymbol': False,
            'lineStyle': {'width': 2, 'color': color},
            'itemStyle': {'color': color},
        }]
        if self.show_minmax:
            for suffix, dash in (('min', [4, 4]), ('max', [2, 4])):
                series.append({
                    'name': f'{label} {suffix}',
                    'type': 'line',
                    'yAxisIndex': axis,
                    'data': points.get(suffix, []),
                    'showSymbol': False,
                    'lineStyle': {'width': 1, 'color': color,
                                  'opacity': 0.5, 'type': dash},
                    'itemStyle': {'color': color},
                })
        return series

    def bar(self, signal: Signal, points: list) -> dict:
        """Słupki z przyrostu licznika; sign=-1 odbija je pod oś."""
        return {
            'name': signal.label,
            'type': 'bar',
            'yAxisIndex': signal.axis,
            'data': [[ts, round(value * signal.sign, 3)] for ts, value in points],
            'barMaxWidth': 14,
            'itemStyle': {'color': signal.color},
        }

    def grouped_names(self) -> set:
        names = set()
        for group in self.groups:
            names.update(group.members)
        return names

    # -------------------------------------------------------------- podpisy

    def update_stats(self, data, current) -> None:
        """Podpisy pod wykresem – dla gauge wartości, dla licznika suma."""
        entries = []
        grouped = self.grouped_names() if self.group_on else set()

        for signal in self.signals:
            if signal.kind == COUNTER:
                points = data.get(f'{signal.name}_delta', [])
                total = sum(value for _, value in points)
                text = f'suma {total:.2f} {signal.unit}'.strip()
                entries.append((signal.label, signal.color, text if points else 'brak danych'))
            elif signal.name not in grouped:
                points = data.get(f'{signal.name}_avg', [])
                now_value = current.get(f'{signal.name}_avg')
                entries.append((signal.label, signal.color,
                                gauge_text(points, now_value, signal.unit)))

        if self.group_on:
            for group in self.groups:
                points = sum_points([data.get(f'{name}_avg', []) for name in group.members])
                entries.append((group.label, group.color,
                                gauge_text(points, None, group.unit)))

        points_total = sum(len(values) for values in data.values())
        if self.stats_container is not None:
            self.stats_container.clear()
            with self.stats_container:
                for label, color, text in entries:
                    with ui.row().classes('items-center gap-2'):
                        ui.icon('circle').style(f'color: {color}').classes('text-xs')
                        ui.label(label).classes('text-sm')
                        ui.label(text).classes('text-sm text-grey-5')

        if self.info is not None:
            stamp = datetime.now().strftime('%H:%M:%S')
            self.info.text = f'{points_total} punktów · odczyt {stamp}'


def sum_points(series_list: list) -> list:
    """Suma serii po wspólnych znacznikach czasu (kubełki są te same)."""
    accumulator: dict[int, float] = {}
    for points in series_list:
        for ts, value in points:
            accumulator[ts] = accumulator.get(ts, 0.0) + value
    return [[ts, round(accumulator[ts], 2)] for ts in sorted(accumulator)]


def gauge_text(points: list, now_value, unit: str) -> str:
    st = db.stats(points)
    parts = []
    if now_value is not None and now_value[0] is not None:
        parts.append(f'teraz {now_value[0]:.1f} {unit}'.strip())
    elif st['last'] is not None:
        parts.append(f"teraz {st['last']:.1f} {unit}".strip())
    if st['avg'] is not None:
        parts += [f"śr {st['avg']:.1f}", f"min {st['min']:.1f}", f"max {st['max']:.1f}"]
    return '  ·  '.join(parts) if parts else 'brak danych'
