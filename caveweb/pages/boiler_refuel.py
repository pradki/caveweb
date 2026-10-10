# -*- coding: utf-8 -*-
"""Tankowanie podajnika – zapisuje ile węgla zasypano, kiedy, i stan licznika
`total_s` podajnika w tym momencie (patrz `refuels.py` po dlaczego).
"""

from __future__ import annotations
__version__ = "0.1"

from nicegui import app, ui

from .. import fuel_level, mqttclient, refuels, topics
from ..widgets import page_header

STORAGE_BAG_SIZE_KEY = 'refuel_bag_size_kg'
FEEDER_COUNTERS_TOPIC = topics.relay_counters('co_feeder')


def current_feeder_total_s() -> float | None:
    return mqttclient.cache.value(FEEDER_COUNTERS_TOPIC, 'total_s')


def format_hours(seconds: float) -> str:
    hours = seconds / 3600.0
    return f'{hours:.1f} h' if hours < 100 else f'{hours:.0f} h'


@ui.page('/boiler/refuel')
def refuel() -> None:
    page_header('Tankowanie', back='/boiler')

    last_bag_size = app.storage.user.get(STORAGE_BAG_SIZE_KEY, 25)

    with ui.column().classes('w-full p-3 gap-3 max-w-md'):
        prev = refuels.last()
        if prev is not None:
            with ui.card().classes('w-full p-3 gap-1'):
                ui.label('Ostatnie tankowanie').classes('text-xs text-grey-5')
                ui.label(
                    f'{prev.timestamp:%Y-%m-%d %H:%M} · {prev.bags} x {prev.bag_size_kg} kg '
                    f'= {prev.total_kg:.0f} kg'
                    + ('' if prev.filled_to_full else ' (nie do pełna)')
                ).classes('text-sm')
                current_s = current_feeder_total_s()
                if current_s is not None and prev.feeder_total_s is not None:
                    elapsed = max(0.0, current_s - prev.feeder_total_s)
                    coef = refuels.coefficient_for(prev.bag_size_kg)
                    note = f'podajnik pracował {format_hours(elapsed)} od tamtej pory'
                    if coef:
                        note += f' · przy {coef:.0f} s/kg to ok. {elapsed / coef:.0f} kg'
                    ui.label(note).classes('text-xs text-grey-6')
                elif current_s is None:
                    ui.label('brak danych z licznika podajnika (broker?)') \
                        .classes('text-xs text-grey-6')

        bags = ui.number('Ilość worków', value=1, min=1, max=10, step=1,
                         format='%.0f').classes('w-full')
        bag_size_switch = ui.switch('Worki 25 kg (wyłączone = worki 20 kg)',
                                    value=(last_bag_size == 25)).classes('w-full')
        full_switch = ui.switch('Zasypano do pełna', value=True).classes('w-full')

        summary = ui.label('').classes('text-base font-medium')

        def update_summary() -> None:
            size = 25 if bag_size_switch.value else 20
            count = bags.value or 0
            summary.text = f'Zasypano: {count:.0f} x {size} kg = {count * size:.0f} kg'

        bags.on_value_change(lambda _: update_summary())
        bag_size_switch.on_value_change(lambda _: update_summary())
        update_summary()

        def confirm() -> None:
            size = 25 if bag_size_switch.value else 20
            app.storage.user[STORAGE_BAG_SIZE_KEY] = size
            record = refuels.append(
                bags=int(bags.value or 0),
                bag_size_kg=size,
                filled_to_full=full_switch.value,
                feeder_total_s=current_feeder_total_s(),
            )
            # Nie czekamy na godzinny cykl fuel_level.publish_loop() - świeże
            # tankowanie od razu zmienia szacunek, niech broker to zobaczy teraz.
            fuel_level.publish_once()
            ui.notify(
                f'Zapisano: {record.total_kg:.0f} kg ({record.timestamp:%Y-%m-%d %H:%M})',
                type='positive')
            ui.timer(1.5, lambda: ui.navigate.to('/boiler'), once=True)

        ui.button('Zatwierdź', icon='check', on_click=confirm) \
            .props('color=primary').classes('w-full')
