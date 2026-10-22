"""Testy szablonow Home Assistant z `homeassistant/`.

Renderuja PRAWDZIWE pliki konfiguracyjne (nie kopie logiki), wiec sprawdzaja
dokladnie to, co wjedzie do Home Assistant.
"""

from datetime import datetime

import pytest

yaml = pytest.importorskip('yaml')

from tgerdn.simulate import build_states  # noqa: E402

DAY = datetime(2026, 10, 21)


def render_at(config, payload, hour, *, charged=0, switch_on=False):
    """Renderuje encje HA w danej godzinie i zwraca zbior stanow."""
    moment = DAY.replace(hour=hour)
    states = build_states(payload, payload, charged=charged, switch_on=switch_on)
    config.render_entities(states, moment)
    return states


def realistic_charged(plan_hours, hour):
    """Ile godzin planu zdazylismy naladowac do danej godziny (scenariusz idealny)."""
    return len([h for h in plan_hours if h <= hour])


# ----------------------------------------------------------------- pliki YAML

def test_pliki_ha_sa_poprawnym_yaml(ha_config):
    lovelace = yaml.safe_load(
        (ha_config.ha_dir / 'lovelace_v2.yaml').read_text(encoding='utf-8')
    )
    assert isinstance(lovelace, dict)
    assert 'views' in lovelace
    assert len(lovelace['views']) == 2


def test_automatyzacje_sa_zdefiniowane(ha_config):
    assert len(ha_config.automation) == 2
    ids = {item['id'] for item in ha_config.automation}
    assert 'tge_v2_charging_car' in ids
    assert 'tge_v2_charging_counter' in ids


def test_encje_sa_zdefiniowane(ha_config):
    names = {name for _, name, _, _ in ha_config.entities()}
    assert 'TGE v2 Reguly' in names
    assert 'TGE v2 Aktualna cena' in names
    assert 'TGE v2 najtansze 5h' in names


# ------------------------------------------------------------- renderowanie

def test_szablony_renderuja_sie_dla_kazdej_godziny(ha_config, payload):
    for hour in range(24):
        states = render_at(ha_config, payload, hour, charged=realistic_charged(
            payload['plan']['hours'], hour))
        assert states['sensor.tge_v2_aktualna_cena']['state'] != ''
        assert states['binary_sensor.tge_v2_najtansze_5h']['state'] in ('on', 'off')


def test_cena_biezacej_godziny(ha_config, payload):
    # Godzina zegara 02:00 -> godzina TGE H03
    states = render_at(ha_config, payload, 2)
    expected = payload['fixing_i_prices'][2]['total']
    assert float(states['sensor.tge_v2_aktualna_cena']['state']) == pytest.approx(expected)


def test_cena_poprzedniej_godziny_nie_miesza_sie(ha_config, payload):
    for hour in range(24):
        states = render_at(ha_config, payload, hour)
        expected = payload['fixing_i_prices'][hour]['total']
        assert float(states['sensor.tge_v2_aktualna_cena']['state']) == pytest.approx(expected)


def test_atrybuty_ceny(ha_config, payload):
    states = render_at(ha_config, payload, 2)
    attributes = states['sensor.tge_v2_aktualna_cena']['attributes']
    entry = payload['fixing_i_prices'][2]
    assert float(attributes['spot']) == pytest.approx(entry['fixing_i_price_pln_kwh'])
    assert float(attributes['margin']) == pytest.approx(entry['margin'])
    assert attributes['day'] == payload['day']


# ----------------------------------------------------------------- okno

def test_okno_wlaczone_w_godzinach_planu(ha_config, payload):
    for hour in payload['plan']['hours']:
        states = render_at(ha_config, payload, hour - 1,
                           charged=realistic_charged(payload['plan']['hours'], hour - 1))
        assert states['binary_sensor.tge_v2_najtansze_5h']['state'] == 'on', (
            f'brak ladowania w godzinie {hour - 1:02d}:00')


def test_okno_wylaczone_poza_planem(ha_config, payload):
    plan = payload['plan']['hours']
    for hour in range(24):
        if hour + 1 in plan:
            continue
        states = render_at(ha_config, payload, hour,
                           charged=realistic_charged(plan, hour))
        assert states['binary_sensor.tge_v2_najtansze_5h']['state'] == 'off', (
            f'niepotrzebne ladowanie w godzinie {hour:02d}:00')


def test_okno_stabilne_w_ciagu_doby(ha_config, payload):
    """Plan to N najtanszych godzin dnia - okno nie moze sie przesuwac."""
    plan = payload['plan']['hours']
    windows = set()
    for hour in range(24):
        states = render_at(ha_config, payload, hour,
                           charged=realistic_charged(plan, hour))
        windows.add(states['binary_sensor.tge_v2_najtansze_5h']['attributes']['window_hours'])
    assert len(windows) == 1


def test_odbudowa_okna_gdy_ha_padl_przed_oknem(ha_config, payload):
    """HA padlo o 02:00-04:00 - godziny przepadly, okno musi sie odbudowac."""
    states = render_at(ha_config, payload, 5, charged=0)
    attributes = states['binary_sensor.tge_v2_najtansze_5h']['attributes']
    assert int(attributes['missing_hours']) == 3
    # W oknie zostaje dokladnie tyle godzin, ile jeszcze potrzeba.
    window = [int(h) for h in attributes['window_hours'].split(',')]
    future = [h for h in window if h >= 6]
    assert len(future) == 5


