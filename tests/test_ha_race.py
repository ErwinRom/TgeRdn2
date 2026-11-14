"""Wyscig o pelnej godzinie: cena, okno i licznik zmieniaja sie w tej samej
sekundzie, a druga automatyzacja czyta stan przelacznika.

Bez opoznienia wynik zalezy od kolejnosci zdarzen: licznik zalicza godzine,
ktorej nie bylo, albo gubi te, ktora byla (zgubiona godzina dokleja potem
drogie godziny "odbudowy"), a przelacznik potrafi mrugnac. Test uruchamia
model z `race_model.py` na prawdziwych szablonach i sprawdza, ze automatyzacja,
ktora jest w repo, tych bledow nie ma.
"""

import pytest

pytest.importorskip('yaml')
pytest.importorskip('jinja2')

from race_model import simulate, uses_debounce  # noqa: E402

DAYS = 12
SEED = 20261112


@pytest.fixture(scope='module')
def car(ha_config):
    return next(a for a in ha_config.automation if a['id'] == 'tge_v2_charging_car')


def test_automatyzacja_czeka_na_ustalenie_sie_stanu(car):
    assert uses_debounce(car), (
        'tge_v2_charging_car musi miec `mode: restart` i `delay` jako pierwsza akcje'
    )


def test_z_opoznieniem_wynik_nie_zalezy_od_kolejnosci_zdarzen(ha_config, car):
    result = simulate(ha_config, DAYS, SEED, debounce=uses_debounce(car))
    assert result['boundaries'] == DAYS * 23
    assert result['extra_toggles'] == 0, result
    assert result['bad_credit'] == 0, result


def test_model_wykrywa_blad_bez_opoznienia(ha_config):
    """Test z zebami: ten sam model bez opoznienia musi znalezc bledy,
    inaczej powyzszy test niczego nie sprawdza."""
    result = simulate(ha_config, DAYS, SEED, debounce=False)
    assert result['bad_credit'] > 0, result
