"""Testy logiki wykresu: dobór kolumn, sumowanie grup, budowa serii.

Strony nie budujemy (to wymagałoby kontekstu żądania NiceGUI) – tworzymy
instancję bez __init__ i ustawiamy tylko stan przełączników.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytest.importorskip('nicegui', reason='logika strony importuje nicegui')

from caveweb.chartpage import ChartPage, sum_points  # noqa: E402
from caveweb.pages.battery import BatteryPage  # noqa: E402
from caveweb.pages.energy import EnergyPage  # noqa: E402
from caveweb.pages.power import PowerPage  # noqa: E402


def page(cls, minmax=False, group=False) -> ChartPage:
    instance = object.__new__(cls)
    instance.show_minmax = minmax
    instance.group_on = group
    return instance


def names(series):
    return [entry['name'] for entry in series]


def test_columns_gauge_without_minmax():
    assert page(PowerPage).columns() == [
        'pv1_power_avg', 'pv2_power_avg',
        'load_power_l1_avg', 'load_power_l2_avg', 'load_power_l3_avg',
    ]


def test_columns_gauge_with_minmax():
    columns = page(PowerPage, minmax=True).columns()
    assert columns[:3] == ['pv1_power_avg', 'pv1_power_min', 'pv1_power_max']
    assert len(columns) == 15


def test_columns_counter_uses_delta_only():
    assert page(EnergyPage).columns() == ['load_energy_total_delta']
    # licznik nie ma min/max, więc przełącznik nic nie zmienia
    assert page(EnergyPage, minmax=True).columns() == ['load_energy_total_delta']


def test_grouping_replaces_single_lines_with_sums():
    data = {
        'pv1_power_avg': [[1000, 100.0], [2000, 200.0]],
        'pv2_power_avg': [[1000, 10.0], [2000, 20.0]],
        'load_power_l1_avg': [[1000, 1.0]],
        'load_power_l2_avg': [[1000, 2.0]],
        'load_power_l3_avg': [[1000, 3.0]],
    }
    grouped = page(PowerPage, group=True).build_series(data)
    assert names(grouped) == ['PV (1+2)', 'Obciążenie (L1+L2+L3)']
    assert grouped[0]['data'] == [[1000, 110.0], [2000, 220.0]]
    assert grouped[1]['data'] == [[1000, 6.0]]

    single = page(PowerPage).build_series(data)
    assert names(single) == ['PV1', 'PV2', 'L1', 'L2', 'L3']


def test_counter_series_is_bar_and_discharge_goes_below_zero():
    data = {
        'battery_soc_avg': [[1000, 55.0]],
        'battery_charge_total_delta': [[1000, 0.4]],
        'battery_discharge_total_delta': [[1000, 0.3]],
    }
    series = page(BatteryPage).build_series(data)
    kinds = {entry['name']: entry['type'] for entry in series}
    assert kinds == {'SOC': 'line', 'Ładowanie': 'bar', 'Rozładowanie': 'bar'}
    by_name = {entry['name']: entry for entry in series}
    assert by_name['Ładowanie']['data'] == [[1000, 0.4]]
    assert by_name['Rozładowanie']['data'] == [[1000, -0.3]]
    # SOC na osi lewej (0), energia na prawej (1)
    assert by_name['SOC']['yAxisIndex'] == 0
    assert by_name['Ładowanie']['yAxisIndex'] == 1


def test_minmax_adds_dashed_lines():
    data = {
        'battery_soc_avg': [[1000, 55.0]],
        'battery_soc_min': [[1000, 50.0]],
        'battery_soc_max': [[1000, 60.0]],
        'battery_charge_total_delta': [],
        'battery_discharge_total_delta': [],
    }
    series = page(BatteryPage, minmax=True).build_series(data)
    assert names(series)[:3] == ['SOC', 'SOC min', 'SOC max']
    assert series[1]['lineStyle']['type'] == [4, 4]
    assert series[1]['lineStyle']['width'] == 1


def test_sum_points_aligns_on_timestamps():
    assert sum_points([
        [[1, 1.0], [2, 2.0]],
        [[2, 0.5], [3, 3.0]],
    ]) == [[1, 1.0], [2, 2.5], [3, 3.0]]


def test_sum_points_of_nothing():
    assert sum_points([[], []]) == []
