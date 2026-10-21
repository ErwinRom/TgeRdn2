"""Testy kontraktu JSON i zapisu plikow."""

import json

import pytest

from tgerdn.publisher import (
    empty_payload,
    read_payload,
    write_payload,
)


def test_payload_zawiera_wszystkie_klucze(payload):
    for key in ('version', 'day', 'fetched_at', 'data_fetched', 'data_points',
                'unit', 'tariff', 'fixing_i_prices', 'prices', 'plan', 'stats'):
        assert key in payload, f'brak klucza {key}'


def test_payload_ma_24_godziny(payload):
    assert payload['data_points'] == 24
    assert len(payload['fixing_i_prices']) == 24
    assert len(payload['prices']) == 24


def test_godziny_sa_od_1_do_24(payload):
    assert [entry['hour'] for entry in payload['fixing_i_prices']] == list(range(1, 25))


def test_klucze_wstecznie_zgodne_z_v1(payload):
    """Stare szablony czytaja `hour` i `fixing_i_price_pln_kwh` - musza dzialac."""
    entry = payload['fixing_i_prices'][0]
    assert set(entry) >= {'data_dostawy', 'hour', 'fixing_i_price_pln_kwh'}
    assert entry['data_dostawy'] == payload['day']


def test_cena_w_przeliczeniu_na_kwh(payload):
    entry = payload['fixing_i_prices'][0]
    assert entry['fixing_i_price_pln_kwh'] == pytest.approx(0.60177)
    assert entry['total'] == pytest.approx(entry['fixing_i_price_pln_kwh'] + entry['margin'])


def test_dtime_jest_poczatkiem_przedzialu(payload):
    entry = payload['prices'][0]
    assert entry['dtime'] == f"{payload['day']}T00:00:00"
    assert entry['period'] == '00:00-01:00'


def test_plan_w_payloadzie(payload, plan):
    assert payload['plan']['hours'] == list(plan.hours)
    assert payload['plan']['count'] == 5


def test_tariff_w_payloadzie(payload, tariff):
    assert payload['tariff']['charging_hours'] == tariff.charging_hours
    assert payload['tariff']['window_hours'] == list(tariff.window_hours)


def test_pusty_payload(tariff):
    payload = empty_payload('2026-10-22', tariff, label='tomorrow')
    assert payload['data_fetched'] is False
    assert payload['data_points'] == 0
    assert payload['fixing_i_prices'] == []
    assert payload['plan'] is None


def test_zapis_tworzy_plik(tmp_path, payload):
    path = tmp_path / 'today.json'
    assert write_payload(path, payload) is True
    assert path.exists()
    assert json.loads(path.read_text(encoding='utf-8'))['day'] == payload['day']


def test_zapis_jest_atomowy_i_nie_zostawia_smiatek(tmp_path, payload):
    path = tmp_path / 'today.json'
    write_payload(path, payload)
    leftovers = [p for p in tmp_path.iterdir() if p.name != 'today.json']
    assert leftovers == []


def test_odczyt_pliku(tmp_path, payload):
    path = tmp_path / 'today.json'
    write_payload(path, payload)
    loaded = read_payload(path)
    assert loaded['day'] == payload['day']


def test_odczyt_brakujacego_pliku(tmp_path):
    assert read_payload(tmp_path / 'nie_ma.json') is None


def test_odczyt_uszkodzonego_pliku(tmp_path):
    path = tmp_path / 'zepsuty.json'
    path.write_text('{ to nie jest json', encoding='utf-8')
    assert read_payload(path) is None
