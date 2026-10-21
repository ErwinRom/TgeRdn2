"""Testy parsowania tabeli Fixing I."""

import pytest

from tgerdn.tge import parse_fixings, page_date_for, url_for

from datetime import date


def test_parsuje_wszystkie_24_godziny(fixings):
    assert len(fixings) == 24
    assert sorted(f.hour for f in fixings) == list(range(1, 25))


def test_rozpoznaje_date_dostawy(fixings):
    assert {f.day for f in fixings} == {'2026-10-21'}


def test_kurs_pierwszej_godziny(fixings):
    first = next(f for f in fixings if f.hour == 1)
    assert first.price_pln_mwh == pytest.approx(601.77)


def test_nie_bierze_kolumny_typ_instrumentu(fixings):
    # Kolumna "Typ instrumentu" zawiera wartosci typu 60 (wolumen).
    # Parser nie moze wziac jej za kurs.
    for fixing in fixings:
        assert fixing.price_pln_mwh > 60


def test_pusta_strona_daje_pusta_liste():
    assert parse_fixings('<html><body><p>brak danych</p></body></html>') == []


def test_strona_bez_kursu_daje_pusta_liste():
    html = """
    <table><tr><th>Data dostawy</th><th>Kurs [PLN/MWh]</th></tr>
    <tr><td>2026-10-21_H01</td><td>-</td></tr></table>
    """
    assert parse_fixings(html) == []


def test_akceptuje_kropke_dziesietna():
    html = """
    <table>
    <tr><th>Data dostawy</th><th>Typ instrumentu</th>
        <!-- Fixing I start --><th>Kurs [PLN/MWh]</th><!-- Fixing I end --></tr>
    <tr><td>2026-10-21_H01</td><td>60</td>
        <!-- Fixing I start --><td>500.25</td><!-- Fixing I end --></tr>
    </table>
    """
    fixings = parse_fixings(html)
    assert len(fixings) == 1
    assert fixings[0].price_pln_mwh == pytest.approx(500.25)


def test_pomija_wiersze_bez_godziny():
    html = """
    <table>
    <tr><td>Razem</td><td>100</td>
        <!-- Fixing I start --><td>500</td><!-- Fixing I end --></tr>
    </table>
    """
    assert parse_fixings(html) == []


def test_data_dostawy_zmienia_sie_o_dzien():
    assert page_date_for(date(2026, 10, 21)) == date(2026, 10, 20)


def test_adres_strony_uzywa_dnia_poprzedzajacego():
    url = url_for('https://tge.pl/energia-elektryczna-rdn', date(2026, 10, 21))
    assert 'dateShow=20-10-2026' in url
    assert 'type=1' in url
