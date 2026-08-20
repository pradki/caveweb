"""Wspólne elementy interfejsu: nagłówek strony, kafelek, nagłówek sekcji."""

from __future__ import annotations
__version__ = "0.2"

from typing import Callable

from nicegui import ui

# Kafelek ma być duży – aplikacja chodzi na panelu dotykowym Raspberry Pi.
# Wysokość minimalna, nie stała: kafelki z wartościami bieżącymi są wyższe.
TILE_CLASSES = (
    'w-44 min-h-44 cursor-pointer items-center justify-center '
    'transition-transform hover:scale-105'
)


def page_header(title: str, back: str | None = None) -> None:
    """Górny pasek z opcjonalnym przyciskiem powrotu."""
    with ui.header().classes('bg-blue-900 text-white items-center'):
        if back is not None:
            ui.button(icon='arrow_back', on_click=lambda: ui.navigate.to(back)) \
                .props('flat round color=white dense')
        ui.label(title).classes('text-lg font-medium')


def tile(icon: str, title: str, target: str | None = None,
         subtitle: str = '', on_click: Callable | None = None,
         body: Callable | None = None) -> ui.card:
    """Kafelek nawigacyjny.

    `body` to funkcja rysująca wnętrze kafelka (u nas: wartości bieżące).
    Bez `target` i `on_click` kafelek jest wyszarzony i nic nie robi.
    """
    enabled = bool(target or on_click)
    card = ui.card().classes(TILE_CLASSES + ('' if enabled else ' opacity-40'))
    with card:
        ui.icon(icon).classes('text-4xl text-blue-4')
        ui.label(title).classes('text-base font-medium text-center')
        if body is not None:
            body()
        if subtitle:
            ui.label(subtitle).classes('text-xs text-grey-6 text-center')
    if on_click is not None:
        card.on('click', on_click)
    elif target is not None:
        card.on('click', lambda: ui.navigate.to(target))
    return card


def tile_grid():
    """Kontener układający kafelki w responsywną siatkę."""
    return ui.row().classes('w-full justify-center gap-4 p-4')


def section(title: str) -> None:
    """Nagłówek sekcji na stronie szczegółowej."""
    ui.label(title).classes('text-sm uppercase tracking-wide text-grey-6 mt-2')
