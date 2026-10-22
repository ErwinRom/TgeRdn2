"""Testy ksztaltu plikow konfiguracyjnych HA.

HA ma inne reguly dla plikow w katalogu `packages/` niz dla pliku glownego:

  command_line:  lista wpisow, kazdy {platform: POJEDYNCZY dict}
                 (COMBINED_SCHEMA w integracji command_line - `sensor:` to
                  jeden konfig, nie lista)
  template:      lista (integracja ma PACKAGE_MERGE_HINT = "list")
  input_number:  w pakiecie slownik, w pliku glownym lista lub slownik
                 (pakiet musi byc slownikiem, inaczej supervisor rzuca
                  "integration 'input_number' cannot be merged, expected a dict")

Blad w tym miejscu nie wychodzi w zadnych testach renderowania - HA odrzuca
caly konfiguracje. Dlatego ksztalt sprawdzamy osobno.
"""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
HA = REPO / 'tgerdn' / 'homeassistant'

PLATFORMS = ('sensor', 'binary_sensor', 'switch', 'cover', 'notify')


def _load(name: str) -> dict:
    return yaml.safe_load((HA / name).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def package_config():
    """Wariant pakietowy - encje w katalogu packages/."""
    return _load('tgerdn_v2.yaml')


def _command_line_entries(config: dict) -> list:
    return config['command_line']


def test_command_line_jest_lista(package_config):
    config = package_config
    assert isinstance(config['command_line'], list)


def test_command_line_platform_to_jeden_dict(package_config):
    """`sensor:` mapuje do POJEDYNCZEGO slownika, nie do listy.

    HA wymaga tego w COMBINED_SCHEMA integracji command_line - lista powoduje
    bled "expected a mapping for dictionary value 'command_line->N->sensor'".
    """
    config = package_config
    for index, entry in enumerate(_command_line_entries(config)):
        assert isinstance(entry, dict), f'wpis command_line[{index}] to nie slownik'
        for platform, platform_config in entry.items():
            assert platform in PLATFORMS, f'nieznana platforma {platform}'
            assert isinstance(platform_config, dict), (
                f"command_line[{index}].{platform} musi byc slownikiem "
                f'(jest {type(platform_config).__name__}) - '
                'kazda platforma to jeden konfig, nie lista'
            )
            assert 'name' in platform_config, f'command_line[{index}].{platform} bez name'


def test_command_line_ma_unikalne_id(package_config):
    config = package_config
    ids = [entry[platform]['unique_id']
           for entry in _command_line_entries(config)
           for platform in entry]
    assert len(ids) == len(set(ids)), f'powtorzone unique_id: {ids}'


def test_input_number_w_pakiecie_to_slownik(package_config):
    """Pakiet musi byc slownikiem - lista daje 'cannot be merged, expected a dict'."""
    assert isinstance(package_config['input_number'], dict), (
        'input_number w wariancie pakietowym musi byc slownikiem, nie lista'
    )
    for slug, conf in package_config['input_number'].items():
        assert isinstance(conf, dict)
        assert 'min' in conf and 'max' in conf


def test_template_jest_lista(package_config):
    """Integracja template ma PACKAGE_MERGE_HINT = 'list' - lista jest poprawna
    takze w pakiecie."""
    config = package_config
    assert isinstance(config['template'], list)
    for block in config['template']:
        assert isinstance(block, dict)
        for platform, entities in block.items():
            assert platform in ('sensor', 'binary_sensor')
            assert isinstance(entities, list)
            for entity in entities:
                assert 'name' in entity and 'unique_id' in entity


def test_encje_maja_id_i_nazwe(package_config):
    config = package_config
    for block in config['template']:
        for entities in block.values():
            for entity in entities:
                assert entity.get('unique_id'), f'encja bez unique_id: {entity.get("name")}'
                assert entity.get('name'), 'encja bez name'