def test_odbudowa_dodaje_najtanssze_godziny(ha_config, payload):
    """Dokladane godziny musza byc najtanszymi z pozostalych."""
    states = render_at(ha_config, payload, 5, charged=0)
    window = [int(h) for h in
              states['binary_sensor.tge_v2_najtansze_5h']['attributes']['window_hours'].split(',')]
    plan = payload['plan']['hours']

    future = [entry for entry in payload['fixing_i_prices']
              if entry['hour'] >= 6 and entry['hour'] not in plan]
    future.sort(key=lambda entry: entry['total'])
    extras = [h for h in window if h not in plan]

    assert extras == [entry['hour'] for entry in future[:len(extras)]]


def test_ladowanie_wlaczya_sie_w_pierwszej_godzinie_odbudowy(ha_config, payload):
    """Po awarii ladowanie wraca w najtanszej dostepnej godzinie."""
    plan = payload['plan']['hours']
    states = render_at(ha_config, payload, 5, charged=0)
    window = [int(h) for h in
              states['binary_sensor.tge_v2_najtansze_5h']['attributes']['window_hours'].split(',')]
    extras = sorted(h for h in window if h not in plan)
    first_extra = extras[0]

    states = render_at(ha_config, payload, first_extra - 1, charged=0)
    assert states['binary_sensor.tge_v2_najtansze_5h']['state'] == 'on'


def test_bez_utraty_godzin_okno_sie_nie_powieksza(ha_config, payload):
    """Gdy wszystkie godziny planu zostaly naladowane, brak godzin do odbudowy."""
    states = render_at(ha_config, payload, 23, charged=5)
    assert int(states['binary_sensor.tge_v2_najtansze_5h']['attributes']['missing_hours']) == 0


# ------------------------------------------------------------ automatyzacja

def test_automatyzacja_wlacza_w_oknie(ha_config, payload):
    moment = DAY.replace(hour=payload['plan']['hours'][0] - 1)
    states = build_states(payload, payload, charged=0, switch_on=False)
    ha_config.render_entities(states, moment)
    assert ha_config.render_condition(ha_config.turn_on_template, states, moment) is True


def test_automatyzacja_wylacza_poza_oknem(ha_config, payload):
    plan = payload['plan']['hours']
    hour = next(h for h in range(1, 25) if h not in plan)
    moment = DAY.replace(hour=hour - 1)
    states = build_states(payload, payload, charged=0, switch_on=True)
    ha_config.render_entities(states, moment)
    assert ha_config.render_condition(ha_config.turn_off_template, states, moment) is True


def test_histereza_wlacza_przy_niskiej_cenie(ha_config, payload):
    """Poza oknem, ale cena ponizej progu - ladowanie zostaje wlaczone."""
    plan = payload['plan']['hours']
    hour = next(h for h in range(1, 25) if h not in plan)
    moment = DAY.replace(hour=hour - 1)
    states = build_states(payload, payload, charged=0, switch_on=False)
    ha_config.render_entities(states, moment)
    states['sensor.tge_v2_aktualna_cena']['state'] = '0.1'
    assert ha_config.render_condition(ha_config.turn_on_template, states, moment) is True


def test_niedostepna_cena_nie_wywraca_szablonu(ha_config, payload):
    moment = DAY.replace(hour=10)
    states = build_states(payload, payload, charged=0, switch_on=False)
    ha_config.render_entities(states, moment)
    states['sensor.tge_v2_aktualna_cena']['state'] = 'unavailable'
    assert ha_config.render_condition(ha_config.turn_on_template, states, moment) is False
    assert ha_config.render_condition(ha_config.turn_off_template, states, moment) is False


def test_brak_danych_wylacza_ladowanie_poza_oknem(ha_config, payload):
    """Cena nieznana poza oknem = wylacz ladowanie (nie palimy prad za nic)."""
    plan = payload['plan']['hours']
    hour = next(h for h in range(1, 25) if h not in plan)
    moment = DAY.replace(hour=hour - 1)
    states = build_states(payload, payload, charged=0, switch_on=True)
    ha_config.render_entities(states, moment)
    states['sensor.tge_v2_aktualna_cena']['state'] = 'unavailable'
    assert ha_config.render_condition(ha_config.turn_off_template, states, moment) is True


def test_brak_danych_nie_wylacza_ladowania_w_oknie(ha_config, payload):
    """W oknie ladujemy nawet wtedy, gdy cena chwilowo nie jest znana."""
    moment = DAY.replace(hour=payload['plan']['hours'][0] - 1)
    states = build_states(payload, payload, charged=0, switch_on=True)
    ha_config.render_entities(states, moment)
    states['sensor.tge_v2_aktualna_cena']['state'] = 'unavailable'
    assert ha_config.render_condition(ha_config.turn_off_template, states, moment) is False


def test_limit_ceny_dziala(ha_config, payload):
    """max_charge_price > 0 blokuje ladowanie w drogiej godzinie."""
    plan = payload['plan']['hours']
    hour = next(h for h in range(1, 25) if h not in plan)
    moment = DAY.replace(hour=hour - 1)
    states = build_states(payload, payload, charged=0, switch_on=False)
    ha_config.render_entities(states, moment)
    states['sensor.tge_v2_reguly']['attributes']['max_charge_price'] = '0.01'
    assert ha_config.render_condition(ha_config.turn_on_template, states, moment) is False


def test_przelacznik_nie_jest_tlyiony_gdy_juz_wlaczony(ha_config, payload):
    """Automatyzacja nie wylacza przelacznika, ktory juz jest wlaczony."""
    moment = DAY.replace(hour=10)
    states = build_states(payload, payload, charged=0, switch_on=True)
    ha_config.render_entities(states, moment)
    states['sensor.tge_v2_reguly']['attributes']['max_charge_price'] = '0.01'
    assert ha_config.render_condition(ha_config.turn_off_template, states, moment) is True
