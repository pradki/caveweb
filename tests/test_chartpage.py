# -*- coding: utf-8 -*-
"""Testy logiki wykresu - bez pytest i bez uruchamiania serwera.

    python tests/test_chartpage.py

Strony nie budujemy (to wymagałoby kontekstu żądania NiceGUI) - tworzymy
instancję bez __init__ i ustawiamy tylko stan przełączników. Gdy nicegui nie
jest zainstalowane, podstawiamy atrapę: sprawdzamy liczenie serii, nie interfejs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb.chartpage import sum_points
from caveweb.pages.battery import BatteryPage
from caveweb.pages.energy import EnergyPage
from caveweb.pages.power import PowerPage
from caveweb.pages.temperature import TemperaturePage


def page(cls, minmax=False, group=False):
    instance = object.__new__(cls)
    instance.show_minmax = minmax
    instance.group_on = group
    return instance


def names(series):
    return [entry['name'] for entry in series]


# 1. dobór kolumn dla sygnałów typu gauge
check("gauge bez min/max czyta tylko _avg", page(PowerPage).columns() == [
    'pv1_power_avg', 'pv2_power_avg',
    'load_power_l1_avg', 'load_power_l2_avg', 'load_power_l3_avg',
])
columns = page(PowerPage, minmax=True).columns()
check("gauge z min/max czyta trzy kolumny na sygnał", len(columns) == 15)
check("kolejność kolumn avg/min/max",
      columns[:3] == ['pv1_power_avg', 'pv1_power_min', 'pv1_power_max'])

# 2. licznik ma tylko _delta, przełącznik min/max nic nie zmienia
check("licznik czyta _delta", page(EnergyPage).columns() == ['load_energy_total_delta'])
check("licznik ignoruje min/max",
      page(EnergyPage, minmax=True).columns() == ['load_energy_total_delta'])

# 3. grupowanie zamienia pojedyncze linie na sumy
data = {
    'pv1_power_avg': [[1000, 100.0], [2000, 200.0]],
    'pv2_power_avg': [[1000, 10.0], [2000, 20.0]],
    'load_power_l1_avg': [[1000, 1.0]],
    'load_power_l2_avg': [[1000, 2.0]],
    'load_power_l3_avg': [[1000, 3.0]],
}
single = page(PowerPage).build_series(data)
check("bez grupowania pięć linii", names(single) == ['PV1', 'PV2', 'L1', 'L2', 'L3'])
grouped = page(PowerPage, group=True).build_series(data)
check("z grupowaniem dwie linie",
      names(grouped) == ['PV (1+2)', 'Obciążenie (L1+L2+L3)'])
check("suma PV po znacznikach czasu", grouped[0]['data'] == [[1000, 110.0], [2000, 220.0]])
check("suma faz", grouped[1]['data'] == [[1000, 6.0]])

# 4. liczniki jako słupki, rozładowanie pod osią
data = {
    'battery_soc_avg': [[1000, 55.0]],
    'battery_charge_total_delta': [[1000, 0.4]],
    'battery_discharge_total_delta': [[1000, 0.3]],
}
series = {entry['name']: entry for entry in page(BatteryPage).build_series(data)}
check("SOC linią", series['SOC']['type'] == 'line')
check("ładowanie słupkiem", series['Ładowanie']['type'] == 'bar')
check("ładowanie dodatnie", series['Ładowanie']['data'] == [[1000, 0.4]])
check("rozładowanie pod osią", series['Rozładowanie']['data'] == [[1000, -0.3]])
check("SOC na osi lewej", series['SOC']['yAxisIndex'] == 0)
check("energia na osi prawej", series['Ładowanie']['yAxisIndex'] == 1)

# 5. min/max dokłada cienkie linie przerywane
data = {
    'battery_soc_avg': [[1000, 55.0]],
    'battery_soc_min': [[1000, 50.0]],
    'battery_soc_max': [[1000, 60.0]],
    'battery_charge_total_delta': [],
    'battery_discharge_total_delta': [],
}
series = page(BatteryPage, minmax=True).build_series(data)
check("min/max dokłada dwie serie", names(series)[:3] == ['SOC', 'SOC min', 'SOC max'])
check("linia min jest przerywana", series[1]['lineStyle']['type'] == [4, 4])
check("linia min jest cieńsza", series[1]['lineStyle']['width'] == 1)

# 6. brak danych nie wysypuje budowy serii
empty = page(TemperaturePage).build_series({})
check("pusty słownik danych -> puste serie",
      all(entry['data'] == [] for entry in empty) and len(empty) == len(TemperaturePage.signals))

# 7. sumowanie po znacznikach czasu
check("sum_points scala po ts", sum_points([
    [[1, 1.0], [2, 2.0]],
    [[2, 0.5], [3, 3.0]],
]) == [[1, 1.0], [2, 2.5], [3, 3.0]])
check("sum_points z pustych serii", sum_points([[], []]) == [])

done()
