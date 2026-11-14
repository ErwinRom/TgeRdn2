"""Testy trybu `serve` (uzywany w dodatku HA)."""

import json
from datetime import datetime, time, timedelta

from tgerdn.cli import (RETRY_DELAYS, _missing_labels, _next_run, _parse_run_times,
                        _retry_time)


def test_parsowanie_godzin():
    times = _parse_run_times('00:01,12:01')
    assert times == [time(0, 1), time(12, 1)]


def test_parsowanie_godzin_ze_spacjami():
    assert _parse_run_times(' 06:30 , 18:30 ') == [time(6, 30), time(18, 30)]


def test_nieprawidlowa_godzina_uzywa_domyslnych():
    assert _parse_run_times('nonsense') == [time(0, 1), time(12, 1)]


def test_pusta_godzina_uzywa_domyslnych():
    assert _parse_run_times('') == [time(0, 1), time(12, 1)]


def test_nastepne_pobieranie_dzisiaj():
    now = datetime(2026, 10, 21, 6, 0, 0)
    assert _next_run(now, [time(0, 1), time(12, 1)]) == datetime(2026, 10, 21, 12, 1)


def test_nastepne_pobieranie_jutro():
    now = datetime(2026, 10, 21, 13, 0, 0)
    assert _next_run(now, [time(0, 1), time(12, 1)]) == datetime(2026, 10, 22, 0, 1)


def test_dokladnie_w_godzinie_pobierania_idzie_dzisiaj():
    """Godzina 00:01 juz minela -> nastepne pobieranie jest nastepnego dnia."""
    now = datetime(2026, 10, 21, 0, 1, 0)
    assert _next_run(now, [time(0, 1)]) == datetime(2026, 10, 22, 0, 1)


def test_przed_godzina_pobierania_idzie_dzisiaj():
    now = datetime(2026, 10, 21, 0, 0, 30)
    assert _next_run(now, [time(0, 1)]) == datetime(2026, 10, 21, 0, 1)


# ----------------------------------------------------- ponawianie po porazce

def _write(tmp_path, name, day, fetched=True):
    (tmp_path / name).write_text(json.dumps({'day': day, 'data_fetched': fetched}),
                                 encoding='utf-8')


def test_brak_plikow_to_brak_danych_na_dzis(tmp_path):
    now = datetime(2026, 10, 21, 0, 2)
    assert _missing_labels(tmp_path, now) == ['today']


def test_wczorajszy_plik_nie_liczy_sie_jako_dzisiejszy(tmp_path):
    """Pobranie o 00:01 sie nie udalo - today.json jest jeszcze z wczoraj."""
    _write(tmp_path, 'today.json', '2026-10-20')
    assert _missing_labels(tmp_path, datetime(2026, 10, 21, 0, 2)) == ['today']


def test_pusty_plik_nie_liczy_sie_jako_dane(tmp_path):
    _write(tmp_path, 'today.json', '2026-10-21', fetched=False)
    assert _missing_labels(tmp_path, datetime(2026, 10, 21, 3, 0)) == ['today']


def test_rano_jutro_nie_jest_jeszcze_oczekiwane(tmp_path):
    """TGE publikuje Fixing I od 10:30 - wczesniej brak jutra to norma."""
    _write(tmp_path, 'today.json', '2026-10-21')
    assert _missing_labels(tmp_path, datetime(2026, 10, 21, 9, 0)) == []


def test_po_publikacji_brak_jutra_to_awaria(tmp_path):
    _write(tmp_path, 'today.json', '2026-10-21')
    assert _missing_labels(tmp_path, datetime(2026, 10, 21, 12, 5)) == ['tomorrow']
    _write(tmp_path, 'tomorrow.json', '2026-10-22')
    assert _missing_labels(tmp_path, datetime(2026, 10, 21, 12, 5)) == []


def test_ponawianie_zwieksza_odstepy_i_ma_limit():
    now = datetime(2026, 10, 21, 0, 2)
    scheduled = datetime(2026, 10, 21, 12, 1)
    gaps = [(_retry_time(now, scheduled, attempt) - now).total_seconds()
            for attempt in range(len(RETRY_DELAYS) + 3)]
    assert gaps[:len(RETRY_DELAYS)] == list(RETRY_DELAYS)
    assert set(gaps[len(RETRY_DELAYS):]) == {RETRY_DELAYS[-1]}


def test_ponawianie_ustepuje_planowemu_pobraniu():
    scheduled = datetime(2026, 10, 21, 12, 1)
    now = scheduled - timedelta(seconds=30)
    assert _retry_time(now, scheduled, 0) is None
