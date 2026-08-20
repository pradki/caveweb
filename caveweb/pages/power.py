"""Wykres mocy: panele PV i obciążenie faz."""

from __future__ import annotations

__version__ = "0.1"

from nicegui import ui

from ..chartpage import ChartPage, Group, Signal


class PowerPage(ChartPage):
    title = 'Moc'
    key = 'power'
    y_axes = [{'name': 'W'}]
    group_label = 'sumuj PV / fazy'
    signals = [
        Signal('pv1_power', 'PV1', '#ffd54f', unit='W', group='pv'),
        Signal('pv2_power', 'PV2', '#ffb300', unit='W', group='pv'),
        Signal('load_power_l1', 'L1', '#4fc3f7', unit='W', group='load'),
        Signal('load_power_l2', 'L2', '#7986cb', unit='W', group='load'),
        Signal('load_power_l3', 'L3', '#ba68c8', unit='W', group='load'),
    ]
    # Przełącznik zamienia pojedyncze linie na dwie sumy
    groups = [
        Group('pv', 'PV (1+2)', '#ffca28',
              ('pv1_power', 'pv2_power'), unit='W'),
        Group('load', 'Obciążenie (L1+L2+L3)', '#4dd0e1',
              ('load_power_l1', 'load_power_l2', 'load_power_l3'), unit='W'),
    ]


@ui.page('/charts/power')
def power() -> None:
    PowerPage().build()
