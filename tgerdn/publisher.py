"""Buduje pliki JSON dla Home Assistant i zapisuje je atomowo.

Kontrakt pliku (v2) - jedno zrodlo prawdy dla wszystkich sensorow:

    version, day, delivery_date, fetched_at, last_update, ok, data_fetched,
    data_points, unit, icon, friendly_name, source, tariff,
    fixing_i_prices  - 24 godziny (klucze z v1 + margines i cena razem),
    prices           - ten sam zbior w formacie do wykresow,
    plan             - okno najtanszych godzin i oszczednosc,
    stats            - minima, maxima, srednie.

Zapis jest atomowy (plik tymczasowy + `os.replace`), wiec Home Assistant
nigdy nie przeczyta polowy pliku.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from .config import Tariff
from .model import DayPrices, Plan

logger = logging.getLogger(__name__)

VERSION = 2
UNIT = 'PLN/kWh'
ICON = 'mdi:cash'
FRIENDLY_NAME = {
    'today': 'TGE RDN - Ceny dzis',
    'tomorrow': 'TGE RDN - Ceny jutro',
}


def build_payload(
    day_prices: DayPrices,
    plan: Plan | None,
    tariff: Tariff,
    *,
    label: str = 'today',
) -> dict[str, Any]:
    """Buduje pelna strukture JSON dla jednej doby."""
    hours = [hour.to_dict(day_prices.day) for hour in day_prices.hours]

    prices = [
        {
            'dtime': f"{day_prices.day}T{hour.hour - 1:02d}:00:00",
            'period': hour.period,
            'rce_pln': hour.spot,
            'total_pln': hour.total,
            'business_date': day_prices.day,
        }
        for hour in day_prices.hours
    ]

    totals = [hour.total for hour in day_prices.hours]
    stats = {
        'count': len(totals),
        'min': min(totals) if totals else None,
        'max': max(totals) if totals else None,
        'avg': plan.day_avg if plan else None,
    }

    return {
        'version': VERSION,
        'day': day_prices.day,
        'delivery_date': day_prices.day,
        'fetched_at': day_prices.fetched_at,
        'last_update': day_prices.fetched_at,
        'ok': bool(day_prices.hours),
        'data_fetched': bool(day_prices.hours),
        'data_points': len(day_prices.hours),
        'unit': UNIT,
        'icon': ICON,
        'friendly_name': FRIENDLY_NAME.get(label, FRIENDLY_NAME['today']),
        'source': day_prices.source_url,
        'tariff': tariff.to_dict(),
        'fixing_i_prices': hours,
        'prices': prices,
        'plan': plan.to_dict() if plan else None,
        'stats': stats,
    }


def empty_payload(day: str, tariff: Tariff, *, label: str, source: str = '') -> dict[str, Any]:
    """Payload dla doby, ktorej TGE jeszcze nie opublikowal (lub ktora wygasla)."""
    return {
        'version': VERSION,
        'day': day,
        'delivery_date': day,
        'fetched_at': None,
        'last_update': None,
        'ok': False,
        'data_fetched': False,
        'data_points': 0,
        'unit': UNIT,
        'icon': ICON,
        'friendly_name': FRIENDLY_NAME.get(label, FRIENDLY_NAME['today']),
        'source': source,
        'tariff': tariff.to_dict(),
        'fixing_i_prices': [],
        'prices': [],
        'plan': None,
        'stats': {'count': 0, 'min': None, 'max': None, 'avg': None},
    }


def read_payload(path: Path) -> dict[str, Any] | None:
    """Wczytuje poprzedni payload (albo None, gdy pliku nie ma / jest uszkodzony)."""
    try:
        with open(path, encoding='utf-8') as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as error:
        logger.warning('Nie udalo sie wczytac %s: %s', path, error)
        return None
    return data if isinstance(data, dict) else None


def write_payload(path: Path, payload: dict[str, Any]) -> bool:
    """Zapisuje payload atomowo. Zwraca True, gdy zapis sie powiodl."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=path.parent,
            prefix=f'.{path.name}.',
            suffix='.tmp',
            delete=False,
        )
        try:
            with handle:
                json.dump(payload, handle, indent=2, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            # tempfile tworzy plik 0600 - plik z danymi ma byc czytelny
            # takze dla innego uzytkownika (np. procesu HA).
            os.chmod(handle.name, 0o644)
            os.replace(handle.name, path)
        except BaseException:
            Path(handle.name).unlink(missing_ok=True)
            raise
    except OSError as error:
        logger.error('Nie udalo sie zapisac %s: %s', path, error)
        return False

    logger.info('Zapisano %s (%s godzin)', path, payload.get('data_points', 0))
    return True
