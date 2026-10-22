"""Test referencji do encji.

Kazdy `state_attr('sensor.x', ...)`, `states('binary_sensor.y')` i
`input_number.z` musi wskazywac na encje, ktora faktycznie istnieje.

Blad jest cichy: `states()` nieznanej encji zwraca 'unknown', a `| float(0)`
zamienia to w zero - szablon renderuje sie poprawnie, tylko zly wynik.
Dlatego sprawdzamy referencje osobno.

entity_id:
  - template / command_line  ->  platform + slug(nazwa)
  - input_number             ->  input_number + slug(klucza)
"""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
HA = REPO / 'tgerdn' / 'homeassistant'

REFERENCE = re.compile(
    r"""(?:state_attr|states)\(\s*['"]([a-z_]+\.[a-z0-9_]+)['"]"""
)
INPUT_REFERENCE = re.compile(
    r"""states\(\s*['"](input_number\.[a-z0-9_]+)['"]"""
)


def slugify(text: str) -> str:
    import unicodedata

    normalized = unicodedata.normalize('NFKD', text)
    ascii_text = ''.join(c for c in normalized if not unicodedata.combining(c))
    return ascii_text.lower().replace(' ', '_').replace('-', '_').replace('.', '')


def entity_ids(config: dict) -> set[str]:
    """Zwraca entity_id wszystkich encji zdefiniowanych w konfiguracji."""
    found = set()

    for entry in config.get('command_line', []):
        for platform, platform_config in entry.items():
            found.add(f"{platform}.{slugify(platform_config['name'])}")

    for block in config.get('template', []):
        for platform, entities in block.items():
            for entity in entities:
                found.add(f"{platform}.{slugify(entity['name'])}")

    numbers = config.get('input_number')
    if isinstance(numbers, dict):
        found.update(f'input_number.{slug}' for slug in numbers)
    elif isinstance(numbers, list):
        for item in numbers:
            found.update(f'input_number.{slug}' for slug in item)

    return found


def _templates(config: dict) -> list[str]:
    out = []
    for block in config.get('template', []):
        for entities in block.values():
            for entity in entities:
                out.append(entity.get('state') or '')
                out.extend((entity.get('attributes') or {}).values())
    return [t for t in out if isinstance(t, str)]


def _references(texts: list[str]) -> set[str]:
    found = set()
    for text in texts:
        found.update(REFERENCE.findall(text))
        found.update(INPUT_REFERENCE.findall(text))
    return found


@pytest.fixture(scope='module')
def package():
    return yaml.safe_load((HA / 'tgerdn_v2.yaml').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def automation():
    return yaml.safe_load((HA / 'tgerdn_v2_automation.yaml').read_text(encoding='utf-8'))


def test_input_number_slug_jest_entity_id_uzywany_w_szablonach(package):
    """Klucz sluga tworzy entity_id - musi byc identyczny z referencja.

    Regresja: slug 'tgerdn_v2_ladowane_godziny' dawal encje
    input_number.tgerdn_v2_ladowane_godziny, a szablony odwolywaly sie do
    input_number.tge_v2_ladowane_godziny - licznik nigdy sie nie inkrementowal.
    """
    numbers = package['input_number']
    slugs = set(numbers) if isinstance(numbers, dict) else {
        slug for item in numbers for slug in item}
    referenced = {
        ref.split('.', 1)[1]
        for ref in _references(_templates(package))
        if ref.startswith('input_number.')
    }
    assert referenced, 'szablony nie odwoluja sie do input_number'
    assert referenced <= slugs, (
        f'szablony odwoluja sie do {referenced - slugs}, a zdefiniowane sa {slugs}'
    )


def test_szablony_nie_odwoluja_sie_do_nieistniejacych_encji(package):
    known = entity_ids(package)
    referenced = _references(_templates(package))
    missing = referenced - known
    assert not missing, f'szablony odwoluja sie do nieistniejacych encji: {missing}'


def test_automatyzacja_nie_odwoluje_sie_do_nieistniejacych_encji(package, automation):
    known = entity_ids(package)
    texts = []
    for item in automation:
        for action in item.get('actions', []):
            texts.extend(_action_texts(action))
        for trigger in item.get('triggers', []):
            texts.extend(_action_texts(trigger))
    referenced = _references(texts)
    missing = referenced - known
    assert not missing, f'automatyzacja odwoluje sie do nieistniejacych encji: {missing}'


def _action_texts(node) -> list[str]:
    """Wyciaga wszystkie szablony z dowolnego fragmentu konfiguracji."""
    out = []
    if isinstance(node, str):
        out.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            out.extend(_action_texts(value))
    elif isinstance(node, list):
        for value in node:
            out.extend(_action_texts(value))
    return out
