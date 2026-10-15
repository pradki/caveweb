"""Wspólne elementy interfejsu: nagłówek strony, kafelek, nagłówek sekcji."""

from __future__ import annotations
__version__ = "0.2"

from typing import Callable

from nicegui import ui

# Kafelek ma być duży – aplikacja chodzi na panelu dotykowym Raspberry Pi.
# Wysokość minimalna, nie stała: kafelki z wartościami bieżącymi są wyższe.
# w-60/min-h-60 (15rem) - ok. 30% większe niż poprzednie w-44 (11rem), z
# zapasem na więcej danych w body, nie tylko większą czcionkę.
TILE_CLASSES = (
    'w-60 min-h-60 cursor-pointer items-center justify-center '
    'transition-transform hover:scale-105'
)


def page_header(title: str, back: str | bool | None = None,
                right: Callable | None = None) -> None:
    """Górny pasek z opcjonalnym przyciskiem powrotu, przyciskiem home i
    czymś dodatkowym z prawej strony (np. zegarem na /home - patrz
    `live.clock_label`).

    `back=True` cofa przez historię przeglądarki (`ui.navigate.back()`) -
    tego chcemy prawie zawsze, bo jedna strona bywa otwierana z kilku miejsc
    (np. każdy wykres z `/charts`, `/pv` i `/boiler` naraz) i stały cel typu
    `back='/charts'` wracał tam nawet, gdy ktoś przyszedł skądinąd. Goły URL
    (`back='/inne'`) wciąż działa, gdyby kiedyś naprawdę trzeba było wymusić
    konkretny cel zamiast "tam, skąd przyszedłem".

    Przycisk home (ikona `home`) pokazuje się zawsze, gdy `back` jest podane -
    czyli na każdej stronie poza samym `/home`, które go nie przekazuje."""
    with ui.header().classes('bg-blue-900 text-white items-center justify-between'):
        with ui.row().classes('items-center gap-1'):
            if back is not None:
                go_back = ui.navigate.back if back is True else (lambda: ui.navigate.to(back))
                ui.button(icon='arrow_back', on_click=go_back) \
                    .props('flat round color=white dense')
                ui.button(icon='home', on_click=lambda: ui.navigate.to('/home')) \
                    .props('flat round color=white dense')
            ui.label(title).classes('text-lg font-medium q-ml-xs')
        if right is not None:
            right()


def tile(icon: str, title: str, target: str | None = None,
         subtitle: str = '', on_click: Callable | None = None,
         body: Callable | None = None,
         header_body: Callable | None = None) -> ui.card:
    """Kafelek nawigacyjny.

    `body` to funkcja rysująca wnętrze kafelka (u nas: wartości bieżące).
    `header_body` rysuje coś dodatkowego w tym samym wierszu co tytuł - np.
    jedną, najważniejszą wartość obok nazwy kafelka ("PV" + moc), żeby nie
    liczyła się do wierszy w `body` i kafelek został kwadratem.
    Bez `target` i `on_click` kafelek jest wyszarzony i nic nie robi.

    Wiersz tytułu wyrównany `items-center`, nie `items-baseline` - część
    `header_body` (np. `live_fuel_indicator`) dorzuca ikonę obok tekstu, a
    ikona nie ma tekstowego baseline, więc `items-baseline` liczyła go
    niejednoznacznie i przesuwała zawartość względem tytułu."""
    enabled = bool(target or on_click)
    card = ui.card().classes(TILE_CLASSES + ('' if enabled else ' opacity-40'))
    with card:
        ui.icon(icon).classes('text-4xl text-blue-4')
        with ui.row().classes('items-center gap-1 justify-center'):
            ui.label(title).classes('text-base font-medium text-center')
            if header_body is not None:
                header_body()
        if body is not None:
            body()
        if subtitle:
            ui.label(subtitle).classes('text-xs text-grey-6 text-center')
    if on_click is not None:
        card.on('click', on_click)
    elif target is not None:
        card.on('click', lambda: ui.navigate.to(target))
    return card


def tile_grid():
    """Kontener układający kafelki w responsywną siatkę."""
    return ui.row().classes('w-full justify-center gap-4 p-4')


