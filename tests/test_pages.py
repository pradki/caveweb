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

from caveweb import fuel_level, heating_params, live, topics
from caveweb.pages import boiler, boiler_config, comfort, home, pv, recuperation, temperatures

# --- każda strona musi być zaimportowana w caveweb/__init__.py ---------------
# Samo istnienie pages/foo.py nic nie rejestruje - @ui.page tylko dekoruje
# funkcję, a ta musi się wykonać raz przy starcie. caveweb/__init__.py robi to
# jawnym importem na nazwę; strona pominięta tam odpowiada 404 mimo że kod
# jest poprawny i wszystkie inne testy przechodzą (tak jak tutaj - dokładnie
# ten gap sprawił, że /temperatures wróciło 404 po wdrożeniu).
_pages_dir = Path(__file__).resolve().parent.parent / 'caveweb' / 'pages'
_page_modules = {p.stem for p in _pages_dir.glob('*.py') if p.stem != '__init__'}
_init_source = (Path(__file__).resolve().parent.parent / 'caveweb' / '__init__.py').read_text(encoding='utf-8')
_imported = {name for name in _page_modules if f'import {name}' in _init_source}
check("każdy moduł w pages/ jest zaimportowany w caveweb/__init__.py",
      _page_modules == _imported)

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
check("kafelek temperatur na ekranie głównym pokazuje zewnątrz i wewnątrz",
      [spec.topics for spec in home.TEMPERATURES_TILE] == [
          ('cave/sensors/temperature/outside_temp',),
          ('cave/sensors/temperature/inside_temp',),
      ])
check("kafelek komfortu: temperatura wewnętrzna i podłogi, wprost z czujników",
      [(spec.topics, spec.key) for spec in home.COMFORT_TILE] == [
          (('cave/sensors/temperature/inside_temp',), 'value'),
          (('cave/sensors/temperature/floor_temp',), 'value'),
      ])
check("kafelek rekuperacji: wilgotność i CO2 z cave/comfort",
      [(spec.topics, spec.key) for spec in home.RECUPERATION_TILE] == [
          ((topics.COMFORT_TOPIC,), 'humidity'),
          ((topics.COMFORT_TOPIC,), 'co2'),
      ])

# --- strona /temperatures ------------------------------------------------------

check("10 czujników, bez duplikatów nazw",
      len(temperatures.SENSORS) == 10
      and len({name for name, _ in temperatures.SENSORS}) == 10)
check("etykiety też unikalne (klucze LivePanel.bind)",
      len({label for _, label in temperatures.SENSORS}) == 10)
check("LABELS to po prostu odwrotność SENSORS",
      temperatures.LABELS == dict(temperatures.SENSORS))
check("każdy czujnik ma kolor przypisany (lista kolorów >= liczby czujników)",
      len(temperatures.COLORS) >= len(temperatures.SENSORS))
check("wszystkie nazwy odpowiadają topicom cave/sensors/temperature/*",
      all(topics.sensor(name) == f'cave/sensors/temperature/{name}'
          for name, _ in temperatures.SENSORS))

# strona wykresu filtruje nieznane/puste nazwy z query stringa, zamiast
# budować Signal z czegokolwiek, co ktoś wpisze w URL
_known = set(temperatures.LABELS)
check("filtr zna tylko zadeklarowane czujniki",
      {'furnace_temp', 'nie_istnieje', ''} & _known == {'furnace_temp'})

# --- wszystkie zestawy wartości ----------------------------------------------

