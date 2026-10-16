# -*- coding: utf-8 -*-
"""Panel komfortu – jeden ekran z tym, co niezbędne do pracy na co dzień
(temperatura, stan, zawór, aktualna/następna reguła); konfiguracja (harmonogram
dzień/noc, nieobecność, strojenie zaworu) jest głębiej, na `/comfort/config` -
ten sam podział co `/boiler` + `/boiler/config`, żeby ten ekran nie rozrastał
się formularzami rzadko ruszanych nastaw (patrz założenia UI - "panel czytelny,
tylko to co niezbędne do działania").

Wszystko, co silnik SAM zdecydował (`effective_setpoint`, `current_rule`,
`next_rule`...) czytamy wprost z `cave/comfort` - ta strona nie liczy priorytetu
nieobecność/dzień/noc samodzielnie (comfort-controller README, sekcja
"Absence mode": "Interfejs ma prezentować decyzję silnika, a nie samodzielnie
obliczać temperaturę"). Jedyny wyjątek to temperatura wewnętrzna i podłogi -
czytane WPROST z czujników (`cave/sensors/temperature/*`), nie z `temp_current`
na `cave/comfort` - niezależnie od tego, czy comfort-controller akurat działa
(ten sam powód co kafelek Komfortu na `/home`)."""

from __future__ import annotations
__version__ = "0.3"

from datetime import datetime

from nicegui import ui

from .. import live, mqttclient, topics
from ..widgets import page_header

TOPIC = topics.COMFORT_TOPIC


def format_until(iso_str) -> str:
    """"do 19:00" dziś, "do 2026-10-20 08:00" gdy inny dzień - silnik zawsze
    wysyła pełną datę+godzinę (patrz comfort_controller.py:_publish_status),
    strona skraca wyświetlanie tylko gdy to i tak dzisiaj."""
    if not iso_str:
        return ''
    try:
        dt = datetime.fromisoformat(iso_str)
    except (TypeError, ValueError):
        return ''
    if dt.date() == datetime.now().date():
        return f'do {dt.strftime("%H:%M")}'
    return f'do {dt.strftime("%Y-%m-%d %H:%M")}'


def _mode_label(interval: float = 5.0):
    """Tryb pracy w nagłówku strony (założenia UI, sekcja "Nagłówek")."""
    label = ui.label('').classes('text-sm px-3 text-blue-2')

    def refresh() -> None:
        label.text = mqttclient.cache.value(TOPIC, 'current_rule') or ''

    ui.timer(0.1, refresh, once=True)
    ui.timer(interval, refresh)
    return label


def _card(label: str, icon: str, classes: str = 'w-44') -> ui.card:
    """Powłoka karty, ten sam wygląd co `live.LivePanel.render_cards()` -
    reszta tej strony miesza karty bindowane przez LivePanel (Temperatura,
    Wartość zadana, Temperatura podłogi) z kartami rysowanymi ręcznie (Stan,
    Otwarcie zaworu - niepasujące do prostego "jedno pole -> jedna liczba"),
    i obie mają wyglądać tak samo."""
    card = ui.card().classes(f'{classes} p-3 gap-1')
    with card:
        with ui.row().classes('items-center gap-1 no-wrap'):
            if icon:
                ui.icon(icon).classes('text-sm text-blue-4')
            ui.label(label).classes('text-xs text-grey-5')
    return card


def _state_card() -> None:
    """"Stan": duży emoji+tekst wg `hvac_state` - która gałąź bang-bang jest
    aktywna, NIE stan pompy (ta chodzi prawie zawsze - patrz comfort-controller
    README, "The pump"). Podpis pod spodem (wiek odczytu) nie tylko informuje
    o nieaktualności (jak reszta kart) - bez niego ta karta miała tylko dwa
    wiersze zamiast trzech jak sąsiadki, więc "Stan" wizualnie siedział niżej."""
    card = _card('Stan', 'local_fire_department')
    with card:
        state_label = ui.label('–').classes('text-2xl font-medium')
        caption_label = ui.label('').classes('text-xs text-grey-7')

    def refresh() -> None:
        value = mqttclient.cache.value(TOPIC, 'hvac_state')
        state_label.text = {'grzeje': '♨️ grzeje', 'czeka': '💤 czeka'}.get(value, '–')
        age = mqttclient.cache.age(TOPIC)
        if age is None:
            caption_label.text = 'brak danych'
        elif age > live.STALE_SECONDS:
            caption_label.text = 'nieaktualne'
        else:
            caption_label.text = f'{age:.0f} s temu' if age < 90 else f'{age / 60:.0f} min temu'

    ui.timer(0.1, refresh, once=True)
    ui.timer(5.0, refresh)


def _valve_card() -> None:
    """"Otwarcie zaworu": wartość + prosty pasek (założenia UI, sekcja C -
    "preferowane duże wartości procentowe... oraz proste wskaźniki paskowe").
    Jedna wspólna wartość (cel `mixing_valve`), nie rozbita na dwa osobne pola
    "ciepło"/"dogrzewanie" z pierwotnych założeń - silnik today/night dzieli
    bang-bang na low/high per pora dnia, nie na dwa niezależnie czytane kanały
    (patrz comfort-controller docstring), więc dwa pola pokazywałyby to samo
    rozbite bez potrzeby; szczegółowe progi dzień/noc są w `/comfort/config`."""
    card = _card('Otwarcie zaworu', 'tune')
    with card:
        valve_label = ui.label('–').classes('text-2xl font-medium')
        valve_bar = ui.linear_progress(value=0, show_value=False) \
            .classes('w-full').props('rounded color=blue-4 size=8px')
        valve_caption = ui.label('').classes('text-xs text-grey-7')

    def refresh() -> None:
        value = mqttclient.cache.value(TOPIC, 'mixing_valve')
        if value is None:
            valve_label.text = 'Brak danych'
            valve_bar.value = 0.0
            valve_caption.text = ''
            return
        value = float(value)
        valve_label.text = f'{value:.0f}%'
        valve_bar.value = max(0.0, min(1.0, value / 100.0))
        age = mqttclient.cache.age(TOPIC)
        valve_caption.text = 'nieaktualne' if age is not None and age > live.STALE_SECONDS else ''

    ui.timer(0.1, refresh, once=True)
    ui.timer(5.0, refresh)