def section(title: str) -> None:
    """Nagłówek sekcji na stronie szczegółowej."""
    ui.label(title).classes('text-sm uppercase tracking-wide text-grey-6 mt-2')


def number_stepper(label: str = '', *, value=None, min=None, max=None,
                   step: float = 1, suffix: str | None = None,
                   format: str | None = None, classes: str = 'w-32',
                   repeat_interval: float = 0.15) -> ui.number:
    """`ui.number` z dużymi przyciskami +/- obok pola, zamiast polegania na
    natywnych strzałkach `input[type=number]` - na dotykowym 10" ekranie Pi w
    te malutkie strzałki trudno trafić palcem (zgłoszone na /boiler/config).
    `hide-spin-buttons` chowa je, a te dwa przyciski obok robią to samo, w
    rozmiarze wygodnym do dotyku. `classes` ustawia szerokość całej grupy
    (przyciski + pole), nie samego pola - ono rozciąga się między nimi, więc
    to jest zamiennik 1:1 dla `ui.number(...).classes(classes)` gdziekolwiek
    był używany wcześniej.

    Przytrzymanie przycisku powtarza krok co `repeat_interval` - jeden
    `ui.timer(repeat_interval, ..., immediate=True)` na przycisk: odpala się
    od razu na naciśnięcie (to samo, co kiedyś robił `on_click`) i powtarza,
    dopóki trzymane. Zdarzenia `pointer*` (nie osobno `mouse*`/`touch*`) -
    jedno source zdarzeń dla myszy, dotyku i rysika, bez podwójnego odpalenia,
    jakie dają przeglądarki emulujące mysz po touchu."""
    held = {'minus': None, 'plus': None}

    def bump(delta: float) -> None:
        current = number.value if number.value is not None else 0.0
        new_value = current + delta
        if min is not None and new_value < min:
            new_value = min
        if max is not None and new_value > max:
            new_value = max
        number.value = new_value

    def start(key: str, delta: float) -> None:
        stop(key)
        held[key] = ui.timer(repeat_interval, lambda: bump(delta))

    def stop(key: str) -> None:
        timer = held.get(key)
        if timer is not None:
            timer.cancel()
            held[key] = None

    with ui.row().classes(f'items-center gap-1 no-wrap {classes}'):
        minus_btn = ui.button(icon='remove') \
            .props('round unelevated color=grey-8').classes('w-12 h-12 shrink-0')
        number = ui.number(label, value=value, min=min, max=max, step=step,
                           suffix=suffix, format=format) \
            .props('outlined dense hide-spin-buttons').classes('flex-grow min-w-0')
        plus_btn = ui.button(icon='add') \
            .props('round unelevated color=grey-8').classes('w-12 h-12 shrink-0')

    minus_btn.on('pointerdown', lambda: start('minus', -step))
    plus_btn.on('pointerdown', lambda: start('plus', step))
    for ev in ('pointerup', 'pointerleave', 'pointercancel'):
        minus_btn.on(ev, lambda: stop('minus'))
        plus_btn.on(ev, lambda: stop('plus'))

    return number


def fuel_indicator(percent: float) -> None:
    """Mały wskaźnik paliwa: ikona + procent, kolor wg progu. Procent w
    `text-base font-medium` - tak samo jak tytuł kafelka obok niego (patrz
    `tile()`) - osobny inline `font-size`/`font-weight` wyglądał jak inna
    czcionka, mimo że to ta sama, bo omijał te same klasy co reszta
    typografii strony.

    Bez własnego `ui.row()` - rysuje ikonę i etykietę wprost w wierszu
    wywołującego (patrz `live_fuel_indicator()`), żeby nie było zagnieżdżenia
    wiersz-w-wierszu (wygląda jak przesunięta, inna czcionka)."""
    if percent < 20:
        color = '#dc2626'  # czerwony
    elif percent < 60:
        color = '#d97706'  # pomarańczowy
    else:
        color = '#16a34a'  # zielony

    ui.icon('local_gas_station', size='20px').style(f'color: {color}')
    ui.label(f'{percent:.0f}%').classes('text-base font-medium').style(f'color: {color}')
