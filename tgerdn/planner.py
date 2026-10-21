"""Plan ladowania - okno najtanszych godzin.

Plan liczymy raz na dobe w Pythonie (nie w szablonach HA), dzieki czemu:
  - okno jest stabilne przez cala dobe (przelacznik nie skacze),
  - reguly sa policzone dokladnie raz i da sie je przetestowac,
  - Home Assistant dostaje gotowe liczby zamiast robic sortowanie w Jinja.

Cena ma dwie skladowe: kurs Fixing I (spot) i margines dostawy (taryfa
okienkowa nocą, dzienna w dzień). Okno wybieramy po cenie razem z marginesem,
bo to ona odzwierciedla realny koszt ladowania.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import Tariff
from .model import DayPrices, HourPrice, Plan
from .tge import RawFixing

MWH_TO_KWH = 1000.0


def build_day_prices(
    day: str,
    fixings: list[RawFixing],
    tariff: Tariff,
    *,
    fetched_at: str,
    source_url: str,
) -> DayPrices:
    """Zamienia surowe wiersze TGE na dobe cen z marginesami.

    Args:
        day: data dostawy w formacie YYYY-MM-DD.
        fixings: wiersze Fixing I (mogą obejmowac kilka dób).
        tariff: taryfa (marginesy).
        fetched_at: znacznik czasu pobrania.
        source_url: adres strony zrodlowej.

    Returns:
        `DayPrices` z 24 godzinami (albo mniej, jesli brakuje danych).
    """
    by_hour = {fixing.hour: fixing for fixing in fixings if fixing.day == day}

    hours: list[HourPrice] = []
    for hour in range(1, 25):
        fixing = by_hour.get(hour)
        if fixing is None:
            continue
        spot = round(fixing.price_pln_mwh / MWH_TO_KWH, 6)
        hours.append(
            HourPrice(hour=hour, spot=spot, margin=tariff.margin(hour - 1))
        )

    return DayPrices(
        day=day,
        hours=tuple(hours),
        fetched_at=fetched_at,
        source_url=source_url,
    )


def build_plan(day_prices: DayPrices, tariff: Tariff) -> Plan:
    """Liczy plan ladowania na podstawie cen doby.

    Okno to N najtanszych godzin CALEGO dnia (po cenie z marginesem).
    Dzieki temu jest stabilne przez dobe i daje dokladnie N godzin.
    """
    if not day_prices.hours:
        raise ValueError('Brak cen - nie da sie policzyc planu')

    ranked = sorted(day_prices.hours, key=lambda h: (h.total, h.hour))
    count = min(tariff.charging_hours, len(ranked))

    window = ranked[:count]
    dearest = sorted(day_prices.hours, key=lambda h: (-h.total, h.hour))[:count]

    return Plan(
        hours=tuple(sorted(h.hour for h in window)),
        cost_avg=round(sum(h.total for h in window) / count, 6),
        cost_worst=round(sum(h.total for h in dearest) / count, 6),
        cheapest_hour=ranked[0].hour,
        cheapest_price=ranked[0].total,
        dearest_hour=dearest[0].hour,
        dearest_price=dearest[0].total,
        day_avg=round(sum(h.total for h in day_prices.hours) / len(day_prices.hours), 6),
    )


def merge_plan(previous: dict | None, plan: Plan) -> Plan:
    """Zachowuje plan z poprzedniego zapisu, jesli dotyczy tego samego dnia.

    Plan ma byc stabilny przez dobe. Jesli TGE kiedys skoryguje kurs,
    plan przeliczony od nowa mógłby przesunac okno i spowodowac
    "skakanie" przelacznika - dlatego trzymamy plan z pierwszego zapisu.
    """
    if not previous:
        return plan

    hours = previous.get('hours')
    if not isinstance(hours, list) or not hours:
        return plan

    try:
        frozen = tuple(sorted(int(hour) for hour in hours))
    except (TypeError, ValueError):
        return plan

    return Plan(
        hours=frozen,
        cost_avg=plan.cost_avg,
        cost_worst=plan.cost_worst,
        cheapest_hour=plan.cheapest_hour,
        cheapest_price=plan.cheapest_price,
        dearest_hour=plan.dearest_hour,
        dearest_price=plan.dearest_price,
        day_avg=plan.day_avg,
    )


def delivery_days(today: date, count: int = 2) -> list[date]:
    """Doby dostawy, ktore nas interesuja: dzis i kolejne dni."""
    return [today + timedelta(days=offset) for offset in range(count)]


def now_iso() -> str:
    """Znacznik czasu w formacie ISO (lokalna strefa czasowa)."""
    return datetime.now().astimezone().isoformat(timespec='seconds')
