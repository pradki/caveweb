"""Aplikacja webowa cave (NiceGUI) – kafelki, wartości bieżące i wykresy."""
__version__ = "0.3"

from nicegui import app, ui

from . import config, mqttclient
from .pages import home
from .pages import charts
from .pages import temperature
from .pages import battery
from .pages import power
from .pages import energy
from .pages import boiler
from .pages import boiler_config
from .pages import pv


@ui.page('/')
def index() -> None:
    ui.navigate.to('/home')


@app.on_startup
def start_mqtt() -> None:
    """Klient MQTT startuje razem z serwerem, już po wczytaniu konfiguracji."""
    mqttclient.start(**config.MQTT)
