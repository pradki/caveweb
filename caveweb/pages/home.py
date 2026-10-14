"""Ekran główny – kafelki najwyższego poziomu z wartościami bieżącymi."""

from __future__ import annotations
__version__ = "0.2"

from nicegui import ui

from .. import fuel_level, live, topics
from ..widgets import page_header, tile, tile_grid

# Wartości pokazywane wprost na kafelkach - tyle, żeby jednym spojrzeniem
# wiedzieć, czy warto wchodzić głębiej.
BOILER_TILE = [
    live.value_of('piec', topics.sensor('furnace_temp'), unit='°C', digits=1),
]

TEMPERATURES_TILE = [
    live.value_of('zewnątrz', topics.sensor('outside_temp'), unit='°C', digits=1),
    live.value_of('wewnątrz', topics.sensor('inside_temp'), unit='°C', digits=1),
]

COMFORT_TILE = [
    # Wprost z czujników, nie z cave/comfort (temp_current) - ten sam pomiar
    # inside_temp, ale niezależny od tego, czy comfort-controller akurat
    # działa. floor_temp obok, w tym samym wierszu (render_compact, dwie
    # pozycje) - żeby kafelek nie urósł o drugi rząd.
    live.value_of('temperatura', topics.sensor('inside_temp'), unit='°C', digits=1),
    live.value_of('podłoga', topics.sensor('floor_temp'), unit='°C', digits=1),
]

# Wilgotność i CO2 przeniesione tu z Panelu komfortu - inny temat (powietrze,
# nie temperatura/zawór), docelowo osobna usługa rekuperacji.
RECUPERATION_TILE = [
    live.Value('wilgotność', (topics.COMFORT_TOPIC,), key='humidity',
              unit='%', digits=0, columns=()),
    live.Value('CO2', (topics.COMFORT_TOPIC,), key='co2',
              unit='ppm', digits=0, columns=()),
]

PV_TILE = [
    live.sum_of('moc PV', [topics.deye('pv1_power'), topics.deye('pv2_power')],
                unit='W', digits=0),
    live.value_of('bateria', topics.deye('battery_soc'), unit='%', digits=0),
    live.sum_of('obciążenie', [topics.deye('load_power_l1'),
                               topics.deye('load_power_l2'),
                               topics.deye('load_power_l3')], unit='W', digits=0),
]


@ui.page('/home')
def home() -> None:
    page_header('cave', right=live.clock_label)

    boiler = live.LivePanel(BOILER_TILE)
    pv = live.LivePanel(PV_TILE)
    temperatures = live.LivePanel(TEMPERATURES_TILE)
    comfort = live.LivePanel(COMFORT_TILE)
    recuperation = live.LivePanel(RECUPERATION_TILE)

    def boiler_body() -> None:
        # Jeden wiersz, nie `render_compact` (dwie kolumny z podpisami pod
        # spodem) - inaczej temperatura i węgiel łamią się na dwa rzędy i
        # kafelek rośnie wyżej niż reszta. "~" zamiast podpisu - w jednym
        # wierszu nie ma miejsca na opis, pełne wyjaśnienie w tooltipie.
        # Tylko prognoza na całą dobę - zużycie "do tej pory" jest już na
        # /boiler (karta Podajnika), nie trzeba go dublować na kafelku.
        with ui.row().classes('items-baseline gap-1 justify-center flex-nowrap'):
            temp_label = ui.label('–').classes('text-lg font-medium leading-tight')
            ui.label('·').classes('text-xs text-grey-6')
            live.inline_topic_field(fuel_level.TOPIC, 'projected_daily_kwh',
                                    prefix='~', suffix='kWh', digits=0) \
                .tooltip('Szacowane zużycie węgla za całą dobę (z dzisiejszego tempa)')
        boiler.bind('piec', temp_label)

    def comfort_header() -> None:
        # Emoji wg hvac_state - który próg bang-bang jest teraz aktywny:
        # ♨️ "grzeje" (mixing_valve_high), 💤 "czeka" (mixing_valve_low). NIE
        # stan pompy - ta chodzi prawie zawsze (patrz comfort-controller
        # README), więc nic by to nie różnicowało. Obok tytułu, tak jak
        # poziom paliwa obok "Kocioł CO" - żeby zostało miejsce w body na
        # temperaturę + podłogę w jednym rzędzie.
        live.mapped_emoji_field(topics.COMFORT_TOPIC, 'hvac_state',
                                {'grzeje': '♨️', 'czeka': '💤'})

    with tile_grid():
        tile('insert_chart', 'Wykresy', target='/charts',
             subtitle='temperatury, moc, energia')
        tile('local_fire_department', 'Kocioł CO', target='/boiler',
             header_body=lambda: live.live_fuel_indicator(fuel_level.TOPIC),
             body=boiler_body)
        tile('solar_power', 'PV', target='/pv',
             header_body=pv.render_header_value,
             body=lambda: pv.render_compact(skip=1))
        tile('thermostat', 'Temperatury', target='/temperatures',
             body=temperatures.render_compact)
        tile('spa', 'Panel komfortu', target='/comfort',
             header_body=comfort_header,
             body=comfort.render_compact)
        tile('air', 'Rekuperacja', target='/recuperation',
             body=recuperation.render_compact)
        tile('power', 'Przekaźniki', target='/relays')
        tile('auto_mode', 'Automatyzacje', target='/automations')
        tile('blinds', 'Rolety', subtitle='w przygotowaniu',
             on_click=lambda: ui.notify('Sterowanie roletami – wkrótce'))
        tile('water_drop', 'Nawadnianie', subtitle='w przygotowaniu',
             on_click=lambda: ui.notify('Nawadnianie ogrodu – wkrótce'))
        tile('settings', 'Konfiguracja', target='/settings',
             subtitle='wygaszacz ekranu')

    boiler.start()
    pv.start()
    temperatures.start()
    comfort.start()
    recuperation.start()
    live.mqtt_status_label()
