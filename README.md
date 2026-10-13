# caveweb

NiceGUI dashboard for the cave installation, running as a standalone systemd service on a
Raspberry Pi. The home screen is a grid of touch-friendly tiles: live readouts for the CO
boiler and the PV inverter, and a chart section plotting temperatures, battery, power and
energy over four time ranges — day, week, month, year.

Two data sources, each for what it is good at:

- **MQTT** for *now*. The app subscribes to the broker and keeps the last payload per topic in
  memory. It never publishes, so it cannot influence the boiler, the inverter or the relays.
- **SQLite** for *history*. [metrica](https://github.com/pradki/metrica) collects the same MQTT
  traffic and pre-aggregates it; charts read those rollups read-only. A live value that has not
  arrived yet falls back to the newest 15-minute bucket, labelled as coming from the database.

```
                    ┌──────────────┐
  sensors  ────────▶│              │──▶ metrica ──▶ measurements.db
  inverter ────────▶│ MQTT broker  │                15m / 6h / 1d rollups
  relays   ────────▶│              │                        │
  heating svc ─────▶└──────┬───────┘                        │ read-only
                           │ subscribe only                 │
                           ▼                                ▼
                    ┌───────────────────────────────────────────┐
                    │  caveweb (this repo)                      │
                    │  tiles + live values  ·  ECharts history  │──▶ browser :8081
                    └───────────────────────────────────────────┘
```

## Screens

| Route | What is on it |
|-------|---------------|
| `/home` | A clock (`YYYY-MM-DD HH:MM:SS`) on the right of the header. Tiles: **Wykresy**, **Kocioł CO** (fuel level next to the title, furnace temperature + today's/projected coal energy on the tile), **PV** (PV power next to the title, battery SOC + load on the tile), **Temperatury** (outside/inside on the tile), **Panel komfortu** (♨️/💤 for the floor pump next to the title, same spot as Kocioł CO's fuel level; room + floor temperature on the tile), **Rekuperacja** (humidity + CO2), **Przekaźniki**, **Rolety** and **Nawadnianie** (placeholders, no action yet) |
| `/boiler` | Furnace, flue gas, feeder, return, DHW and fireplace-return temperatures; all 4 buffer sensors (top, upper-middle, lower-middle, bottom), inside and outside; one card per device (fan, feeder) with its total and today's runtime, feeder also showing today's coal in kg/kWh; the key setpoints; **Wypalanie** button (confirmation dialog, configurable °C/minutes) — see [Burning off](#burning-off-a-temporary-self-reverting-setpoint-boost); **Wykres temperatur** goes to `/temperatures`, not a `/charts/*` page, since that's where the actual chart and sensor picker live |
| `/boiler/config` | Every setpoint from `PARAMS_HEATING` — current value from the broker next to an input bounded by the parameter's own min/max. **Zapisz** publishes the whole form — see [Writing setpoints](#writing-setpoints) |
| `/boiler/refuel` | Log a feeder refuel: bag count, bag size (20/25 kg, remembered), whether filled to full — see [Writing data: the refuel log](#writing-data-the-refuel-log) |
| `/pv` | PV total and per string, battery SOC and power, load total and per phase, today's battery charge/discharge and the consumption meter |
| `/temperatures` | All 10 temperature sensors live, each with a checkbox; **Pokaż na wykresie** opens `/temperatures/chart` plotting only the checked ones. The selection is remembered per browser session |
| `/relays` | Pick a waveshare-mqtt-gateway module, then every one of its channels: number, name, state, who holds it, at what priority, when its lease expires, and an **Akcja** button to force on/off/flash_on (duration in s/min/h, your pick) — see [Relays](#relays-manual-channel-control) |
| `/comfort` | Room temperature, floor mixing valve/pump and a simplified day/night schedule, from `cave/comfort` (real for temperature/valve - `comfort-controller`; still stubbed for the rest) — plus a small config form for the temperature target and six bang-bang setpoints that service needs to run — see [Comfort](#comfort-real-for-temperaturevalve-still-stubbed-for-air-quality) |
| `/recuperation` | Humidity, CO2 and other air-quality fields, moved out of `/comfort` — still presentation-only, no publisher of its own yet — see [Recuperation](#recuperation-still-presentation-only) |
| `/charts/*` | Temperatures, battery, power, energy — see [Charts](#charts) |
| `/settings` | Kiosk configuration — currently just the screen-idle blanker (on/off, timeout, whether to restart wayvnc on wake) — see [Kiosk](#kiosk-fullscreen-on-the-pis-own-screen) |

Values are refreshed every 5 s from the in-memory MQTT cache; a value older than 5 minutes is
greyed out, and each card says how old it is and whether it came from the broker or the
database. A sum of several topics (PV1+PV2, L1+L2+L3) says `tylko 2/3` when a component is
missing, so a partial sum is never mistaken for the total.

## MQTT

Payload conventions differ per publisher, so the cache stores the parsed JSON and each screen
declares which field it wants:

| Topic | Field | Example |
|-------|-------|---------|
| `cave/sensors/<kind>/<name>` | `value` | `{"value": 63.4}` |
| `cave/deye/params/<name>` | `value` | `{"value": 1234}` |
| `cave/heating/setpoints/<name>` | `value` | `{"value": 62}` — `furnace_temp` is also **published** by this app, from `/boiler`'s Wypalanie button only — see [Burning off](#burning-off-a-temporary-self-reverting-setpoint-boost) |
| `cave/relay/<module>/<alias>/status` | `state` | `{"channel": 3, "state": "flash_on", "by": "caveweb", "priority": 20, ...}` — `state`/`by`/`priority` also drive `/relays`, see [Relays](#relays-manual-channel-control) |
| `cave/relay/<module>/status` | `channels` | `{"channels": 30, ...}` — the per-module bitmask; `/relays` reads `channels` to know the table's row count and to discover which modules exist at all |
| `cave/relay/<module>/<alias>/counters` | `today_s`, `total_s` | `{"today_s": 5400, ...}` |
| `cave/relay/<module>/<name>/cmd/caveweb` | — | **published** by this app: `co_pump_boiler` automatically alongside the Wypalanie boost (`{"cmd": "flash_on", "duration": 600, "priority": 20}`, see [Burning off](#burning-off-a-temporary-self-reverting-setpoint-boost)), or any channel manually from `/relays`'s **Akcja** button |
| `cave/heating/fuel_level` | `value`, `today_energy_kwh`, `projected_daily_kwh`, ... | **published** by this app, hourly, retained — see [Publishing](#publishing-the-fuel-level-estimate) |
| `cave/comfort` | `temp_current`, `humidity`, `co2`, `hvac_state`, `schedule_mode`, `mixing_valve*`, `pump_on`, ... | one JSON with everything `/comfort` and `/recuperation` show — see [Comfort](#comfort-real-for-temperaturevalve-still-stubbed-for-air-quality) |
| `cave/comfort/setpoints/<name>` | `value` | the seven `comfort-controller` setpoints `/comfort`'s **Konfiguracja** section writes — **published** by this app, retained |

Most publishers use `retain=True`, so the broker replays the current state right after the
subscription and the screens are populated within a second of a restart. The client connects
with `connect_async`, which means a broker that is not up yet (typical during boot) delays the
values but never the web server.

A screen declares a value like this — one topic, or several to be summed:

```python
live.value_of('Piec', topics.sensor('furnace_temp'), unit='°C', digits=1)
live.sum_of('Moc PV', [topics.deye('pv1_power'), topics.deye('pv2_power')], unit='W', digits=0)
live.value_of('Dmuchawa total', topics.relay_counters('co_fan'), kind='duration', key='total_s')
```

`kind='duration'` formats seconds as `HH:MM:SS`, with a day count prefixed once it passes 24h
(`format_value`/`format_duration_hms` in `live.py`) — used for the relay gateway's on-time
counters (`today_s`/`total_s`), which run well past the point where `kind='seconds'`'s
minutes-or-hours format stops being readable.

### Boiler parameters

`caveweb/heating_params.py` is a **copy** of `PARAMS_HEATING` from the heating service's
`shadow_vault.py`, trimmed to what the UI needs: topic, type, range, unit, description. A copy
rather than an import, because caveweb is a standalone service that integrates only through
MQTT and has no access to the `cave` tree. `source_type` splits the dictionary into setpoints
(editable) and sensors (read-only), and both `/boiler` and `/boiler/config` build themselves
from it — a new parameter in the heating service means regenerating this one file.

### Writing setpoints

`/boiler/config`'s **Zapisz** publishes every setpoint field on the page to its
`cave/heating/setpoints/<name>` topic (`{"value": ...}`, retained) - the whole form at once, not a
diff of what actually changed, matching how **Wczytaj z brokera** already fills every field at
once. Each numeric value is clamped to its metadata's `[min, max]` before publishing
(`clamp_value()`) - not cosmetic: `heating-controller`'s `shadow_vault.check_and_correct()` doesn't
clamp an out-of-range value, it resets that parameter to its *default*, so an unclamped value past
the edge would silently undo itself instead of applying. A field left empty is skipped rather than
publishing `null`. This was the one page in this app that only ever listened; the furnace's own
independent hard safety ceiling (`MAX_FURNACE_TEMP`, checked against the real sensor reading, not
any setpoint) is unaffected either way - see "Burning off" below for the other, narrower place
this app writes a setpoint.

### Writing data: the refuel log

`/boiler/refuel` (`caveweb/refuels.py`) is the one place this app writes anything at all - a
plain append-only CSV, not a broker publish, and recording a *fact about the physical world*
(someone poured coal in), never a command that changes how the furnace runs. That's a different
risk than the setpoints page above: it can't feed back into control, so the "we only read"
principle isn't being bent, just scoped to "we don't control the furnace" rather than "we don't
write anything, ever".

Each row: timestamp, bag count, bag size (20 or 25 kg), total kg, whether it was filled to
full, and the feeder's `total_s` counter (`cave/relay/relay_heating/co_feeder/counters`) at
that moment. That last field is the point: the difference between two consecutive "filled to
full" entries' `total_s` is exactly how long the feeder ran to burn through what got topped up
at the second one, so every such pair is a measurement of seconds-of-feeder-runtime per kg for
whichever bag size was actually burning (the *first* entry's size, not necessarily the second's
- `refuels.coefficient_for()` attributes each interval that way). A non-full top-up breaks the
pair on both sides, since it's no longer true that the interval started and ended at a known
full tank.

Both bag sizes currently share one starting coefficient, `308 s/kg`, worked out by hand from a
full season of `/home/sqna/cave/logs/feeder_log.csv` (hand-annotated `# add NNN kg` comment lines
around the hourly on-time rows) - treat it as provisional, since the per-interval spread in that
data was wide (one interval alone was 4-6x faster than the rest). 20 kg had no data of its own at
first, which meant `today_coal_kg`/`today_energy_kwh`/`projected_daily_kwh` stayed `null` for
anyone burning 20 kg bags until a *second* "filled to full" 20 kg refuel happened to measure an
interval from - surprising on the very first 20 kg refuel, which is exactly when someone wants to
see the pipeline working. Sharing 308 s/kg (and the flat 27 MJ/kg calorific value, `ENERGY_MJ_PER_KG`)
across both sizes for now is a deliberate, acknowledged simplification, not a claim that the two
coal types burn identically - real per-size measurements are expected once there's been enough of
a season on 20 kg bags to compare (planned for December/January). `coefficient_for()` always
prefers a real measured pair over `DEFAULT_COEFFICIENTS` for whichever size it's asked about, so
each size's shared default quietly stops mattering the moment that size has its own real pair.

Confirming on `/boiler/refuel` also appends one line to that same `feeder_log.csv`
(`caveweb/feeder_log.py`), in the same hand-written convention: `# add 200kg 8x25kg`. That file is
owned by `heating-controller`'s `feeder_logger.py`, a **separate process** that does a full
read-and-rewrite of the whole CSV on every feeder on-time update - a bare append from here could
land mid-rewrite and simply vanish. Both sides now take the same `fcntl.flock` around their
respective operation (see that service's README) so one can't clobber the other.

### Publishing: the fuel level estimate

`caveweb/fuel_level.py` is the other write path - the only thing this app publishes to MQTT
at all (`mqttclient.publish()`, added just for this). It's the same category as `cave/heating/status`
or `cave/cwu/status` from the other services: a service announcing something it computed about
itself, not a command that controls anything. Once an hour (`publish_loop()`, started from
`caveweb/__init__.py`'s `on_startup`), it replays the whole refuel log and publishes
`cave/heating/fuel_level`, retained:

```json
{
  "value": 75.0, "kg": 150.0, "tank_capacity_kg": 200.0,
  "last_refuel_timestamp": "2026-10-10T18:00:00",
  "last_refuel_total_s": 1000.0, "last_refuel_filled_to_full": true,
  "last_refuel_bag_size_kg": 25, "coefficient_s_per_kg": 308.0,
  "today_coal_kg": 10.0, "today_energy_kwh": 75.0, "projected_daily_kwh": 150.0
}
```

The model (`fuel_level.estimate()`) replays every row in order: a "filled to full" entry resets
the running level to `TANK_CAPACITY_KG` (200 kg); anything else adds its `total_kg` to whatever
the level already was (capped at capacity) - that's the "topped up, not to full" case, which
can't reset the baseline because we don't know what was in the tank before it. Between every
pair of rows, and from the last row to now, the elapsed `total_s` is converted to kg burned using
`refuels.coefficient_for()` for whichever bag size was active over that stretch. `value` is the
percentage (what `fuel_indicator()` in `widgets.py` expects); the rest of the fields are there so
anything subscribing can see *why* the number is what it is, not just the number.

`today_coal_kg`/`today_energy_kwh` are the same estimate applied to just today: the feeder's own
`today_s` (from `cave/relay/relay_heating/co_feeder/counters`, reset at the gateway's midnight)
divided by the currently-active bag's coefficient, times a flat 27 MJ/kg (`ENERGY_MJ_PER_KG`) to
get kWh - coal composition varies enough that this is a rough figure, not a calibrated one, but
kWh is easier to compare against the rest of the installation than kg. All three are `null` until
a refuel has been logged (no bag size to pick a coefficient from yet).

`projected_daily_kwh` answers a different question: not "how much has burned so far today" but
"how much will burn by midnight at this rate" - `today_energy_kwh` divided by how much of the day
has elapsed (`_projected_daily()`), so 15 kWh by noon projects to ~30 kWh/24h. Linear extrapolation,
nothing fancier - it reads as "if the rest of the day burns like the first part did". `null` at
the exact top of midnight (division by zero) and whenever `today_energy_kwh` itself is `null`.

Wired into the Kocioł CO tile on `/home`: `fuel_indicator()` sits next to the tile's title (same
spot `moc PV` has on the PV tile), and the tile body shows `projected_daily_kwh` - "~Y kWh" -
alongside the furnace temperature, one `ui.row` with `flex-nowrap`. Not `LivePanel.render_compact`'s
per-value columns (each with its own caption underneath): that wrapped onto a second row and made
the tile taller than its neighbours. `live.inline_topic_field()` draws just the bare value (a `~`
prefix instead of a caption marks it as an estimate, with the full explanation in a tooltip) for a
field read straight off a topic's payload, for values that aren't a `LivePanel` sensor. Just the
projection, deliberately: the tile is for "how is today shaping up", and `today_coal_kg`/
`today_energy_kwh` (how much has actually burned so far) already have their own rows on the
Podajnik card in "Praca urządzeń" on `/boiler` - see `boiler.WORK` - no need to show both on the
home tile too.

### Burning off: a temporary, self-reverting setpoint boost

`/boiler`'s **Wypalanie** button (`caveweb/furnace_boost.py`) is a second, narrower way this app
writes `furnace_temp_setpoint`, distinct from the general publishing in "Writing setpoints" above:
it raises the setpoint (by how much, and for how long, is confirmed in a dialog each time - see
below) to run the furnace hot enough to burn off buildup, then puts the original value back *by
itself*, without anyone clicking Zapisz again. That self-reverting behaviour is the whole point of
a separate mechanism here rather than just using the config page for this too:

- Clicking **Wypalanie** opens a confirmation dialog instead of acting immediately - easy to tap
  by accident on a touchscreen, and this is a real command to the furnace and pump, not a view.
  The dialog has two fields, prefilled from `BOOST_DELTA_C`/`BOOST_DURATION_SECONDS` (10°C, 10
  minutes) but editable per use: how many degrees to raise, and for how many minutes.
- The boosted value is clamped to the setpoint's configured `max` (72°C). This isn't cosmetic:
  `heating-controller`'s `shadow_vault.check_and_correct()` doesn't clamp an out-of-range value, it
  resets the parameter to its *default* (60°C) - publishing an un-clamped "+10" past the max would
  silently undo the boost instead of applying it.
- State (`original_value`, `boosted_value`, `expires_at`) is written to a small JSON file
  (`config.FURNACE_BOOST_PATH`), not just kept in memory - a caveweb restart mid-boost must not
  strand the furnace at the raised setpoint. `watch_loop()` (started from `on_startup`, polling
  every 15s) checks the expiry regardless of whether it's the same process that started the boost;
  if the deadline already passed while caveweb was down, it reverts immediately on the first check.
  This is the same "decoupled renewal/watchdog" shape used elsewhere in this project for exactly
  the same reason (see e.g. `heating-controller`'s `ping_loop`).
- A second click while a boost is active is refused, rather than adding another +10 on top of the
  already-raised value - the button becomes "Anuluj wypalanie" instead, for an immediate manual
  revert.
- None of this touches `MAX_FURNACE_TEMP`, `heating-controller`'s independent hard safety ceiling
  compared against the *actual* sensor reading, not the setpoint - that stays in force no matter
  what the setpoint says.

**The boiler pump gets kicked at the same moment**, not left to catch up on its own.
`heating-controller`'s own `pump_boiler_ctrl()` already turns that pump on, but only reactively -
once the furnace has *actually* exceeded `setpoint + FURNACE_OVERHEAT_MARGIN`. Waiting for that
after a boost means several idle minutes before heat starts moving to the buffer, right when the
furnace is being pushed hottest. So `start_boost()` also fires its own `flash_on` on the
`co_pump_boiler` channel for the same `BOOST_DURATION_SECONDS`, immediately, at `PUMP_PRIORITY`
(20) - deliberately higher than `heating-controller`'s own lease priority (10) for every command it
sends, including this channel's. `waveshare-mqtt-gateway`'s `leases.ChannelTable.resolve()` always
picks the highest-priority *unexpired* lease across every service with a claim on a channel, so
this claim wins outright for its whole duration, regardless of whether `heating-controller`'s own
threshold has fired yet. Normally it needs no explicit "off" or revert: a `flash_on` lease is a
hardware pulse that expires on its own, same failure-safe shape as every other relay command in
this project, and after it expires `heating-controller`'s own reactive logic is expected to pick
the pump back up anyway, since the furnace is normally still hot enough to exceed the
(by-then-reverted, lower) setpoint by more than its margin.

**Anulowanie (cancel) also tries to stop the pump early**, not just revert the setpoint - this
gap was found the first time someone actually clicked Anuluj mid-boost and the pump kept running
for its full 10 minutes regardless. A plain `off` command doesn't work here: the gateway module
ignores `off` while a `flash_on` pulse it already started is still counting down (measured
directly on the hardware, see `cwu-controller`/`heating-controller`'s `relay_client.py`). Instead,
`cancel_boost()` sends a **new** `flash_on` on the same channel, from the same service
(`caveweb`), for a short `PUMP_CANCEL_DURATION` (2s) - the same register write that started the
pulse, asked to re-arm to a much shorter one, rather than a different command the module is known
to disregard mid-pulse. This is **unverified on the real module** (the two hardware facts it
leans on - "off is ignored mid-pulse" and "a fresh flash_on write re-arms the timer instead of
being ignored the same way" - were never actually tested together) - hence the deliberately
hedged wording in the UI ("pompa powinna się niedługo zatrzymać", not "zatrzymana"). Worth
confirming against the real relay the next time a boost is cancelled mid-flight.

### Relays: manual channel control

`/relays` (`caveweb/relay_control.py` + `caveweb/pages/relays.py`) is the second and broadest
control surface this app has: instead of one fixed command for one fixed purpose (the boost
above), it's a generic "force any channel of any module to any state" page. Built for a future
with more than one `waveshare-mqtt-gateway` module - there's only `relay_heating` today, but
nothing here assumes that stays true.

**Nothing is hardcoded** - no module list, no channel count, no alias names. The gateway already
publishes everything needed, retained, right after it starts:

- `cave/relay/<module>/status` carries a `channels` field - that's both how a module is
  *discovered* (`discover_modules()` scans the cache for this exact 4-segment topic shape) and how
  many rows the table draws.
- `cave/relay/<module>/<name>/status` (5 segments) carries `channel`, `state`, `by` and `priority`
  for one channel, under whatever name the gateway considers primary for it (a configured alias,
  or `ch<N>` when there isn't one). Scanning every topic under a module's prefix
  (`discover_channel_names()`) recovers the full channel-number → name map with no separate config
  to keep in sync.

A channel that has never published any status at all (channel count known, but that specific
channel silent) shows as `ch<N>` with blank state/by/priority, rather than guessing "off" -
`channel_rows()` only reports what's actually been seen.

**Akcja** opens a small dialog: pick `on` / `off` / `flash_on`, a priority (defaults to 50 -
deliberately higher than `heating-controller` and `cwu-controller`'s own priority of 10 for
everything they send, so a manual action actually wins the gateway's arbitration instead of losing
to whichever automatic service already holds the channel), and a duration - the gateway's
`flash_on`/`flash_off` require one explicitly (see `waveshare-mqtt-gateway/mqtt_gateway.py`'s
`VALID_CMDS` handling), and `on`/`off` without one get the gateway's own 1-hour `DEFAULT_LEASE_TTL`
— `send_command()` always sends an explicit value instead (default 60s) so a manual override
doesn't quietly outlive the person who set it. The command goes out as
`cave/relay/<module>/<name>/cmd/caveweb` with the same `{"cmd", "priority", "duration"|"ttl"}`
shape every other service's commands use - the gateway can't tell a manual click here from an
automated decision elsewhere.

The duration field has a unit dropdown (s / min / h, `DURATION_UNITS` in `pages/relays.py`) next
to it rather than making everyone do the arithmetic for e.g. a 2-hour `on` - switching units
converts the number already typed so it still means the same real duration, and `confirm()`
multiplies back to seconds before calling `send_command()` (the gateway only ever sees seconds).

The table's **Wygasa** column reads `expires_at` straight off the same per-channel status payload
as `state`/`by`/`priority` - the gateway's reconciler already converts the winning lease's
(monotonic) `expires_at` to wall-clock time before publishing it (`reconciler.py`'s
`_publish_status`), so `_format_expiry()` only needs a plain subtraction against `time.time()` to
show a countdown ("za 45 s", "za 5 min", ...), refreshed by the same 5 s timer as the rest of the
table. `None` (a channel with no active lease at all) shows as "–".

### Comfort: real for temperature/valve, still stubbed for air quality

`/comfort` (`caveweb/pages/comfort.py`) shows room temperature and the floor-heating mixing
valve/pump, all read from one retained topic, `cave/comfort` (`topics.COMFORT_TOPIC`). This
used to be presentation-only for everything on that topic; it no longer is for this part -
[comfort-controller](https://github.com/pradki/comfort-controller) (a separate, standalone
service, same MQTT-only shape as `cwu-controller`/`heating-controller`) now really decides the
valve target and publishes `temp_current`/`hvac_state`/`schedule_mode`/`mixing_valve*`/`pump_on`.
Humidity/CO2/air quality do not have a real publisher yet, so those still come from
`scripts/comfort_stub.py` (unchanged - see below) and now live on their own page,
[`/recuperation`](#recuperation-still-presentation-only).

Two read-only sections, one `LivePanel` each:

- **Komfort** — current/target temperature, mode (heating only in this first stage, `None`
  until a future stage adds cooling/auto), heating/idle state, zone (one zone for now), and an
  `alarm_reason` cell that stays blank unless `comfort-controller`'s frozen-sensor fail-safe has
  tripped (see that repo's README).
- **Zawór mieszający** — `mixing_valve` (current target %, not a position sensor - the
  controller has none, see its README), the day/night `mixing_valve_low`/`_high` currently in
  effect, `mixing_valve_time` (full travel time) and whether the floor pump is running.
- **Harmonogram** — day/night mode and workday/weekend profile only, per the user's own
  expectation that this is "in practice probably just day/night" until a real schedule exists;
  `schedule_profile`/`override_state` still come from the stub (no workday/weekend or override
  concept in `comfort-controller` yet).

A third section, **Konfiguracja**, is the one place this page writes anything: the room
temperature target (`inside_temp` - note the topic is `cave/comfort/setpoints/inside_temp`,
plural "setpoints" like `cave/heating/setpoints/*`, not "setpoint") at 0.1°C resolution, plus the
six setpoints `comfort-controller` needs to run its stage-0 bang-bang at all - day/night boundary
hours and the four `mixing_valve_low`/`_high` day/night levels - published to their own
`cave/comfort/setpoints/<name>` topics (retained), the same "whole form at once, clamped to
range" shape as `/boiler/config`'s `clamp_value()`/**Zapisz** (`clamp_config_value()` here, with a
per-field `step` in `CONFIG_FIELDS` - 0.1 for the temperature, 1 for everything else - driving
both the stepper buttons and the display precision). Deliberately not every setpoint
`comfort-controller` has (`mixing_valve_time` still doesn't have a field here) - "for now, just
what's necessary for it to run," per the person who asked for this form.

Enum-like fields (`mode`, `hvac_state`, `schedule_mode`, `ventilation_state`, ...) arrive
as ready-to-show Polish text rather than a code the page translates - `live.format_value`
already passes a string value through unchanged, so there is no separate translation table
to keep in sync with whatever the publishing service decides to call its states.

### Recuperation: still presentation-only

`/recuperation` (`caveweb/pages/recuperation.py`) is what `/comfort`'s **Powietrze** section used
to be, moved to its own page because it is a different subsystem (ventilation/air quality) with
no publisher of its own yet - still the same `cave/comfort` topic as `/comfort` for now (nothing
else exists to read from), expected to move to its own topic once a real recuperation service is
built. Temperature, humidity, CO2, and optionally PM2.5/VOC/radon (`None` until a sensor exists),
plus ventilation state, filter and dampness-risk indicators - still only ever from
`scripts/comfort_stub.py`:

```bash
python scripts/comfort_stub.py --host 127.0.0.1
```

Running it alongside `comfort-controller` is fine for these fields specifically (nothing else
publishes them), but see that script's own docstring for the fields it should no longer be
trusted for.

## Charts

The app never scans raw samples; it reads metrica's pre-aggregated tables, so the day view
touches at most 96 rows and the year view 365. Picking the table is the whole "query planner":

| Range   | Table              | Bucket |
|---------|--------------------|--------|
| Day     | `measurements_15m` | 15 min |
| Week    | `measurements_6h`  | 6 h    |
| Month   | `measurements_6h`  | 6 h    |
| Year    | `measurements_1d`  | 1 day  |

Each gauge has `_avg` / `_min` / `_max` columns, each counter `_start` / `_end` / `_delta`.
Gauges are drawn as lines from `_avg` (the `min / max` switch adds thin dashed lines for the
bucket extremes), counters as bars from `_delta` — a bar is "energy in this bucket", not a
running total.

| Page | Signals | Notes |
|------|---------|-------|
| Temperatury | `inside_temp`, `outside_temp`, `buff_top_temp`, `furnace_temp` | lines, °C |
| Bateria | `battery_soc`; `battery_charge_total`, `battery_discharge_total` | SOC line on the left axis (0–100 %), energy bars on the right axis (kWh); discharge is drawn below zero so the two bar series cannot overlap on a time axis |
| Moc | `pv1_power`, `pv2_power`, `load_power_l1..l3` | lines, W; the `sumuj PV / fazy` switch replaces the five lines with two sums (PV1+PV2, L1+L2+L3) |
| Energia | `load_energy_total` | bars, kWh, plus the total for the range; no `min / max` switch, a counter has no extremes |

With grouping *and* `min / max` on, the dashed lines are the sums of the members' per-bucket
minima and maxima — the envelope of the sum, not the extremes of the summed signal.

`/temperatures/chart?params=a,b,c` is the same `ChartPage` machinery with a *dynamic*
`signals` list instead of a fixed one: `/temperatures` lets you check any subset of its 10
sensors, and the chart page builds `Signal`s for just the checked names from the query
string (unknown names are dropped, not turned into a `Signal`). `return_water_temp` is
one of the 10 but metrica does not collect it yet (see `metrica.json`), so selecting it
alone will show an empty chart - the live value on `/temperatures` is unaffected, since
that comes straight from MQTT.

Adding a *fixed* chart is one subclass: declare `signals`, `y_axes` and optionally
`groups`, and the shared `ChartPage` supplies the range toggle, switches, refresh timer
and footer statistics.

```python
class PowerPage(ChartPage):
    title = 'Moc'
    key = 'power'                       # prefix for app.storage.user keys
    y_axes = [{'name': 'W'}]
    signals = [Signal('pv1_power', 'PV1', '#ffd54f', unit='W', group='pv'), ...]
    groups = [Group('pv', 'PV (1+2)', '#ffca28', ('pv1_power', 'pv2_power'), unit='W'), ...]
```

The database is opened read-only (`file:...?mode=ro`). If SQLite cannot open it that way — an
orphaned `-wal` file that needs recovery — the connection falls back to a normal open with
`PRAGMA query_only = 1`, so even the fallback path cannot write. Connections are short-lived
and every query runs in a worker thread (`run.io_bound`), so a slow SD card never blocks the
event loop or other clients.

NULL is not zero: buckets without a value are skipped, so a signal that metrica has not seen
yet simply has no line instead of a fake zero baseline.

## Layout

```
cavewebrun.py            entry point: argparse + ui.run
caveweb.example.json     configuration template (copy to caveweb.json)
caveweb.service          systemd unit
scripts/
    comfort_stub.py       manual dev tool: random cave/comfort payload, not a service
caveweb/
    __init__.py          registers pages, starts the MQTT client on startup
    config.py            database path, broker, ui.run arguments
    db.py                read-only access to the metrica rollup tables
    mqttclient.py        subscribe-only client + last-value cache
    live.py              live value definitions, readout with fallback, panels
    topics.py            MQTT topic conventions in one place
    heating_params.py    copy of PARAMS_HEATING metadata (topic, type, range)
    chartpage.py         shared chart page: ranges, min/max, grouping, refresh
    widgets.py           header (back = browser history, not a fixed URL - one
                         chart page is opened from several places), tiles, section headers,
                         number_stepper (large +/- buttons for every ui.number - a touchscreen
                         can't reliably hit the native input[type=number] spin arrows)
    pages/
        home.py          "/home"                 tiles with live values
        boiler.py        "/boiler"               CO boiler readouts
        boiler_config.py "/boiler/config"        all setpoints from PARAMS_HEATING
        comfort.py        "/comfort"              temperature + floor valve/pump, config form
        recuperation.py   "/recuperation"         humidity/CO2/air quality, presentation only
        pv.py            "/pv"                   inverter readouts
        charts.py        "/charts"               chart tiles
        temperature.py   "/charts/temperature"
        battery.py       "/charts/battery"
        power.py         "/charts/power"
        energy.py        "/charts/energy"
tests/                   plain scripts (db, config, chart logic, live values, pages)
```

## Configuration

Copy the template and edit it — `caveweb.json` is in `.gitignore`, because it holds local
paths and the session `storage_secret`:

```bash
cp caveweb.example.json caveweb.json
```

```json
{
  "database": { "path": "/home/sqna/cave/raspberry/metrica/measurements.db" },
  "mqtt": { "host": "127.0.0.1", "port": 1883, "client_id": "caveweb", "topics": ["cave/#"] },
  "http": { "host": "0.0.0.0", "port": 8081, "storage_secret": "zmien-ten-sekret" },
  "ui": { "refresh_seconds": 60 }
}
```

Everything is optional. `http` accepts the keys listed in `config.HTTP` and passes them
straight to `ui.run()`; `mqtt` the keys from `config.MQTT`. An unknown key is a startup error,
not a silent no-op. Narrow `mqtt.topics` if you do not want the whole `cave/#` tree in memory.

Resolution order for the database path: `--db`, then `database.path` from the config file, then
the `CAVE_DB_PATH` environment variable, then the first existing candidate in `config.py`.

## Running

```bash
pip install -r requirements.txt
python cavewebrun.py --config caveweb.json
```

Then open `http://<raspberry-ip>:8081`. Without `--config` (or when the default `caveweb.json`
is absent) the defaults from `caveweb/config.py` apply. `--db` and `--port` override single
values, which is handy for a second instance against a copy of the database.

## Service

```bash
sudo cp caveweb.service /etc/systemd/system/
sudo systemctl enable --now caveweb
journalctl -u caveweb -f
```

The shipped unit expects a virtualenv at `/home/sqna/venv/cave` and the checkout at
`/home/sqna/cave/raspberry/caveweb`; adjust `User`, `WorkingDirectory` and `ExecStart` to
match your paths.

## HTTPS on port 443

`ui.run()` forwards `ssl_certfile`/`ssl_keyfile` straight to uvicorn, so serving HTTPS is
just two `caveweb.json` keys plus a certificate - no code change. Binding 443 needs a
capability most non-root services don't have; the unit grants it narrowly (to this
process only, not the whole venv's `python3` the way `setcap` on the binary would):

```ini
# add under [Service] in caveweb.service
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
```

Generate a self-signed certificate on the device itself (the private key never needs to
leave it) and point `caveweb.json` at it:

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
  -keyout certs/caveweb.key -out certs/caveweb.crt \
  -subj "/CN=$(hostname -I | awk '{print $1}')"
```

```json
"http": {
  "port": 443,
  "ssl_certfile": "/home/sqna/cave/raspberry/caveweb/certs/caveweb.crt",
  "ssl_keyfile": "/home/sqna/cave/raspberry/caveweb/certs/caveweb.key"
}
```

Self-signed means every browser warns on first visit to this device - there is no CA
behind it, only encryption-in-transit on a LAN panel. Accept/trust it once per browser.

## Kiosk: fullscreen on the Pi's own screen

Three independent **user** systemd units (install under `~/.config/systemd/user/`,
`WantedBy=default.target`, same shape as the existing `heatapp.service` for `caveapp`)
turn the Pi's attached display into a kiosk showing this dashboard:

```bash
mkdir -p ~/.config/systemd/user
cp caveweb-kiosk.service screen-idle.service kiosk-watchdog.service ~/.config/systemd/user/
systemctl --user daemon-reload
```

**`caveweb-kiosk.service`** - Chromium in kiosk mode against the local HTTPS URL.
`--ignore-certificate-errors` is required for the self-signed cert above: kiosk mode has
no address bar, so there is no way to click through the usual browser warning.

**Do not enable this while `caveapp`'s `heatapp.service` is still running** - both set
themselves fullscreen/always-on-top, and they'll fight over the foreground. Switch over
with:

```bash
systemctl --user stop heatapp.service
systemctl --user enable --now caveweb-kiosk.service
```

**`screen-idle.service`** - blanks the physical screen after a period of no touch/input and
wakes it on the next one, independent of whichever app is in front (it operates on the
Wayland output directly, not on a window). Safe to enable regardless of which kiosk app is
running:

```bash
systemctl --user enable --now screen-idle.service
```

It replaces the equivalent logic that `caveapp/screenctrl.py` embeds in its own process (PySide6
cursor polling + `wlr-randr`) with `swayidle`, the standard idle daemon for wlroots compositors -
no Qt dependency, no custom polling loop. While `heatapp.service` is still active its embedded
screen controller does the same thing on the same default timeout, which is redundant but
harmless (both issue the same idempotent `wlr-randr` calls) until `caveapp` is eventually
retired.

Configurable from **`/settings`** on the dashboard itself (on/off, timeout in seconds, whether
to restart `wayvnc` on wake - not always needed, and a wasted restart if it isn't) rather than
by editing the unit. `screen_idle_runner.py` is a thin wrapper: `swayidle` itself always runs,
with `timeout` fixed at whatever the settings said when the process last started - the one value
genuinely baked into its startup arguments. The on-idle and on-resume commands it hands to
`swayidle`, though, call back into this same script (`--off`/`--resume`), which re-reads the
settings file **live, on every single event**: `enabled` gates whether `--off` actually blanks
the screen, and `restart_wayvnc_on_wake` gates the wayvnc restart on `--resume` - `--resume`
itself always turns the screen back on regardless of `enabled`, so a stray touch never leaves you
stuck looking at a blank screen. Net effect: toggling either of those two switches on `/settings`
takes effect on the very next idle/resume event, with no restart at all. Only a changed
`timeout_seconds` still needs `systemctl --user restart screen-idle.service` (which `/settings`
runs for you, only when that value actually changed) since it can't be picked up without
restarting `swayidle`'s own process.

**`kiosk-watchdog.service`** (`kiosk_watchdog.py`) - a once-per-boot recovery check for a
specific failure seen after a Pi reset: the kiosk came up with the screen blanked and touch
unresponsive, most likely because Chromium/the session started before the Wayland/input stack
was fully ready. The watchdog waits up to 5 minutes after boot for *any* input activity (via the
same `swayidle` mechanism, independently of `screen-idle.service`'s own instance - multiple
`swayidle` clients can watch the same compositor's idle state at once). If none arrives in that
window, it forces the screen on and restarts `caveweb-kiosk.service` once. A marker file under
`XDG_RUNTIME_DIR` (tmpfs - cleared on every reboot) makes this strictly one-shot per boot: a
second instance of this unit (e.g. from the kiosk restarting on its own later) finds the marker
and exits immediately, so it can't turn into a restart loop if the real problem is something
else entirely.

## Tests

No framework, no live data, no network — each file is a plain script that prints `OK`/`FAIL`
and exits non-zero on failure:

```bash
python tests/test_db.py
python tests/test_config.py
python tests/test_chartpage.py
python tests/test_live.py
python tests/test_pages.py
python tests/test_refuels.py
python tests/test_fuel_level.py
python tests/test_settings.py
python tests/test_feeder_log.py
python tests/test_furnace_boost.py
python tests/test_relay_control.py
python tests/test_boiler_config.py
```

`test_db.py` builds a temporary database with metrica's schema. `test_config.py` covers the
JSON overrides, including that an unknown `http`/`mqtt` key fails at startup. `test_live.py`
feeds payloads into the cache and checks parsing, per-publisher fields, sums (including partial
ones), staleness, the database fallback, and `publish()` (with and without a started client).
`test_pages.py` validates the screen declarations: every value has a `cave/...` topic, labels
within a panel are unique (a duplicate would silently drop a row), the configuration page covers
every setpoint, and every module in `caveweb/pages/` is actually imported by
`caveweb/__init__.py` (a page whose import is missing still passes every other check and 404s in
production - this caught exactly that bug once already). `test_chartpage.py` checks the
generated ECharts series. `test_refuels.py` covers the append-only log round-trip and
`coefficient_for()` - which pairs count, which don't, and that an interval is attributed to the
bag size that was actually burning. `test_fuel_level.py` covers the level-replay model: resets on
a full fill, adds on a partial one, caps at tank capacity, and picks up a measured coefficient
over the hardcoded starting one once real pairs exist, and the `projected_daily_kwh` linear
extrapolation (including the midnight division-by-zero edge). `test_settings.py` covers the
screen-idle settings round-trip, defaults on a missing or partial file, and that a corrupt file
falls back instead of raising. `test_feeder_log.py` covers the refuel-comment format and that it
appends without disturbing existing content. `test_furnace_boost.py` covers the boost/cancel/expiry
state machine: refusing to start without a live setpoint, refusing a second concurrent boost,
clamping to the setpoint's configured max, a custom delta/duration overriding the defaults, the
pump getting its own higher-priority `flash_on` on the same start and a short re-armed one on
cancel, and `check_expired()` reverting correctly both within a running session and on the
first check after a simulated restart. `test_relay_control.py` covers discovery purely from cache
contents (module list from bitmask topics only, channel-number-to-name mapping from per-channel
topics, a channel that's never published anything showing as `ch<N>` with blank fields instead of
an assumed "off") and `send_command()`'s payload shape for each action, including the default
duration/TTL and a publish failure. `test_boiler_config.py` covers `clamp_value()` (type coercion,
clamping at both ends, int rounding) and `save_to_broker()` against fake input widgets: one
publish per setpoint, an out-of-range value going out clamped rather than as-typed, an empty field
skipped rather than publishing `null`, and that a publish failure doesn't raise. None of these
exercise `screen_idle_runner.py` or `kiosk_watchdog.py`
themselves (`swayidle`/`wlr-randr`/a real compositor aren't available to test against) - only the
pure logic each depends on. If `nicegui` is not installed the tests substitute a stub for it —
only the package imports it, not the logic under test.

## License

MIT
