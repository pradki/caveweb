"""Testy wczytywania konfiguracji JSON."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from caveweb import config  # noqa: E402


@pytest.fixture(autouse=True)
def restore_defaults(monkeypatch):
    """Każdy test dostaje własne kopie globalnych wartości modułu."""
    monkeypatch.setattr(config, 'DB_PATH', Path('/domyslna/measurements.db'))
    monkeypatch.setattr(config, 'REFRESH_SECONDS', 60.0)
    monkeypatch.setattr(config, 'HTTP', dict(config.HTTP))


def write_config(tmp_path, payload) -> Path:
    path = tmp_path / 'caveweb.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


def test_load_overrides_db_refresh_and_http(tmp_path):
    path = write_config(tmp_path, {
        'database': {'path': '/z/pliku/measurements.db'},
        'ui': {'refresh_seconds': 15},
        'http': {'port': 9000, 'storage_secret': 'tajne'},
    })
    assert config.load(path) == path
    assert config.DB_PATH == Path('/z/pliku/measurements.db')
    assert config.REFRESH_SECONDS == 15.0
    assert config.HTTP['port'] == 9000
    assert config.HTTP['storage_secret'] == 'tajne'
    assert config.HTTP['host'] == '0.0.0.0'  # nietknięte zostaje domyślne


def test_db_argument_wins_over_file(tmp_path):
    path = write_config(tmp_path, {'database': {'path': '/z/pliku/measurements.db'}})
    config.load(path, db='/z/linii/polecen.db')
    assert config.DB_PATH == Path('/z/linii/polecen.db')


def test_unknown_http_key_is_an_error(tmp_path):
    path = write_config(tmp_path, {'http': {'porrt': 9000}})
    with pytest.raises(ValueError, match='http.porrt'):
        config.load(path)


def test_missing_file_raises_when_required(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.load(tmp_path / 'nie-ma.json')


def test_missing_file_is_fine_when_optional(tmp_path):
    assert config.load(tmp_path / 'nie-ma.json', required=False) is None
    assert config.DB_PATH == Path('/domyslna/measurements.db')


def test_env_variable_wins_in_resolve(monkeypatch):
    monkeypatch.setenv('CAVE_DB_PATH', '/ze/srodowiska.db')
    assert config.resolve_db_path() == Path('/ze/srodowiska.db')
