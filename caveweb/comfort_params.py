# -*- coding: utf-8 -*-
"""Kopia metadanych nastaw comfort-controller (ten sam wzorzec co
`heating_params.py` dla kotła - caveweb nie importuje tamtego repo, integracja
tylko przez MQTT, więc nowa/zmieniona nastawa tam = ręczna aktualizacja tego
słownika tutaj; patrz comfort-controller/config.example.py po te same
domyślne).

`SETPOINTS` obejmuje tylko nastawy "jednorodne" (bool/liczba - pasują do tego
samego `render_row()`/`clamp_value()` co /boiler/config, patrz
`pages/comfort_config.py`). Trzy pozostałe nastawy nieobecności
(`absence_start`/`absence_end` - zakres dat, `absence_today` - switch z
własnym, żywym podpisem) mają inny kształt widgetu i są obsłużone osobno
tamże - stąd osobne stałe `ABSENCE_*_TOPIC` niżej zamiast wpisów w tym
słowniku."""
from __future__ import annotations
__version__ = "0.1"

TOPIC_ROOT = 'cave/comfort/setpoints'


def topic(name: str) -> str:
    return f'{TOPIC_ROOT}/{name}'


# nazwa -> {topic, data_type, default, min, max, unit, desc} - ten sam kształt
# co heating_params.SETPOINTS, więc boiler_config.clamp_value() działa też tu.
SETPOINTS = {
    'inside_temp_day': dict(
        topic=topic('inside_temp_day'), data_type='float',
        default=21.2, min=15.0, max=28.0, unit='°C',
        desc='Temperatura zadana - komfort dzienny'),
    'inside_temp_night': dict(
        topic=topic('inside_temp_night'), data_type='float',
        default=20.2, min=15.0, max=28.0, unit='°C',
        desc='Temperatura zadana - komfort nocny'),
    'day_start_hour': dict(
        topic=topic('day_start_hour'), data_type='int',
        default=6, min=0, max=23, unit='',
        desc='Dzień od (godzina)'),
    'day_end_hour': dict(
        topic=topic('day_end_hour'), data_type='int',
        default=20, min=0, max=23, unit='',
        desc='Dzień do (godzina) - reszta doby liczy się jako noc'),
    'mixing_valve_low_day': dict(
        topic=topic('mixing_valve_low_day'), data_type='float',
        default=20.0, min=0.0, max=100.0, unit='%',
        desc='Otwarcie zaworu - dzień, temperatura osiągnięta'),
    'mixing_valve_high_day': dict(
        topic=topic('mixing_valve_high_day'), data_type='float',
        default=25.0, min=0.0, max=100.0, unit='%',
        desc='Otwarcie zaworu - dzień, dogrzewanie'),
    'mixing_valve_low_night': dict(
        topic=topic('mixing_valve_low_night'), data_type='float',
        default=15.0, min=0.0, max=100.0, unit='%',
        desc='Otwarcie zaworu - noc, temperatura osiągnięta'),
    'mixing_valve_high_night': dict(
        topic=topic('mixing_valve_high_night'), data_type='float',
        default=20.0, min=0.0, max=100.0, unit='%',
        desc='Otwarcie zaworu - noc, dogrzewanie'),
    'mixing_valve_time': dict(
        topic=topic('mixing_valve_time'), data_type='float',
        default=120.0, min=10.0, max=600.0, unit='s',
        desc='Pełny skok zaworu (0% <-> 100%)'),
    'absence_enabled': dict(
        topic=topic('absence_enabled'), data_type='bool',
        default=False, min=None, max=None, unit='',
        desc='Nieobecność zaplanowana - włączona'),
    'absence_temp': dict(
        topic=topic('absence_temp'), data_type='float',
        default=18.0, min=10.0, max=24.0, unit='°C',
        desc='Temperatura zadana - nieobecność (zaplanowana i "tylko dziś")'),
}

# Trzy grupy pól /comfort/config (patrz pages/comfort_config.py) - jawne listy,
# nie "reszta z SETPOINTS", żeby dodanie nowej nastawy do słownika wyżej nie
# trafiało milcząco do złej sekcji.
SCHEDULE_FIELDS = (
    'inside_temp_day', 'inside_temp_night', 'day_start_hour', 'day_end_hour',
    'mixing_valve_low_day', 'mixing_valve_high_day',
    'mixing_valve_low_night', 'mixing_valve_high_night',
)
ABSENCE_FIELDS = ('absence_enabled', 'absence_temp')
# Reszta - sekcja "Konfiguracja" (analogicznie do /boiler/config "Zaawansowana").
ADVANCED_FIELDS = tuple(name for name in SETPOINTS
                        if name not in SCHEDULE_FIELDS and name not in ABSENCE_FIELDS)

# Nieobecność - trzy nastawy spoza SETPOINTS (patrz docstring modułu).
ABSENCE_START_TOPIC = topic('absence_start')
ABSENCE_END_TOPIC = topic('absence_end')
ABSENCE_TODAY_TOPIC = topic('absence_today')
