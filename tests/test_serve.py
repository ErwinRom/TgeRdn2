"""Testy trybu `serve` (uzywany w dodatku HA)."""

from datetime import datetime, time

from tgerdn.cli import _next_run, _parse_run_times


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
