"""Testy symulacji doby ladowania.

To jest glowny test gwarancji: niezaleznie od cen, auto laduje sie przez
co najmniej N godzin dziennie - takze wtedy, gdy Home Assistant byl
wylaczony w najtanszych godzinach.
"""

import pytest

from tgerdn.simulate import _load_fixture_payload, _scale_payload, simulate_day

pytest.importorskip('yaml')


@pytest.fixture(scope='module')
def fixture_payload(tariff):
    payload, _ = _load_fixture_payload(tariff)
    return payload


def test_zwykly_dzien_daje_piec_godzin(ha_config, fixture_payload):
    result = simulate_day(ha_config, fixture_payload)
    assert result['charged_count'] == 5
    # Plan trzyma godziny TGE (1..24), symulacja - godziny zegara (0..23).
    assert result['charged_hours'] == [hour - 1 for hour in result['plan_hours']]


def test_dzien_drogi_nadal_daje_piec_godzin(ha_config, fixture_payload):
    result = simulate_day(ha_config, _scale_payload(fixture_payload, 2.5))
    assert result['charged_count'] == 5


def test_dzien_tani_daje_co_najmniej_piec_godzin(ha_config, fixture_payload):
    result = simulate_day(ha_config, _scale_payload(fixture_payload, 0.4))
    assert result['charged_count'] >= 5


def test_ha_padl_przed_oknem_okno_sie_odbudowuje(ha_config, fixture_payload):
    """Najtansze godziny minely - trzeba dociagnac do limitu."""
    result = simulate_day(ha_config, fixture_payload, out_of_service=(2, 3, 4))
    assert result['charged_count'] == 5, result['charged_hours']


def test_ha_padl_przed_oknem_odbija_najtansze_godziny(ha_config, fixture_payload):
    result = simulate_day(ha_config, fixture_payload, out_of_service=(2, 3, 4))
    plan = result['plan_hours']
    # Godziny planu, ktore minely i nie zostaly naladowane, nie wliczaja sie
    # do naladowania - ale limit 5 h jest dotrzymany.
    assert len(result['charged_hours']) == 5
    assert set(plan) - set(result['charged_hours']) != set()


def test_okno_jest_stabilne(ha_config, fixture_payload):
    result = simulate_day(ha_config, fixture_payload)
    assert len(result['windows']) == 1


def test_wszystkie_scenariusze_sa_zgodne_z_gwarancja(ha_config, fixture_payload):
    scenariusze = [
        (fixture_payload, ()),
        (fixture_payload, (2, 3, 4)),
        (fixture_payload, (13, 14)),
        (_scale_payload(fixture_payload, 2.5), ()),
        (_scale_payload(fixture_payload, 0.4), ()),
    ]
    for payload, outage in scenariusze:
        result = simulate_day(ha_config, payload, out_of_service=outage)
        assert result['charged_count'] >= 5, (outage, result['charged_hours'])
