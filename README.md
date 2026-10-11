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
| `/home` | A clock (`YYYY-MM-DD HH:MM:SS`) on the right of the header. Tiles: **Wykresy**, **Kocioł CO** (fuel level next to the title, furnace temperature + today's/projected coal energy on the tile), **PV** (PV power next to the title, battery SOC + load on the tile), **Temperatury** (outside/inside on the tile), **Rolety** and **Nawadnianie** (placeholders, no action yet) |
| `/boiler` | Furnace, flue gas, feeder, return, DHW and fireplace-return temperatures; buffer top/bottom, inside and outside; one card per device (fan, feeder) with its total and today's runtime, feeder also showing today's coal in kg/kWh; the key setpoints; **Wypalanie** button — see [Burning off](#burning-off-a-temporary-self-reverting-setpoint-boost) |
| `/boiler/config` | Every setpoint from `PARAMS_HEATING` — current value from the broker next to an input bounded by the parameter's own min/max. **Saving is not wired yet** (see below) |
| `/boiler/refuel` | Log a feeder refuel: bag count, bag size (20/25 kg, remembered), whether filled to full — see [Writing data: the refuel log](#writing-data-the-refuel-log) |
| `/pv` | PV total and per string, battery SOC and power, load total and per phase, today's battery charge/discharge and the consumption meter |
| `/temperatures` | All 10 temperature sensors live, each with a checkbox; **Pokaż na wykresie** opens `/temperatures/chart` plotting only the checked ones. The selection is remembered per browser session |
| `/relays` | Pick a waveshare-mqtt-gateway module, then every one of its channels: number, name, state, who holds it and at what priority, and an **Akcja** button to force on/off/flash_on — see [Relays](#relays-manual-channel-control) |
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

Publishing to `cave/heating/setpoints/#` changes how the furnace runs, and for most of them this
app only ever listens. `/boiler/config`'s **Zapisz** button is still disabled for exactly that
reason: enabling it for every setpoint means a lot more surface to get wrong. One setpoint is the
deliberate exception - see "Burning off" below.

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

`/boiler`'s **Wypalanie** button (`caveweb/furnace_boost.py`) is the one place this app issues an
actual command instead of reporting a status: it raises `furnace_temp_setpoint` by 10°C for ten
minutes, to run the furnace hot enough to burn off buildup, then puts the original value back by
itself. That's a real exception to "this app never controls the furnace" (see "Writing setpoints"
above), so it's deliberately narrow and always self-reverting:

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
threshold has fired yet. It needs no explicit "off" or revert: a `flash_on` lease is a hardware
pulse that expires on its own, same failure-safe shape as every other relay command in this
project. After it expires, `heating-controller`'s own reactive logic is expected to pick the pump
back up anyway, since the furnace is normally still hot enough to exceed the (by-then-reverted,
lower) setpoint by more than its margin.

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
caveweb/
    __init__.py          registers pages, starts the MQTT client on startup
    config.py            database path, broker, ui.run arguments
    db.py                read-only access to the metrica rollup tables
    mqttclient.py        subscribe-only client + last-value cache
    live.py              live value definitions, readout with fallback, panels
    topics.py            MQTT topic conventions in one place
    heating_params.py    copy of PARAMS_HEATING metadata (topic, type, range)
    chartpage.py         shared chart page: ranges, min/max, grouping, refresh
    widgets.py           header, tiles, section headers
    pages/
        home.py          "/home"                 tiles with live values
        boiler.py        "/boiler"               CO boiler readouts
        boiler_config.py "/boiler/config"        all setpoints from PARAMS_HEATING
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
clamping to the setpoint's configured max, the pump getting its own higher-priority `flash_on` on
the same start, and `check_expired()` reverting correctly both within a running session and on the
first check after a simulated restart. `test_relay_control.py` covers discovery purely from cache
contents (module list from bitmask topics only, channel-number-to-name mapping from per-channel
topics, a channel that's never published anything showing as `ch<N>` with blank fields instead of
an assumed "off") and `send_command()`'s payload shape for each action, including the default
duration/TTL and a publish failure. None of these exercise
`screen_idle_runner.py` or `kiosk_watchdog.py`
themselves (`swayidle`/`wlr-randr`/a real compositor aren't available to test against) - only the
pure logic each depends on. If `nicegui` is not installed the tests substitute a stub for it —
only the package imports it, not the logic under test.

## License

MIT
