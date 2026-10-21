"""Wspolne fixture dla testow."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FIXTURE = REPO / 'tests' / 'fixtures' / 'tge_fixing_i_page.html'


@pytest.fixture(scope='session')
def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture(scope='session')
def fixings(fixture_bytes):
    from tgerdn.tge import parse_fixings

    return parse_fixings(fixture_bytes)


@pytest.fixture(scope='session')
def tariff():
    from tgerdn.config import Tariff

    return Tariff()


@pytest.fixture(scope='session')
def day_prices(fixings, tariff):
    from tgerdn.planner import build_day_prices

    day = fixings[0].day
    return build_day_prices(
        day,
        fixings,
        tariff,
        fetched_at='2026-10-21T00:01:00+02:00',
        source_url='fixture://tge',
    )


@pytest.fixture(scope='session')
def plan(day_prices, tariff):
    from tgerdn.planner import build_plan

    return build_plan(day_prices, tariff)


@pytest.fixture(scope='session')
def payload(day_prices, plan, tariff):
    from tgerdn.publisher import build_payload

    return build_payload(day_prices, plan, tariff, label='today')


@pytest.fixture(scope='session')
def ha_config():
    from tgerdn.simulate import HomeAssistantConfig

    return HomeAssistantConfig()
