# -*- coding: utf-8 -*-
"""Testy wartości bieżących: parsowanie payloadów, sumy, awaryjny odczyt z bazy.

    python tests/test_live.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import check, done, ensure_nicegui

ensure_nicegui()

from caveweb import live, mqttclient, topics

NOW = 1_800_000_000.0


def reset(entries=None):
    """Czysty cache z wartościami podanymi jako {topic: (payload, wiek_w_s)}."""
    mqttclient.cache.clear()
    for topic, (payload, age) in (entries or {}).items():
        mqttclient.cache.put(topic, payload, when=NOW - age)


# --- parsowanie payloadów -----------------------------------------------------

check("JSON z polem value", mqttclient.parse_payload('{"value": 21.5}') == {'value': 21.5})
check("goła liczba w tekście", mqttclient.parse_payload('21.5') == 21.5)
check("bajty dekodowane", mqttclient.parse_payload(b'{"value": 3}') == {'value': 3})
check("pusty payload -> None", mqttclient.parse_payload('  ') is None)
check("payload nie-tekstowy -> None", mqttclient.parse_payload(None) is None)

check("extract domyślnie bierze value", mqttclient.extract({'value': 7}) == 7)
check("extract innego pola", mqttclient.extract({'today_s': 120, 'total_s': 9}, 'today_s') == 120)
check("extract brakującego pola -> None", mqttclient.extract({'value': 7}, 'state') is None)
check("extract skalara", mqttclient.extract(21.5) == 21.5)
check("extract zachowuje bool", mqttclient.extract({'state': True}, 'state') is True)
check("extract liczby z tekstu", mqttclient.extract({'value': '42'}) == 42.0)

# --- cache --------------------------------------------------------------------

reset({'cave/x': ({'value': 5}, 10.0)})
check("cache.value wyciąga pole", mqttclient.cache.value('cave/x') == 5)
check("cache.value nieznanego topiku", mqttclient.cache.value('cave/nope') is None)
check("cache.age liczy wiek", round(mqttclient.cache.age('cave/x', now=NOW)) == 10)
check("świeża wartość nie jest stale", not mqttclient.cache.is_stale('cave/x', now=NOW))
reset({'cave/x': ({'value': 5}, 9999.0)})
check("stara wartość jest stale", mqttclient.cache.is_stale('cave/x', now=NOW))

# --- odczyt pojedynczej wartości ---------------------------------------------

furnace = live.value_of('Piec', topics.sensor('furnace_temp'), unit='°C', digits=1)
check("kolumna w bazie zgadnięta z topiku",
      furnace.columns == ('furnace_temp_avg',))

reset({topics.sensor('furnace_temp'): ({'value': 62.34}, 5.0)})
reading = live.read(furnace, now=NOW)
check("wartość z brokera", reading.value == 62.34 and reading.source == 'broker')
check("format z jednostką", reading.text == '62.3 °C')
check("wiek zapamiętany", round(reading.age) == 5)

# --- suma topików -------------------------------------------------------------

pv = live.sum_of('Moc PV', [topics.deye('pv1_power'), topics.deye('pv2_power')],
                 unit='W', digits=0)
reset({
    topics.deye('pv1_power'): ({'value': 1200}, 3.0),
    topics.deye('pv2_power'): ({'value': 800}, 4.0),
})
reading = live.read(pv, now=NOW)
check("suma dwóch topików", reading.value == 2000)
check("format sumy", reading.text == '2000 W')
check("wiek sumy to najstarszy składnik", round(reading.age) == 4)
check("suma kompletna", reading.present == reading.expected == 2)
check("brak adnotacji o brakach", 'tylko' not in live.caption_text(reading))

# niepełna suma musi być widoczna, żeby nikt nie wziął 1200 W za całą produkcję
reset({topics.deye('pv1_power'): ({'value': 1200}, 3.0)})
reading = live.read(pv, now=NOW)
check("niepełna suma liczy tylko to, co jest", reading.value == 1200)
check("niepełna suma jest oznaczona", 'tylko 1/2' in live.caption_text(reading))

# --- inne pole payloadu -------------------------------------------------------

fan_today = live.value_of('Dmuchawa dziś', topics.relay_counters('co_fan'),
                          kind='seconds', key='today_s', columns=())
reset({topics.relay_counters('co_fan'): ({'today_s': 5400, 'total_s': 99}, 2.0)})
reading = live.read(fan_today, now=NOW)
check("czyta pole today_s", reading.value == 5400)
check("sekundy pokazane w minutach", reading.text == '90 min')

fan_state = live.value_of('Dmuchawa', topics.relay_status('co_fan'),
                          kind='bool', key='state', columns=())
reset({topics.relay_status('co_fan'): ({'state': True}, 1.0)})
check("bool jako wł.", live.read(fan_state, now=NOW).text == 'wł.')
reset({topics.relay_status('co_fan'): ({'state': False}, 1.0)})
check("bool jako wył.", live.read(fan_state, now=NOW).text == 'wył.')

# --- awaryjny odczyt z bazy ---------------------------------------------------

reset()
db_values = {'furnace_temp_avg': (58.2, 1_799_999_000)}
reading = live.read(furnace, db_values, now=NOW)
check("bez brokera wchodzi baza", reading.value == 58.2 and reading.source == 'baza')
check("dane z bazy oznaczone jako nieświeże", reading.stale)
check("podpis mówi skąd wartość", 'z bazy' in live.caption_text(reading))

reading = live.read(furnace, {}, now=NOW)
check("brak wszędzie -> brak danych", reading.value is None and reading.text == '–')
check("podpis o braku danych", live.caption_text(reading) == 'brak danych')

# broker ma pierwszeństwo nad bazą
reset({topics.sensor('furnace_temp'): ({'value': 62.0}, 5.0)})
reading = live.read(furnace, db_values, now=NOW)
check("broker wygrywa z bazą", reading.value == 62.0 and reading.source == 'broker')

# --- kolumny do awaryjnego odczytu -------------------------------------------

check("db_columns zbiera bez powtórzeń",
      live.db_columns([furnace, pv, furnace]) ==
      ['furnace_temp_avg', 'pv1_power_avg', 'pv2_power_avg'])
check("kolumny puste dla przekaźników", live.db_columns([fan_today]) == [])

# --- wartość przestarzała -----------------------------------------------------

reset({topics.sensor('furnace_temp'): ({'value': 62.0}, 9999.0)})
check("stara wartość oznaczona jako stale", live.read(furnace, now=NOW).stale)

done()
