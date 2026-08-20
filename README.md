# caveweb

NiceGUI dashboard for the cave installation, running as a standalone systemd service on a
Raspberry Pi. The home screen is a grid of touch-friendly tiles; the chart section plots
temperatures, battery, power and energy over four time ranges — day, week, month, year.

It reads a SQLite database and nothing else: no MQTT client, no broker credentials, no writes.
[metrica](https://github.com/pradki/metrica) collects the samples and pre-aggregates them; this app
only draws what is already there. That keeps the UI process cheap enough for a Pi and means it
can be restarted, updated or crashed without any risk to the collected data.

```
  MQTT broker            metrica                measurements.db              caveweb
      │              (collector, writer)       15m / 6h / 1d rollups       (this repo)
      │  sensors           ┌──────────┐          ┌──────────────┐          ┌──────────┐
      └───────────────────▶│  samples │─────────▶│  gauges: avg │◀─ read ──│  NiceGUI │──▶ browser
                           │  buckets │  WAL     │  min / max   │  only    │  ECharts │    :8081
                           └──────────┘          │  counters:   │          └──────────┘
                                                 │  start/end/Δ │
                                                 └──────────────┘
```

## Why read the rollups instead of raw samples

metrica already folds every sample into fixed buckets (15 minutes, 6 hours, 1 day) and stores,
per signal, `_avg` / `_min` / `_max` for gauges and `_start` / `_end` / `_delta` for counters.
A chart therefore never scans raw history: the day view reads at most 96 rows, the year view
365. Picking the table is the whole "query planner":

| Range   | Table              | Bucket |
|---------|--------------------|--------|
| Day     | `measurements_15m` | 15 min |
| Week    | `measurements_6h`  | 6 h    |
| Month   | `measurements_6h`  | 6 h    |
| Year    | `measurements_1d`  | 1 day  |

Gauges are drawn as lines from `_avg`; the `min / max` switch adds thin dashed lines for the
per-bucket extremes. Counters are drawn as bars from `_delta`, so a bar is "energy in this
bucket", not a running total.

The database is opened read-only (`file:...?mode=ro`). If SQLite cannot open it that way — an
orphaned `-wal` file that needs recovery — the connection falls back to a normal open with
`PRAGMA query_only = 1`, so even the fallback path cannot write. Connections are short-lived
and every query runs in a worker thread (`run.io_bound`), so a slow SD card never blocks the
event loop or other clients.

NULL is not zero: buckets without a value are skipped, so a signal that metrica has not seen
yet simply has no line instead of a fake zero baseline.

## Charts

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

## Layout

```
cavewebrun.py            entry point: argparse + ui.run
caveweb.example.json     configuration template (copy to caveweb.json)
caveweb.service          systemd unit
caveweb/
    __init__.py          registers pages, "/" redirects to "/home"
    config.py            database path, refresh interval, ui.run arguments
    db.py                read-only access to the metrica rollup tables
    chartpage.py         shared chart page: ranges, min/max, grouping, refresh
    widgets.py           header and tile widgets
    pages/
        home.py          "/home"                 top level tiles
        charts.py        "/charts"               chart tiles
        temperature.py   "/charts/temperature"
        battery.py       "/charts/battery"
        power.py         "/charts/power"
        energy.py        "/charts/energy"
tests/                   pytest suite (db layer, config loading, chart logic)
```

## Configuration

Copy the template and edit it — `caveweb.json` is in `.gitignore`, because it holds a local
path and the session `storage_secret`:

```bash
cp caveweb.example.json caveweb.json
```

```json
{
  "database": { "path": "/home/sqna/cave/raspberry/metrica/measurements.db" },
  "http": { "host": "0.0.0.0", "port": 8081, "storage_secret": "zmien-ten-sekret" },
  "ui": { "refresh_seconds": 60 }
}
```

Everything is optional; `http` accepts the keys listed in `config.HTTP` and they are passed
straight to `ui.run()`. An unknown key is a startup error, not a silent no-op.

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

```bash
python -m pytest tests -q
```

`tests/test_db.py` builds a temporary database with metrica's schema, so it needs no live data.
`tests/test_chartpage.py` needs `nicegui` importable (it is skipped otherwise) but never starts
a server: it instantiates the page classes without `__init__` and checks the generated ECharts
series — which columns are requested, that counters become bars, that discharge goes below zero
and that grouping collapses five lines into two sums.

## License

MIT
