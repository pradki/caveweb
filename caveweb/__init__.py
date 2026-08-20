"""Aplikacja webowa cave (NiceGUI) – kafelki i wykresy pomiarów."""
__version__ = "0.2"

from nicegui import ui

from .pages import home
from .pages import charts
from .pages import temperature
from .pages import battery
from .pages import power
from .pages import energy


@ui.page('/')
def index() -> None:
    ui.navigate.to('/home')
