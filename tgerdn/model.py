"""Modele danych - pojedyncza godzina, doba cen i plan ladowania.

Konwencja godzin: TGE publikuje dobe handlowa jako H01..H24, gdzie
H01 oznacza przedzial 00:00-01:00, a H24 przedzial 23:00-24:00.
W calym projekcie trzymamy sie tej konwencji (`hour` 1..24), a godzine
zegara (0..23) wyliczamy przez `clock_hour`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# TGE publikuje kursy w PLN/MWh, my podajemy cene w PLN/kWh.
MWH_TO_KWH = 1000.0


@dataclass(frozen=True)
class HourPrice:
    """Cena jednej godziny doby handlowej.

    Attributes:
        hour: godzina TGE 1..24 (H01 = 00:00-01:00).
        spot: kurs Fixing I w PLN/kWh.
        margin: margines dostawy w PLN/kWh (taryfa okienkowa lub dzienna).
    """

    hour: int
    spot: float
    margin: float

    @property
    def clock_hour(self) -> int:
        """Godzina zegara 0..23 (H01 = 00:00)."""
        return self.hour - 1

    @property
    def total(self) -> float:
        """Cena z marginesem dostawy - to cos faktycznie placimy."""
        return round(self.spot + self.margin, 6)

    @property
    def period(self) -> str:
        """Przedzial godzinowy, np. '00:00-01:00'."""
        return f'{self.clock_hour:02d}:00-{self.hour:02d}:00'

    @property
    def dtime(self) -> str:
        """Poczatek przedzialu w formacie HH:MM:SS."""
        return f'{self.clock_hour:02d}:00:00'

    def to_dict(self, day: str) -> dict[str, Any]:
        """Wersja JSON - zachowuje klucze z v1, zeby stare szablony dzialaly."""
        return {
            'data_dostawy': day,
            'hour': self.hour,
            'fixing_i_price_pln_kwh': self.spot,
            'margin': self.margin,
            'total': self.total,
            'period': self.period,
            'dtime': f'{day}T{self.clock_hour:02d}:00:00',
        }


@dataclass(frozen=True)
class DayPrices:
    """Ceny jednej doby dostawy."""

    day: str
    hours: tuple[HourPrice, ...]
    fetched_at: str
    source_url: str

    def by_hour(self) -> dict[int, HourPrice]:
        return {h.hour: h for h in self.hours}


@dataclass(frozen=True)
class Plan:
    """Plan ladowania na jedna dobe.

    `hours` to godziny TGE (1..24) wybrane jako najtansze. Plan jest liczony
    raz na dobe i nie zmienia sie w ciagu dnia - dzieki temu przelacznik
    nie skacze miedzy godzinami.
    """

    hours: tuple[int, ...]
    cost_avg: float
    cost_worst: float
    cheapest_hour: int
    cheapest_price: float
    dearest_hour: int
    dearest_price: float
    day_avg: float

    @property
    def saving(self) -> float:
        """Oszczednosc na kWh przy ladowaniu w oknie zamiast w najdrozszych godzinach."""
        return round(self.cost_worst - self.cost_avg, 6)

    @staticmethod
    def period_for(hour: int) -> str:
        """Przedzial godzinowy dla godziny TGE, np. 3 -> '02:00-03:00'."""
        return f'{hour - 1:02d}:00-{hour:02d}:00'

    def to_dict(self) -> dict[str, Any]:
        return {
            'hours': list(self.hours),
            'periods': [self.period_for(hour) for hour in self.hours],
            'count': len(self.hours),
            'cost_avg': self.cost_avg,
            'cost_worst': self.cost_worst,
            'saving': self.saving,
            'cheapest_hour': self.cheapest_hour,
            'cheapest_price': self.cheapest_price,
            'dearest_hour': self.dearest_hour,
            'dearest_price': self.dearest_price,
            'day_avg': self.day_avg,
        }
