# -*- coding: utf-8 -*-
"""Testy deklaracji stron: metadane kotła, zestawy wartości, spójność etykiet.

    python tests/test_pages.py

Nie budujemy interfejsu - sprawdzamy dane, z których strony się składają.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import heating_params, live, topics
from caveweb.pages import boiler, boiler_config, home, pv

# --- metadane parametrów kotła (kopia PARAMS_HEATING) ------------------------

check("wszystkie parametry mają topic i typ",
      all(meta.get('topic') and meta.get('data_type')
          for meta in heating_params.PARAMS.values()))
check("nastawy i czujniki dają razem całość",
      len(heating_params.SETPOINTS) + len(heating_params.SENSORS)
      == len(heating_params.PARAMS))
check("nastawy siedzą pod cave/heating/setpoints/",
      all(meta['topic'].startswith('cave/heating/setpoints/')
          for meta in heating_params.SETPOINTS.values()))
check("czujniki siedzą pod cave/sensors/",
      all(meta['topic'].startswith('cave/sensors/')
          for meta in heating_params.SENSORS.values()))
check("liczbowe nastawy mają sensowny zakres",
      all(meta['min'] < meta['max'] for meta in heating_params.SETPOINTS.values()
          if meta['data_type'] in ('int', 'float')))
check("domyślna wartość mieści się w zakresie",
      all(meta['min'] <= meta['default'] <= meta['max']
          for meta in heating_params.SETPOINTS.values()
          if meta['data_type'] in ('int', 'float') and meta['default'] is not None))
check("temperatura pieca to nastawa 52-72 °C",
      (heating_params.SETPOINTS['furnace_temp_setpoint']['min'],
       heating_params.SETPOINTS['furnace_temp_setpoint']['max']) == (52, 72))

# --- kafelki ekranu głównego --------------------------------------------------

check("kafelek kotła pokazuje temperaturę pieca",
      [spec.topics for spec in home.BOILER_TILE] ==
      [('cave/sensors/temperature/furnace_temp',)])
check("kafelek PV pokazuje sumę PV, SOC i sumę faz",
      [spec.topics for spec in home.PV_TILE] == [
          ('cave/deye/params/pv1_power', 'cave/deye/params/pv2_power'),
          ('cave/deye/params/battery_soc',),
          ('cave/deye/params/load_power_l1', 'cave/deye/params/load_power_l2',
           'cave/deye/params/load_power_l3'),
      ])

# --- wszystkie zestawy wartości ----------------------------------------------

PANELS = {
    'home.BOILER_TILE': home.BOILER_TILE,
    'home.PV_TILE': home.PV_TILE,
    'boiler.FURNACE': boiler.FURNACE,
    'boiler.HOUSE': boiler.HOUSE,
    'boiler.WORK': boiler.WORK,
    'boiler.KEY_SETPOINTS': boiler.KEY_SETPOINTS,
    'pv.PRODUCTION': pv.PRODUCTION,
    'pv.BATTERY': pv.BATTERY,
    'pv.LOAD': pv.LOAD,
    'pv.TODAY': pv.TODAY,
}

for name, values in PANELS.items():
    check(f"{name}: każda pozycja ma topic",
          all(spec.topics and all(t.startswith('cave/') for t in spec.topics)
              for spec in values))
    # etykiety są kluczami w LivePanel - duplikat po cichu zgubiłby wiersz
    labels = [spec.label for spec in values]
    check(f"{name}: etykiety unikalne", len(labels) == len(set(labels)))

check("piec na stronie kotła bierze topic z metadanych",
      boiler.FURNACE[0].topics == (heating_params.PARAMS['furnace_temp_sensor']['topic'],))
check("liczniki przekaźnika czytają today_s",
      [spec.key for spec in boiler.WORK] == ['state', 'today_s', 'state', 'today_s'])
check("czasy pracy formatowane jako czas",
      [spec.kind for spec in boiler.WORK if spec.key == 'today_s'] == ['seconds', 'seconds'])
check("stany przekaźników nie mają awaryjnej kolumny w bazie",
      all(spec.columns == () for spec in boiler.WORK))
check("liczniki falownika wskazują kolumnę _end",
      [spec.columns for spec in pv.TODAY] == [
          ('battery_charge_today_end',),
          ('battery_discharge_today_end',),
          ('load_energy_total_end',),
      ])

# --- strona konfiguracji ------------------------------------------------------

specs = {name: boiler_config.spec_for(name, meta)
         for name, meta in heating_params.SETPOINTS.items()}
check("konfiguracja pokrywa wszystkie nastawy",
      len(specs) == len(heating_params.SETPOINTS))
check("nastawa bool ma kind bool",
      specs['furnace_enable_setpoint'].kind == 'bool')
check("nastawa int ma zero cyfr po kropce",
      specs['furnace_temp_setpoint'].digits == 0)
check("nastawa float ma jedną cyfrę",
      specs['inside_temp_setpoint'].digits == 1)
check("konfiguracja czyta te same topiki co usługa grzewcza",
      all(specs[name].topics == (meta['topic'],)
          for name, meta in heating_params.SETPOINTS.items()))

# --- topiki -------------------------------------------------------------------

check("topics.sensor", topics.sensor('furnace_temp') ==
      'cave/sensors/temperature/furnace_temp')
check("topics.sensor innego rodzaju", topics.sensor('scd30_main_airco2', 'airco2') ==
      'cave/sensors/airco2/scd30_main_airco2')
check("topics.deye", topics.deye('pv1_power') == 'cave/deye/params/pv1_power')
check("topics.relay_status", topics.relay_status('co_fan') ==
      f'cave/relay/{topics.RELAY_MODULE}/co_fan/status')
check("topics.relay_counters", topics.relay_counters('co_feeder') ==
      f'cave/relay/{topics.RELAY_MODULE}/co_feeder/counters')

done()
