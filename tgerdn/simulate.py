"""Symulacja doby ladowania na PRAWDZIWYCH szablonach z `homeassistant/`.

Nie jest to kopia logiki - renderuje pliki konfiguracyjne, ktore wjedzie do
Home Assistant, wiec sprawdza dokladnie to, co zostanie zainstalowane.

Wymaga `jinja2` i `pyyaml` (tylko do developmentu - sam scraper ich nie uzywa).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
FIXTURE = REPO_ROOT / 'tests' / 'fixtures' / 'tge_fixing_i_page.html'
SWITCH = 'switch.0xb40ecfd05e500000'
CONFIG_FILE = 'tgerdn_v2.yaml'
AUTOMATION_FILE = 'tgerdn_v2_automation.yaml'
HOURS_IN_DAY = 24


def find_ha_dir(explicit: Path | None = None) -> Path | None:
    """Szuka katalogu z konfiguracja HA (pliki `tgerdn_v2.yaml` itd.).

    Kolejnosc:
      1. argument explicite,
      2. zmienna srodowiskowa TGERDN_HA_DIR,
      3. katalog wewnatrz pakietu (`tgerdn/homeassistant`),
      4. katalog obok pakietu (repozytorium),
      5. katalog w bieżącym katalogu roboczym.
    """
    candidates = [
        explicit,
        Path(os.environ['TGERDN_HA_DIR']) if os.environ.get('TGERDN_HA_DIR') else None,
        PACKAGE_DIR / 'homeassistant',
        REPO_ROOT / 'homeassistant',
        Path.cwd() / 'homeassistant',
    ]
    for candidate in candidates:
        if candidate and (candidate / CONFIG_FILE).is_file():
            return candidate
    return None


# --------------------------------------------------------------- harness Jinja

def _require() -> tuple[Any, Any, Any]:
    """Importuje jinja2/yaml z czytelnym komunikatem, gdy ich nie ma."""
    try:
        import yaml
        from jinja2 import Environment, StrictUndefined
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            'Symulacja wymaga jinja2 i pyyaml: pip install jinja2 pyyaml'
        ) from error
    return yaml, Environment, StrictUndefined


class FakeClock:
    """Udaje `now()` z Home Assistant."""

    def __init__(self, moment: datetime):
        self._moment = moment

    @property
    def hour(self) -> int:
        return self._moment.hour

    def __call__(self) -> 'FakeClock':
        return self

    def __add__(self, delta: timedelta) -> 'FakeClock':
        return FakeClock(self._moment + delta)

    def __str__(self) -> str:
        return self._moment.isoformat()

    def timestamp(self) -> float:
        return self._moment.timestamp()


class FakeStates:
    """Obiekt `states` jak w HA - dziala jako states('id') i states['id']."""

    def __init__(self, states: dict[str, dict]):
        self._states = states

    def __call__(self, entity_id: str) -> str:
        return (self._states.get(entity_id) or {}).get('state', 'unavailable')

    def __getitem__(self, entity_id: str) -> dict:
        return self._states.get(entity_id) or {}


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except ValueError:
            return False
    return False


def _as_timestamp(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return value.timestamp()


def _timestamp_custom(value: Any, fmt: str, local: bool = False) -> str:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime(fmt)
    return value.strftime(fmt)


def build_env(states: dict[str, dict], moment: datetime):
    """Buduje srodowisko Jinja podobne do HA."""
    _, Environment, StrictUndefined = _require()

    env = Environment(undefined=StrictUndefined)
    env.filters['is_number'] = _is_number
    env.filters['to_json'] = json.dumps
    env.filters['from_json'] = json.loads
    env.filters['as_timestamp'] = _as_timestamp
    env.filters['timestamp_custom'] = _timestamp_custom

    def state_attr(entity_id: str, attribute: str) -> Any:
        entity = states.get(entity_id) or {}
        return (entity.get('attributes') or {}).get(attribute)

    def is_state(entity_id: str, value: Any) -> bool:
        entity = states.get(entity_id) or {}
        return entity.get('state') == value

    env.globals['state_attr'] = state_attr
    env.globals['states'] = FakeStates(states)
    env.globals['is_state'] = is_state
    env.globals['is_number'] = _is_number
    env.globals['now'] = FakeClock(moment)
    env.globals['as_timestamp'] = _as_timestamp
    env.globals['timestamp_custom'] = _timestamp_custom
    env.globals['timedelta'] = timedelta
    return env


def slugify(text: str) -> str:
    """Zamienia nazwe encji na entity_id tak jak robi to Home Assistant."""
    import unicodedata

    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(c for c in normalized if not unicodedata.combining(c))
    return ascii_text.lower().replace(' ', '_').replace('-', '_').replace('.', '')


# --------------------------------------------------------------- konfiguracja HA

class HomeAssistantConfig:
    """Wczytuje szablony z `homeassistant/` i renderuje je jak HA."""

    def __init__(self, ha_dir: Path | None = None):
        self.ha_dir = ha_dir or find_ha_dir()
        if not self.ha_dir or not self.ha_dir.is_dir():
            raise RuntimeError(
                'Nie znaleziono katalogu z konfiguracja HA. '
                'Ustaw TGERDN_HA_DIR albo uruchom z katalogu projektu.'
            )

        yaml, _, _ = _require()
        self._yaml = yaml
        self.configuration = yaml.safe_load(
            (self.ha_dir / CONFIG_FILE).read_text(encoding='utf-8')
        )
        self.automation = yaml.safe_load(
            (self.ha_dir / AUTOMATION_FILE).read_text(encoding='utf-8')
        )

        action = self.automation[0]['actions'][0]
        self.turn_on_template = action['choose'][0]['conditions'][0]['value_template']
        self.turn_off_template = action['choose'][1]['conditions'][0]['value_template']

    def entities(self) -> list[tuple[str, str, Any, dict]]:
        """Zwraca (rodzaj, nazwa, szablon stanu, atrybuty) wszystkich encji."""
        out: list[tuple[str, str, Any, dict]] = []
        for block in self.configuration.get('template', []):
            for kind in block:
                for entity in block[kind]:
                    out.append((kind, entity.get('name', '?'),
                                entity.get('state'), entity.get('attributes', {}) or {}))
        return out

    def availability(self) -> dict[str, str]:
        """Zwraca {entity_id: szablon availability} encji, ktore go maja."""
        out: dict[str, str] = {}
        for block in self.configuration.get('template', []):
            for kind in block:
                for entity in block[kind]:
                    if 'availability' in entity:
                        out[f"{kind}.{slugify(entity['name'])}"] = entity['availability']
        return out

    def render_entities(self, states: dict[str, dict], moment: datetime) -> None:
        """Renderuje encje template i wpisuje ich stany do `states`."""
        env = build_env(states, moment)

        def render(template: Any) -> Any:
            if not isinstance(template, str):
                return template
            return env.from_string(template).render().strip()

        availability = self.availability()
        for kind, name, state_template, attributes in self.entities():
            entity_id = f'{kind}.{slugify(name)}'
            if entity_id in availability and render(availability[entity_id]) != 'True':
                states[entity_id] = {'state': 'unavailable', 'attributes': {}}
                continue
            state = render(state_template)
            if kind == 'binary_sensor':
                # HA zamienia stan template binary_sensora na 'on'/'off'
                state = {'True': 'on', 'False': 'off'}.get(str(state), str(state))

            rendered_attributes: dict[str, Any] = {}
            for key, template in attributes.items():
                value = render(template)
                rendered_attributes[key] = value

            states[entity_id] = {'state': state, 'attributes': rendered_attributes}

    def render_condition(self, template: str, states: dict[str, dict], moment: datetime) -> bool:
        env = build_env(states, moment)
        return env.from_string(template).render().strip() == 'True'


# ------------------------------------------------------------------ symulacja

def build_states(
    payload_today: dict,
    payload_tomorrow: dict,
    *,
    charged: int = 0,
    switch_on: bool = False,
) -> dict[str, dict]:
    """Buduje zbior stanow encji HA (tak jak command_line je wystawia)."""
    return {
        'sensor.tge_v2_ceny_dzis': {
            'state': str(payload_today.get('data_points', 0)),
            'attributes': payload_today,
        },
        'sensor.tge_v2_ceny_jutro': {
            'state': str(payload_tomorrow.get('data_points', 0)),
            'attributes': payload_tomorrow,
        },
        'input_number.tge_v2_ladowane_godziny': {
            'state': str(charged),
            'attributes': {'unit_of_measurement': 'h'},
        },
        SWITCH: {'state': 'on' if switch_on else 'off', 'attributes': {}},
    }


def simulate_day(
    config: HomeAssistantConfig,
    payload_today: dict,
    *,
    out_of_service: tuple[int, ...] = (),
    day: date | None = None,
) -> dict[str, Any]:
    """Przechodzi przez 24 godziny i liczy godziny z wlaczonym ladowaniem.

    Args:
        config: wczytana konfiguracja HA.
        payload_today: zawartosc today.json.
        out_of_service: godziny, w ktorych Home Assistant nie dziala
            (przelacznik zostaje w ostatnim stanie, licznik sie nie inkrementuje).
        day: data symulacji (domyslnie z planu).

    Returns:
        Slownik z wynikami: godziny ladowania, okno, itp.
    """
    day = day or date.fromisoformat(payload_today.get('day', '2026-01-01'))
    switch_on = False
    charged_hours: list[int] = []
    windows: set[tuple[int, ...]] = set()

    for hour in range(HOURS_IN_DAY):
        moment = datetime(day.year, day.month, day.day, hour, 0, 0)
        states = build_states(payload_today, payload_today,
                              charged=len(charged_hours), switch_on=switch_on)
        config.render_entities(states, moment)

        window = states.get('binary_sensor.tge_v2_najtansze_5h', {})
        attributes = window.get('attributes', {})
        raw_window = attributes.get('window_hours')
        if isinstance(raw_window, str) and raw_window.strip():
            try:
                windows.add(tuple(int(part) for part in raw_window.split(',') if part.strip()))
            except ValueError:
                pass

        if hour in out_of_service:
            # HA nie dziala - przelacznik zostaje jak byl, licznik nie rosnie.
            if switch_on:
                charged_hours.append(hour)
            continue

        want_on = config.render_condition(config.turn_on_template, states, moment)
        want_off = config.render_condition(config.turn_off_template, states, moment)

        if want_on and not switch_on:
            switch_on = True
        elif want_off and switch_on:
            switch_on = False

        if switch_on:
            charged_hours.append(hour)

    plan = payload_today.get('plan') or {}
    return {
        'charged_hours': charged_hours,
        'charged_count': len(charged_hours),
        'plan_hours': list(plan.get('hours', [])),
        'windows': sorted(windows),
        'out_of_service': list(out_of_service),
    }


# ------------------------------------------------------------------ scenariusze

def _scale_payload(payload: dict, factor: float) -> dict:
    """Mnozy wszystkie ceny w payloadzie (scenariusze: tani / drogi dzien)."""
    scaled = json.loads(json.dumps(payload))
    for entry in scaled.get('fixing_i_prices', []):
        entry['fixing_i_price_pln_kwh'] = round(entry['fixing_i_price_pln_kwh'] * factor, 6)
        entry['total'] = round(entry['total'] * factor, 6)
    for entry in scaled.get('prices', []):
        entry['rce_pln'] = round(entry['rce_pln'] * factor, 6)
        entry['total_pln'] = round(entry['total_pln'] * factor, 6)
    return scaled


def _trim_payload(payload: dict, hours_to_keep: int) -> dict:
    """Zostawia tylko czesc godzin (scenariusz: niepelne dane)."""
    trimmed = json.loads(json.dumps(payload))
    keep = {hour for hour in range(1, hours_to_keep + 1)}
    trimmed['fixing_i_prices'] = [
        entry for entry in trimmed.get('fixing_i_prices', []) if entry['hour'] in keep
    ]
    trimmed['prices'] = [
        entry for entry in trimmed.get('prices', [])
        if int(entry.get('dtime', 'T00')[11:13]) + 1 in keep
    ]
    trimmed['data_points'] = len(trimmed['fixing_i_prices'])
    return trimmed


def _load_fixture_payload(tariff) -> tuple[dict, dict]:
    """Buduje payloady z zapisanej strony TGE (bez sieci)."""
    from .planner import build_day_prices, build_plan
    from .publisher import build_payload
    from .tge import parse_fixings

    if not FIXTURE.exists():
        raise RuntimeError(f'Brak fixture: {FIXTURE}')

    fixings = parse_fixings(FIXTURE.read_bytes())
    if not fixings:
        raise RuntimeError('Fixture nie zawiera tabeli Fixing I')

    day = fixings[0].day
    day_prices = build_day_prices(day, fixings, tariff,
                                  fetched_at=datetime.now().isoformat(),
                                  source_url='fixture://tge')
    plan = build_plan(day_prices, tariff)
    payload = build_payload(day_prices, plan, tariff, label='today')
    return payload, payload


def run_scenarios(verbose: bool = True, ha_dir: Path | None = None) -> int:
    """Odpala scenariusze i wypisuje wyniki. Zwraca kod wyjscia (0 = OK)."""
    from .config import Tariff

    tariff = Tariff()
    config = HomeAssistantConfig(ha_dir)
    payload, _ = _load_fixture_payload(tariff)

    scenarios = [
        ('zwykly dzien', payload, ()),
        ('HA padlo o 02:00-04:00 (przed oknem)', payload, (2, 3, 4)),
        ('HA padlo o 03:00-05:00 (w trakcie okna)', payload, (3, 4, 5)),
        ('caly dzien drogi (x2.5)', _scale_payload(payload, 2.5), ()),
        ('caly dzien tani (x0.4)', _scale_payload(payload, 0.4), ()),
        ('niepelne dane (12 godzin)', _trim_payload(payload, 12), ()),
    ]

    print('\n=== Symulacja doby ladowania (prawdziwe szablony z homeassistant/) ===\n')
    failures = 0

    for label, scenario_payload, outage in scenarios:
        result = simulate_day(config, scenario_payload, out_of_service=outage)
        count = result['charged_count']
        hours = result['charged_hours']
        plan = result['plan_hours']
        expected = 5

        ok = count >= expected
        failures += 0 if ok else 1

        if verbose:
            print(f'  {label}')
            print(f'    plan (najtansze {len(plan)} h): {plan}')
            print(f'    ladowanie ON: {count} h -> {hours}')
            print(f'    okno w ciagu doby: {len(result["windows"])} wariantow '
                  f'{result["windows"] if len(result["windows"]) > 1 else ""}')
            print(f'    [{"OK " if ok else "ZLA"}] minimum {expected} h dziennie')
            if outage:
                print(f'    (HA niedostepne w godzinach {list(outage)})')
            print()

    print(f'  Scenariuszy z błędem: {failures}\n')
    return 0 if failures == 0 else 1
