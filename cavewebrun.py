"""Uruchomienie aplikacji cave (NiceGUI).

    python cavewebrun.py
    python cavewebrun.py --config caveweb.json
    python cavewebrun.py --db /home/sqna/metrica/measurements.db --port 8082

Bez `--config` (albo gdy domyślny `caveweb.json` nie istnieje) wchodzą wartości
domyślne z caveweb/config.py.
"""
from __future__ import annotations
__version__ = "0.2"

import argparse
from pathlib import Path

import caveweb
from caveweb import config

DEFAULT_CONFIG = Path(__file__).with_name('caveweb.json')


def parse_args():
    parser = argparse.ArgumentParser(description='caveweb – wykresy pomiarów cave (NiceGUI)')
    parser.add_argument('--config', default=str(DEFAULT_CONFIG),
                        help='plik konfiguracji JSON (domyślnie caveweb.json obok skryptu)')
    parser.add_argument('--db', help='nadpisuje database.path z konfiguracji')
    parser.add_argument('--port', type=int, help='nadpisuje http.port z konfiguracji')
    parser.add_argument('--version', action='version', version=f'caveweb {caveweb.__version__}')
    return parser.parse_args()


args = parse_args()
# domyślnej ścieżki nie wymagamy – brak pliku znaczy "jedziemy na domyślnych"
loaded = config.load(args.config, db=args.db,
                     required=Path(args.config) != DEFAULT_CONFIG)
if args.port:
    config.HTTP['port'] = args.port

print(f'caveweb {caveweb.__version__}: konfiguracja {loaded or "domyślna"}, '
      f'baza {config.DB_PATH}, port {config.HTTP["port"]}')

caveweb.ui.run(**config.HTTP)
