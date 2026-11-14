"""Swiezosc danych: zrodlo cen wybierane po dacie, brak danych = trzymaj stan.

Plik today.json jest odswiezany po polnocy z opoznieniem (zapis o 00:01 plus
odczyt przez HA), a gdy pobranie sie nie uda - nawet przez wiele godzin. Bez
sprawdzania daty HA uzywalby wczorajszych cen i planu jako dzisiejszych.
"""

import copy
from datetime import datetime

import pytest

yaml = pytest.importorskip('yaml')

from tgerdn.config import Tariff  # noqa: E402
from tgerdn.publisher import empty_payload  # noqa: E402
from tgerdn.simulate import _scale_payload, build_env, build_states  # noqa: E402

DAY = datetime(2026, 10, 21)          # = doba z fixture
W = 'binary_sensor.tge_v2_najtansze_5h'
P = 'sensor.tge_v2_aktualna_cena'


def _yesterday(payload):
    """Wczorajsze dane: inna doba i inne ceny (zeby bylo widac, skad idzie cena)."""
    old = _scale_payload(payload, 3.0)
    old['day'] = '2026-10-20'
    old['plan'] = dict(old['plan'], hours=[1, 2, 3, 4, 5])
    return old


def _render(config, today_file, tomorrow_file, hour, **kwargs):
    moment = DAY.replace(hour=hour, minute=30)
    states = build_states(today_file, tomorrow_file, **kwargs)
    config.render_entities(states, moment)
    return states, moment


def test_po_polnocy_przed_odswiezeniem_pliku_uzywa_pliku_jutra(ha_config, payload):
    """today.json jeszcze z wczoraj, tomorrow.json (z 12:01) = dzisiejsze ceny."""
    old = _yesterday(payload)
    states, _ = _render(ha_config, old, payload, 0)
    assert float(states[P]['state']) == pytest.approx(payload['fixing_i_prices'][0]['total'])
    assert states[P]['attributes']['day'] == payload['day']
    window = [int(h) for h in states[W]['attributes']['window_hours'].split(',')]
    assert window == payload['plan']['hours']


@pytest.mark.parametrize('hour', range(24))
def test_decyzja_nie_zalezy_od_tego_czy_plik_juz_odswiezony(ha_config, payload, hour):
    """Stan sprzed i po odswiezeniu today.json musi byc ten sam - inaczej
    przelacznik mrugalby o polnocy."""
    tomorrow_empty = empty_payload('2026-10-22', Tariff(), label='tomorrow')
    stale, _ = _render(ha_config, _yesterday(payload), payload, hour)
    fresh, _ = _render(ha_config, payload, tomorrow_empty, hour)
    for entity in (W, P):
        assert stale[entity]['state'] == fresh[entity]['state'], (hour, entity)
        assert stale[entity]['attributes'] == fresh[entity]['attributes'], (hour, entity)


def test_zaden_plik_nie_dotyczy_dzisiaj_brak_danych(ha_config, payload):
    """Pobranie nie powiodlo sie, a tomorrow.json tez jest z innej doby."""
    old = _yesterday(payload)
    other = empty_payload('2026-10-22', Tariff(), label='tomorrow')
    states, moment = _render(ha_config, old, other, 10, switch_on=True)
    assert states[P]['state'] == 'unavailable'
    assert states[W]['state'] == 'off'
    assert ha_config.render_condition(ha_config.guard_template, states, moment) is False


def test_stare_dane_nie_wlaczaja_ladowania(ha_config, payload):
    """Wczorajszy plan ([1..5]) nie moze wlaczyc dzisiaj ladowania o 00:30."""
    old = _yesterday(payload)
    other = empty_payload('2026-10-22', Tariff(), label='tomorrow')
    states, moment = _render(ha_config, old, other, 0, switch_on=False)
    assert ha_config.render_condition(ha_config.turn_on_template, states, moment) is False


def test_brak_danych_nie_zmienia_przelacznika_w_zadnej_godzinie(ha_config, payload):
    old = _yesterday(payload)
    other = empty_payload('2026-10-22', Tariff(), label='tomorrow')
    for hour in range(24):
        for switch_on in (True, False):
            states, moment = _render(ha_config, old, other, hour, switch_on=switch_on)
            blocked = not ha_config.render_condition(ha_config.guard_template, states, moment)
            assert blocked, f'{hour:02d}:30 przelacznik={switch_on}'


# --------------------------------------------------------- automatyzacje