def _rule_card() -> None:
    """"Aktualna reguła" (założenia UI, sekcja D) - nazwa reguły, jej
    temperatura i do kiedy obowiązuje, wprost z `cave/comfort` (patrz docstring
    modułu)."""
    card = _card('Aktualna reguła', 'rule', classes='w-full')
    with card:
        name_label = ui.label('–').classes('text-lg font-medium')
        detail_label = ui.label('').classes('text-sm text-grey-7')

    def refresh() -> None:
        name = mqttclient.cache.value(TOPIC, 'current_rule')
        temp = mqttclient.cache.value(TOPIC, 'effective_setpoint')
        until = mqttclient.cache.value(TOPIC, 'current_rule_until')
        name_label.text = name or '–'
        parts = []
        if temp is not None:
            parts.append(f'{float(temp):.1f} °C')
        until_text = format_until(until)
        if until_text:
            parts.append(until_text)
        detail_label.text = ' · '.join(parts)

    ui.timer(0.1, refresh, once=True)
    ui.timer(5.0, refresh)


def _next_change_card() -> None:
    """"Następna zmiana" (założenia UI, sekcja E) - "Brak zaplanowanej zmiany"
    to w praktyce tylko stan przejściowy (dzień/noc zmieniają się zawsze co
    jakiś czas) albo brak danych z silnika, nie normalny stan ustalony."""
    card = _card('Następna zmiana', 'update', classes='w-full')
    with card:
        when_label = ui.label('').classes('text-sm text-grey-7')
        rule_label = ui.label('–').classes('text-lg font-medium')

    def refresh() -> None:
        rule = mqttclient.cache.value(TOPIC, 'next_rule')
        at = mqttclient.cache.value(TOPIC, 'next_change_at')
        temp = mqttclient.cache.value(TOPIC, 'next_temp')
        if not rule or not at:
            when_label.text = ''
            rule_label.text = 'Brak zaplanowanej zmiany'
            return
        when_label.text = format_until(at)
        temp_text = f' → {float(temp):.1f} °C' if temp is not None else ''
        rule_label.text = f'{rule}{temp_text}'

    ui.timer(0.1, refresh, once=True)
    ui.timer(5.0, refresh)


# Trzy wartości, dla których zwykły tekstowy format (z szarzeniem przy
# nieaktualności i podpisem "x s temu"/"brak danych") wystarcza bez niczego
# dodatkowego - LivePanel.bind() robi to za darmo, patrz live.py.
TOP_VALUES = [
    live.value_of('Temperatura', topics.sensor('inside_temp'), unit='°C', digits=1),
    live.Value('Wartość zadana', (TOPIC,), key='effective_setpoint', unit='°C', digits=1, columns=()),
    live.value_of('Temperatura podłogi', topics.sensor('floor_temp'), unit='°C', digits=1),
]


@ui.page('/comfort')
def comfort() -> None:
    page_header('Panel komfortu', back=True, right=_mode_label)

    panel = live.LivePanel(TOP_VALUES)
    temp_spec, setpoint_spec, floor_spec = TOP_VALUES

    with ui.column().classes('w-full max-w-4xl mx-auto p-3 gap-3'):
        with ui.row().classes('w-full gap-3 flex-wrap justify-center'):
            card = _card(temp_spec.label, 'thermostat')
            with card:
                value_label = ui.label('–').classes('text-2xl font-medium')
                caption_label = ui.label('').classes('text-xs text-grey-7')
            panel.bind(temp_spec.label, value_label, caption_label)

            _state_card()

            card = _card(setpoint_spec.label, 'flag')
            with card:
                value_label = ui.label('–').classes('text-2xl font-medium')
                caption_label = ui.label('').classes('text-xs text-grey-7')
            panel.bind(setpoint_spec.label, value_label, caption_label)

            _valve_card()

            card = _card(floor_spec.label, 'device_thermostat')
            with card:
                value_label = ui.label('–').classes('text-2xl font-medium')
                caption_label = ui.label('').classes('text-xs text-grey-7')
            panel.bind(floor_spec.label, value_label, caption_label)

        with ui.column().classes('w-full gap-3'):
            _rule_card()
            _next_change_card()

        with ui.row().classes('w-full gap-3 justify-center'):
            ui.button('Harmonogram', icon='schedule',
                      on_click=lambda: ui.navigate.to('/comfort/config')).props('outline')
            ui.button('Nieobecność', icon='flight_takeoff',
                      on_click=lambda: ui.navigate.to('/comfort/config')).props('outline')
            ui.button('Konfiguracja', icon='tune',
                      on_click=lambda: ui.navigate.to('/comfort/config')).props('outline')

    panel.start()
    live.mqtt_status_label()
