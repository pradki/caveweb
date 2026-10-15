"""Aplikacja webowa cave (NiceGUI) – kafelki, wartości bieżące i wykresy."""
__version__ = "0.3"

import asyncio

from nicegui import app, ui

from . import config, fuel_level, furnace_boost, mqttclient
from .pages import home
from .pages import charts
from .pages import temperature
from .pages import battery
from .pages import power
from .pages import energy
from .pages import automations
from .pages import boiler
from .pages import boiler_config
from .pages import boiler_refuel
from .pages import comfort
from .pages import comfort_config
from .pages import pv
from .pages import recuperation
from .pages import relays
from .pages import settings
from .pages import temperatures


@ui.page('/')
def index() -> None:
    ui.navigate.to('/home')


@app.on_startup
def start_mqtt() -> None:
    """Klient MQTT startuje razem z serwerem, już po wczytaniu konfiguracji."""
    mqttclient.start(**config.MQTT)
    asyncio.create_task(fuel_level.publish_loop())
    asyncio.create_task(furnace_boost.watch_loop())
