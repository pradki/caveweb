"""Ekran główny – kafelki najwyższego poziomu."""
__version__ = "0.1"

from nicegui import ui

from ..widgets import page_header, tile, tile_grid


@ui.page('/home')
def home() -> None:
    page_header('cave')
    with tile_grid():
        tile('insert_chart', 'Wykresy', target='/charts')
