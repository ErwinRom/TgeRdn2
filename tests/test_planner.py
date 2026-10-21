"""Testy planu ladowania - okno najtanszych godzin."""

import pytest

from tgerdn.model import DayPrices
from tgerdn.planner import build_plan, merge_plan


def test_plan_ma_pietsc_godzin(tariff, plan):
    assert len(plan.hours) == tariff.charging_hours == 5


def test_plan_to_najtansze_godziny_po_cenie_z_marginesem(day_prices, plan):
    ranked = sorted(day_prices.hours, key=lambda h: (h.total, h.hour))
    assert set(plan.hours) == {h.hour for h in ranked[:5]}


def test_plan_posortowany(day_prices, plan):
    assert list(plan.hours) == sorted(plan.hours)


def test_margines_okienkowy_w_nocy(day_prices, tariff):
    noc = next(h for h in day_prices.hours if h.hour == 1)
    assert noc.margin == tariff.window_margin

    dzien = next(h for h in day_prices.hours if h.hour == 12)
    assert dzien.margin == tariff.day_margin


def test_cena_laczna_to_kurs_plus_margines(day_prices):
    for hour in day_prices.hours:
        assert hour.total == pytest.approx(hour.spot + hour.margin)


def test_srednia_okna_jest_nizsza_od_sredniej_doby(plan):
    assert plan.cost_avg <= plan.day_avg
    assert plan.cost_avg < plan.cost_worst
    assert plan.saving == pytest.approx(plan.cost_worst - plan.cost_avg)


def test_plan_bez_danych_raises(tariff):
    empty = DayPrices(day='2026-10-21', hours=(), fetched_at='x', source_url='y')
    with pytest.raises(ValueError):
        build_plan(empty, tariff)


def test_merge_plan_zachowuje_poprzedni_plan(plan):
    frozen = merge_plan({'hours': [3, 4, 5, 6, 7]}, plan)
    assert frozen.hours == (3, 4, 5, 6, 7)


def test_merge_plan_bez_poprzedniego_zwraca_plan(plan):
    assert merge_plan(None, plan) is plan
    assert merge_plan({}, plan) is plan


def test_merge_plan_odrzuca_uzyte_dane(plan):
    assert merge_plan({'hours': 'nonsense'}, plan) is plan
