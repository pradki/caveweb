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
| `/home` | Tiles: **Wykresy**, **Kocioł CO** (furnace temperature on the tile), **PV** (PV power, battery SOC, load), **Rolety** and **Nawadnianie** (placeholders, no action yet) |
| `/boiler` | Furnace, flue gas, feeder, return, DHW and fireplace-return temperatures; buffer top/bottom, inside and outside; fan and feeder state plus their runtime today; the key setpoints |
| `/boiler/config` | Every setpoint from `PARAMS_HEATING` — current value from the broker next to an input bounded by the parameter's own min/max. **Saving is not wired yet** (see below) |
| `/pv` | PV total and per string, battery SOC and power, load total and per phase, today's battery charge/discharge and the consumption meter |
| `/charts/*` | Temperatures, battery, power, energy — see [Charts](#charts) |

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
| `cave/heating/setpoints/<name>` | `value` | `{"value": 62}` |
| `cave/relay/<module>/<alias>/status` | `state` | `{"state": true}` |
| `cave/relay/<module>/<alias>/counters` | `today_s`, `total_s` | `{"today_s": 5400, ...}` |

Most publishers use `retain=True`, so the broker replays the current state right after the
subscription and the screens are populated within a second of a restart. The client connects
with `connect_async`, which means a broker that is not up yet (typical during boot) delays the
values but never the web server.

A screen declares a value like this — one topic, or several to be summed:

```python
live.value_of('Piec', topics.sensor('furnace_temp'), unit='°C', digits=1)
live.sum_of('Moc PV', [topics.deye('pv1_power'), topics.deye('pv2_power')], unit='W', digits=0)
live.value_of('Dmuchawa dziś', topics.relay_counters('co_fan'), kind='seconds', key='today_s')
```

### Boiler parameters

`caveweb/heating_params.py` is a **copy** of `PARAMS_HEATING` from the heating service's
`shadow_vault.py`, trimmed to what the UI needs: topic, type, range, unit, description. A copy
rather than an import, because caveweb is a standalone service that integrates only through
MQTT and has no access to the `cave` tree. `source_type` splits the dictionary into setpoints
(editable) and sensors (read-only), and both `/boiler` and `/boiler/config` build themselves
from it — a new parameter in the heating service means regenerating this one file.

### Writing setpoints

Publishing to `cave/heating/setpoints/#` changes how the furnace runs, and this app has so far
only ever listened. So the configuration page renders the inputs and the current values but the
**Zapisz** button is disabled: enabling it means adding a `publish()` to `mqttclient` and
wiring the button to it. Deliberate decision, not an oversight.

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

Adding a chart is one subclass: declare `signals`, `y_axes` and optionally `groups`, and the
shared `ChartPage` supplies the range toggle, switches, refresh timer and footer statistics.

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

## Tests

No framework, no live data, no network — each file is a plain script that prints `OK`/`FAIL`
and exits non-zero on failure:

```bash
python tests/test_db.py
python tests/test_config.py
python tests/test_chartpage.py
python tests/test_live.py
python tests/test_pages.py
```

`test_db.py` builds a temporary database with metrica's schema. `test_config.py` covers the
JSON overrides, including that an unknown `http`/`mqtt` key fails at startup. `test_live.py`
feeds payloads into the cache and checks parsing, per-publisher fields, sums (including partial
ones), staleness and the database fallback. `test_pages.py` validates the screen declarations:
every value has a `cave/...` topic, labels within a panel are unique (a duplicate would
silently drop a row), and the configuration page covers every setpoint. `test_chartpage.py`
checks the generated ECharts series. If `nicegui` is not installed the tests substitute a stub
for it — only the package imports it, not the logic under test.

## License

MIT
