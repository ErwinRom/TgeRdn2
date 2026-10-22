"""Konfiguracja: taryfa, progi sterowania i katalog wyjsciowy.

Wszystko da sie nadpisac zmiennymi srodowiskowymi, dzieki czemu ten sam
kod dziala w terminalu, w kontenerze i w harmonogramie systemd.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

# Domyslny katalog trwaly - /tmp jest czyszczony przy restarcie systemu,
# a pliki musza przetrwac restart, bo Home Assistant czyta je w petli.
DEFAULT_OUTPUT_DIR = Path.home() / '.local' / 'share' / 'tgerdn'

# Godziny dobowe, w ktorych obowiazuje taryfa okienkowa (tansza dostawa).
DEFAULT_WINDOW_HOURS = (0, 1, 2, 3, 4, 5, 13, 14, 22, 23)


@dataclass(frozen=True)
class Tariff:
    """Taryfa i progi sterowania ladowaniem.

    Attributes:
        window_margin: margines dostawy w godzinach okienkowych (PLN/kWh).
        day_margin: margines dostawy w godzinach dziennych (PLN/kWh).
        window_hours: godziny zegara (0..23) z taryfa okienkowa.
        charging_hours: ile godzin dziennie ladujemy w najtanszym oknie.
        charge_below: wlac ladowanie, gdy cena spadnie ponizej progu.
        stop_above: wylacz ladowanie, gdy cena wzrośnie powyżej progu.
        max_charge_price: twardy limit ceny (0 = wylaczony).
    """

    window_margin: float = 0.0993
    day_margin: float = 0.3276
    window_hours: tuple[int, ...] = DEFAULT_WINDOW_HOURS
    charging_hours: int = 5
    charge_below: float = 0.4
    stop_above: float = 0.5
    max_charge_price: float = 0.0

    def margin(self, clock_hour: int) -> float:
        """Margines dostawy dla godziny zegara (0..23)."""
        return self.window_margin if clock_hour in self.window_hours else self.day_margin

    def to_dict(self) -> dict[str, object]:
        return {
            'window_margin': self.window_margin,
            'day_margin': self.day_margin,
            'window_hours': list(self.window_hours),
            'charging_hours': self.charging_hours,
            'charge_below': self.charge_below,
            'stop_above': self.stop_above,
            'max_charge_price': self.max_charge_price,
        }

    def with_overrides(self, **kwargs: object) -> 'Tariff':
        """Kopia taryfy ze zmienionymi polami (pomija None)."""
        clean = {k: v for k, v in kwargs.items() if v is not None}
        if 'window_hours' in clean:
            clean['window_hours'] = tuple(clean['window_hours'])  # type: ignore[arg-type]
        return replace(self, **clean)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> 'Tariff':
        """Tariff z domyslnych wartosci, nadpisanych zmiennymi srodowiskowymi."""
        env = os.environ if env is None else env
        tariff = cls()
        return tariff.with_overrides(
            window_margin=_float(env.get('TGERDN_WINDOW_MARGIN')),
            day_margin=_float(env.get('TGERDN_DAY_MARGIN')),
            charging_hours=_int(env.get('TGERDN_CHARGING_HOURS')),
            charge_below=_float(env.get('TGERDN_CHARGE_BELOW')),
            stop_above=_float(env.get('TGERDN_STOP_ABOVE')),
            max_charge_price=_float(env.get('TGERDN_MAX_CHARGE_PRICE')),
            window_hours=_hours(env.get('TGERDN_WINDOW_HOURS')),
        )


@dataclass(frozen=True)
class Settings:
    """Ustawienia uruchomienia."""

    output_dir: Path = DEFAULT_OUTPUT_DIR
    tariff: Tariff = Tariff()
    timeout: float = 30.0
    retries: int = 3
    base_url: str = 'https://tge.pl/energia-elektryczna-rdn'

    def with_overrides(self, **kwargs: object) -> 'Settings':
        clean = {k: v for k, v in kwargs.items() if v is not None}
        if 'output_dir' in clean:
            clean['output_dir'] = Path(str(clean['output_dir'])).expanduser()
        return replace(self, **clean)  # type: ignore[arg-type]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> 'Settings':
        env = os.environ if env is None else env
        out = env.get('TGERDN_OUTPUT_DIR')
        return cls(
            output_dir=Path(out).expanduser() if out else DEFAULT_OUTPUT_DIR,
            tariff=Tariff.from_env(env),
            timeout=_float(env.get('TGERDN_TIMEOUT')) or 30.0,
            retries=_int(env.get('TGERDN_RETRIES')) or 3,
            base_url=env.get('TGERDN_BASE_URL') or cls.base_url,
        )


def _float(value: str | None) -> float | None:
    if value is None or value.strip() == '':
        return None
    try:
        return float(value.replace(',', '.'))
    except ValueError:
        return None


def _int(value: str | None) -> int | None:
    if value is None or value.strip() == '':
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _hours(value: str | None) -> tuple[int, ...] | None:
    if value is None or value.strip() == '':
        return None
    try:
        return tuple(int(part) for part in value.replace(';', ',').split(',') if part.strip())
    except ValueError:
        return None