PANELS = {
    'home.BOILER_TILE': home.BOILER_TILE,
    'home.PV_TILE': home.PV_TILE,
    'home.COMFORT_TILE': home.COMFORT_TILE,
    'home.RECUPERATION_TILE': home.RECUPERATION_TILE,
    'boiler.FURNACE': boiler.FURNACE,
    'boiler.HOUSE': boiler.HOUSE,
    'boiler.WORK': boiler.WORK,
    'boiler.KEY_SETPOINTS': boiler.KEY_SETPOINTS,
    'pv.PRODUCTION': pv.PRODUCTION,
    'pv.BATTERY': pv.BATTERY,
    'pv.LOAD': pv.LOAD,
    'pv.TODAY': pv.TODAY,
    'comfort.COMFORT': comfort.COMFORT,
    'comfort.VALVE': comfort.VALVE,
    'comfort.SCHEDULE': comfort.SCHEDULE,
    'recuperation.AIR': recuperation.AIR,
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
check("liczniki przekaźnika czytają total_s i today_s",
      [spec.key for spec in boiler.WORK[:4]] == ['total_s', 'today_s', 'total_s', 'today_s'])
check("czasy pracy formatowane jako HH:MM:SS",
      all(spec.kind == 'duration' for spec in boiler.WORK[:4]))
check("liczniki przekaźników nie mają awaryjnej kolumny w bazie",
      all(spec.columns == () for spec in boiler.WORK))
check("DEVICES paruje total+dziś pod wspólnym tytułem, z WORK po kolei",
      [spec for _, _, rows in boiler.DEVICES for _, spec in rows] == boiler.WORK)
check("dobowe zużycie węgla podajnika czyta fuel_level.TOPIC, nie licznik przekaźnika",
      [spec.topics for spec in boiler.WORK[4:]] == [(fuel_level.TOPIC,)] * 2
      and [spec.key for spec in boiler.WORK[4:]] == ['today_coal_kg', 'today_energy_kwh'])
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
check("topics.relay_cmd", topics.relay_cmd('co_pump_boiler', 'caveweb') ==
      f'cave/relay/{topics.RELAY_MODULE}/co_pump_boiler/cmd/caveweb')
check("topics.COMFORT_TOPIC", topics.COMFORT_TOPIC == 'cave/comfort')

# --- strony /comfort i /recuperation - żadna pozycja nie ma awaryjnej kolumny
# w bazie (metrica tego topiku nie zbiera - to nie czujnik, dedykowane usługi
# dopiero powstają/są w budowie); inside_temp na kafelku /home to inny temat,
# patrz osobny check wyżej (ten czujnik metrica już zbiera) -----------------
check("żadna pozycja /comfort i /recuperation nie ma kolumny w bazie",
      all(spec.columns == () for values in
          (comfort.COMFORT, comfort.VALVE, comfort.SCHEDULE, recuperation.AIR,
           home.RECUPERATION_TILE)
          for spec in values))

# --- strona /comfort - formularz nastawy temperatury + sześciu bang-bang etapu 0

check("CONFIG_FIELDS adresuje nastawy comfort-controller pod cave/comfort/setpoints/*",
      all(comfort.config_setpoint_topic(name) == f'cave/comfort/setpoints/{name}'
          for name, *_ in comfort.CONFIG_FIELDS))
check("nazwy pól unikalne", len({name for name, *_ in comfort.CONFIG_FIELDS})
      == len(comfort.CONFIG_FIELDS))
check("min < max i domyślna w zakresie, dla każdego pola",
      all(min_v < max_v and min_v <= default <= max_v
          for _, _, _, min_v, max_v, default, _, _ in comfort.CONFIG_FIELDS))
check("krok dodatni dla każdego pola", all(step > 0 for *_, step in comfort.CONFIG_FIELDS))
check("nastawa temperatury ma krok 0.1 - reszta pełne jednostki",
      comfort.CONFIG_FIELDS[0][0] == 'inside_temp' and comfort.CONFIG_FIELDS[0][-1] == 0.1
      and all(field[-1] == 1 for field in comfort.CONFIG_FIELDS[1:]))
check("progi niskie niższe niż wysokie, w obu porach dnia (domyślne wartości)",
      comfort.CONFIG_FIELDS[3][5] < comfort.CONFIG_FIELDS[4][5]   # low/high dzień
      and comfort.CONFIG_FIELDS[5][5] < comfort.CONFIG_FIELDS[6][5])  # low/high noc
check("godzina początku dnia wcześniejsza niż końca (domyślne wartości)",
      comfort.CONFIG_FIELDS[1][5] < comfort.CONFIG_FIELDS[2][5])

check("clamp_config_value: w zakresie - bez zmian",
      comfort.clamp_config_value('float', 0, 100, 25.0) == 25.0)
check("clamp_config_value: poza zakresem - przycięte, nie odrzucone",
      comfort.clamp_config_value('float', 0, 100, 150.0) == 100.0
      and comfort.clamp_config_value('float', 0, 100, -5.0) == 0.0)
check("clamp_config_value: int zaokrąglony do liczby całkowitej",
      comfort.clamp_config_value('int', 0, 23, 19.6) == 20
      and isinstance(comfort.clamp_config_value('int', 0, 23, 19.6), int))

check("'Nastawa' w sekcji Komfort czyta wprost cave/comfort/setpoints/inside_temp, "
      "nie zdublowane pole na cave/comfort (usunięte stamtąd - patrz comfort_controller README)",
      next(spec for spec in comfort.COMFORT if spec.label == 'Nastawa').topics
      == (comfort.config_setpoint_topic('inside_temp'),))

done()