def _car(ha_config):
    return next(a for a in ha_config.automation if a['id'] == 'tge_v2_charging_car')


def _seconds(value):
    hours, minutes, seconds = (int(part) for part in str(value).split(':'))
    return hours * 3600 + minutes * 60 + seconds


def test_ladowanie_czeka_na_ustalenie_sie_stanu(ha_config):
    """O pelnej godzinie cena, okno i licznik zmieniaja sie w tej samej sekundzie.
    `restart` + `delay` zlewa to w jedna decyzje podjeta po ustaniu zdarzen.
    Model `tests/race_model.py` pokazuje, co daje brak tego opoznienia."""
    car = _car(ha_config)
    assert car['mode'] == 'restart'
    assert 'delay' in car['actions'][0]
    assert _seconds(car['actions'][0]['delay']) >= 5


def test_warunek_danych_jest_przed_wyborem_akcji(ha_config):
    actions = _car(ha_config)['actions']
    kinds = [next(iter(action)) for action in actions]
    assert kinds.index('delay') < kinds.index('condition') < kinds.index('choose')


def test_straznik_wylacza_po_dluzszym_braku_cen(ha_config):
    watchdog = next(a for a in ha_config.automation
                    if a['id'] == 'tge_v2_charging_watchdog')
    trigger = watchdog['triggers'][0]
    assert trigger['entity_id'] == P
    assert trigger['to'] == 'unavailable'
    assert 3600 <= _seconds(trigger['for']) <= 4 * 3600
    turn_off = [a for a in watchdog['actions'] if a.get('action') == 'switch.turn_off']
    assert turn_off, 'straznik musi wylaczac przelacznik'


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def test_szablony_z_automatyzacji_renderuja_sie(ha_config, payload):
    """Literowka w wiadomosci do Dziennika wyszlaby dopiero w HA, w trakcie pracy."""
    moment = DAY.replace(hour=10)
    states = build_states(payload, payload, charged=0, switch_on=True)
    ha_config.render_entities(states, moment)
    env = build_env(states, moment)
    rendered = 0
    for automation in ha_config.automation:
        for text in _strings(automation):
            if '{{' in text or '{%' in text:
                env.from_string(text).render(trigger={'id': 'godzina'})
                rendered += 1
    # warunek danych, 2 warunki wyboru akcji, 2 wiadomosci, 2 szablony licznika
    assert rendered == 7


def test_wiadomosc_do_dziennika_podaje_powod(ha_config, payload):
    moment = DAY.replace(hour=10)
    states = build_states(payload, payload, charged=0, switch_on=False)
    ha_config.render_entities(states, moment)
    env = build_env(states, moment)
    car = _car(ha_config)
    choose = next(action for action in car['actions'] if 'choose' in action)
    logs = [step for branch in choose['choose'] for step in branch['sequence']
            if step.get('action') == 'logbook.log']
    assert len(logs) == 2
    for step in logs:
        message = env.from_string(step['data']['message']).render(trigger={'id': 'godzina'})
        assert 'okno' in message and 'cena' in message and 'godzina' in message


def test_wyzwalacze_maja_id(ha_config):
    for trigger in _car(ha_config)['triggers']:
        assert trigger.get('id'), trigger


def test_progi_w_ha_sa_zgodne_z_taryfa_w_pythonie(ha_config):
    """Python liczy plan, HA odtwarza go wedlug progow z `sensor.tge_v2_reguly`.
    Rozjazd daje ladowanie wg innych progow, niz zalozyl plan - bez zadnego bledu."""
    import ast

    from jinja2 import Environment

    reguly = next(entity for block in ha_config.configuration['template']
                  for entity in block.get('sensor', [])
                  if entity['name'] == 'TGE v2 Reguly')
    in_ha = {key: ast.literal_eval(Environment().from_string(value).render().strip())
             for key, value in reguly['attributes'].items()}
    tariff = Tariff()
    assert in_ha == {
        'charging_hours': tariff.charging_hours,
        'charge_below': tariff.charge_below,
        'stop_above': tariff.stop_above,
        'max_charge_price': tariff.max_charge_price,
        'window_margin': tariff.window_margin,
        'day_margin': tariff.day_margin,
        'window_hours': list(tariff.window_hours),
    }


def test_wejscie_nie_jest_modyfikowane_przez_testy(payload):
    """Zabezpieczenie fixture session-scoped: _yesterday() pracuje na kopii."""
    before = copy.deepcopy(payload)
    _yesterday(payload)
    assert payload == before
