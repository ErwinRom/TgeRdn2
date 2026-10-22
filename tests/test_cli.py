"""Testy wiersza polecen (bez sieci - pobieranie jest podmienione)."""

import json
from datetime import date

import pytest

from tgerdn import cli


@pytest.fixture(autouse=True)
def frozen_today(monkeypatch, fixings):
    """'Dzis' = doba z fixture - inaczej testy zaleza od daty systemowej."""
    fixture_day = date.fromisoformat(fixings[0].day)

    class FrozenDate(date):
        @classmethod
        def today(cls):
            return cls.fromordinal(fixture_day.toordinal())

    monkeypatch.setattr(cli, 'date', FrozenDate)


@pytest.fixture
def output_dir(tmp_path):
    return tmp_path / 'out'


def _args(output_dir, *extra):
    return cli.build_parser().parse_args(['fetch', '--output-dir', str(output_dir), *extra])


def test_fetch_zapisuje_oba_pliki(monkeypatch, output_dir, fixings):
    monkeypatch.setattr(cli, '_fetch_day', lambda day, settings: ('ok', fixings, 'http://test'))

    assert cli.cmd_fetch(_args(output_dir)) == 0

    today = json.loads((output_dir / 'today.json').read_text(encoding='utf-8'))
    tomorrow = json.loads((output_dir / 'tomorrow.json').read_text(encoding='utf-8'))
    assert today['data_fetched'] is True
    assert today['data_points'] == 24
    assert today['plan']['count'] == 5
    # Fixture zawiera tylko 2026-10-21, wiec plik na jutro jest pusty.
    assert tomorrow['data_fetched'] is False
    assert tomorrow['day'] != today['day']


def test_fetch_gdy_brak_danych_zapisuje_pusty_payload(monkeypatch, output_dir):
    """TGE nie opublikowal jeszcze jutra - plik musi byc pusty, nie cudzy."""
    monkeypatch.setattr(cli, '_fetch_day', lambda day, settings: ('ok', [], 'http://test'))

    cli.cmd_fetch(_args(output_dir))

    payload = json.loads((output_dir / 'tomorrow.json').read_text(encoding='utf-8'))
    assert payload['data_fetched'] is False
    assert payload['data_points'] == 0
    assert payload['fixing_i_prices'] == []


def test_fetch_przy_bledzie_nie_tknie_starego_pliku(monkeypatch, output_dir):
    output_dir.mkdir(parents=True)
    path = output_dir / 'today.json'
    path.write_text('{"day": "stary"}', encoding='utf-8')

    monkeypatch.setattr(cli, '_fetch_day', lambda day, settings: ('error', [], 'http://test'))

    cli.cmd_fetch(_args(output_dir))

    assert json.loads(path.read_text(encoding='utf-8'))['day'] == 'stary'


def test_fetch_zachowuje_plan_z_poprzedniego_zapisu(monkeypatch, output_dir, fixings):
    """Plan musi byc stabilny w ciagu dnia - nie moze sie przesunac."""
    output_dir.mkdir(parents=True)
    path = output_dir / 'today.json'
    path.write_text(json.dumps({
        'day': fixings[0].day,
        'plan': {'hours': [1, 2, 3, 4, 5]},
    }), encoding='utf-8')

    monkeypatch.setattr(cli, '_fetch_day', lambda day, settings: ('ok', fixings, 'http://test'))

    cli.cmd_fetch(_args(output_dir))

    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['plan']['hours'] == [1, 2, 3, 4, 5]


def test_doctor_bez_plikow(output_dir):
    args = cli.build_parser().parse_args(['doctor', '--output-dir', str(output_dir)])
    assert cli.cmd_doctor(args) == 1


def test_doctor_z_plikami(monkeypatch, output_dir, fixings):
    monkeypatch.setattr(cli, '_fetch_day', lambda day, settings: ('ok', fixings, 'http://test'))
    cli.cmd_fetch(_args(output_dir))

    args = cli.build_parser().parse_args(['doctor', '--output-dir', str(output_dir)])
    assert cli.cmd_doctor(args) == 0


def test_show_bez_pliku(output_dir):
    args = cli.build_parser().parse_args(['show', 'today', '--output-dir', str(output_dir)])
    assert cli.cmd_show(args) == 1


def test_show_z_plikiem(monkeypatch, output_dir, fixings, capsys):
    monkeypatch.setattr(cli, '_fetch_day', lambda day, settings: ('ok', fixings, 'http://test'))
    cli.cmd_fetch(_args(output_dir))

    args = cli.build_parser().parse_args(['show', 'today', '--output-dir', str(output_dir)])
    assert cli.cmd_show(args) == 0

    output = capsys.readouterr().out
    assert 'okno lad.' in output
    assert 'oszczednosc' in output
