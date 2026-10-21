"""Testy kluczy konfiguracyjnych wobec schematow HA.

HA odrzuca nieznane klucze (bled typu "'xyz' is an invalid option for ...").
Kazdy klucz w plikach konfiguracyjnych musi byc w schemacie konkretnej
integracji - inaczej cala konfiguracja jest odrzucona.

Allowlisty ponizej odpowiadaja schematom z home-assistant/core:
  components/command_line/__init__.py  -> SENSOR_SCHEMA, BINARY_SENSOR_SCHEMA
  components/input_number/__init__.py  -> CONFIG_SCHEMA (helper)
  components/template/                 -> SENSOR_YAML_SCHEMA, BINARY_SENSOR_YAML_SCHEMA
"""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
HA = REPO / 'tgerdn' / 'homeassistant'

COMMAND_LINE_SENSOR = {
    'command', 'command_timeout', 'json_attributes', 'json_attributes_path',
    'name', 'icon', 'unit_of_measurement', 'value_template', 'unique_id',
    'device_class', 'state_class', 'scan_interval', 'availability',
}
COMMAND_LINE_BINARY_SENSOR = {
    'command', 'command_timeout', 'json_attributes', 'json_attributes_path',
    'name', 'icon', 'value_template', 'unique_id', 'device_class',
    'scan_interval', 'availability',
}
# helper input_number: schema NIE zawiera unique_id
INPUT_NUMBER = {
    'name', 'min', 'max', 'initial', 'step', 'icon', 'unit_of_measurement',
    'device_class', 'mode',
}
TEMPLATE_SENSOR = {
    'name', 'unique_id', 'icon', 'unit_of_measurement', 'state_class',
    'device_class', 'state', 'attributes', 'availability',
}
TEMPLATE_BINARY_SENSOR = {
    'name', 'unique_id', 'icon', 'device_class', 'state', 'attributes',
    'availability',
}


def _load(name: str) -> dict:
    return yaml.safe_load((HA / name).read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def files():
    return {name: _load(name) for name in ('configuration.yaml', 'tgerdn_v2.yaml')}


@pytest.mark.parametrize('name', ['configuration.yaml', 'tgerdn_v2.yaml'])
def test_command_line_ma_dozwolone_klucze(files, name):
    config = files[name]
    for index, entry in enumerate(config['command_line']):
        for platform, platform_config in entry.items():
            allowed = COMMAND_LINE_SENSOR if platform == 'sensor' else COMMAND_LINE_BINARY_SENSOR
            extra = set(platform_config) - allowed
            assert not extra, (
                f'command_line[{index}].{platform}: niedozwolone klucze {extra} '
                f'(dla {platform} w HA: {sorted(allowed)})'
            )


@pytest.mark.parametrize('name', ['configuration.yaml', 'tgerdn_v2.yaml'])
def test_input_number_ma_dozwolone_klucze(files, name):
    """Helper input_number nie akceptuje unique_id - HA odrzuca caly config."""
    config = files[name]
    numbers = config['input_number']
    items = numbers.items() if isinstance(numbers, dict) else [
        (key, value) for entry in numbers for key, value in entry.items()]
    for slug, conf in items:
        extra = set(conf) - INPUT_NUMBER
        assert not extra, f'input_number.{slug}: niedozwolone klucze {extra}'
        assert 'min' in conf and 'max' in conf, f'input_number.{slug}: brak min/max'


@pytest.mark.parametrize('name', ['configuration.yaml', 'tgerdn_v2.yaml'])
def test_template_ma_dozwolone_klucze(files, name):
    config = files[name]
    for block in config['template']:
        for platform, entities in block.items():
            allowed = TEMPLATE_SENSOR if platform == 'sensor' else TEMPLATE_BINARY_SENSOR
            for entity in entities:
                extra = set(entity) - allowed
                assert not extra, (
                    f'{platform} "{entity.get("name")}": niedozwolone klucze {extra}'
                )


def test_input_number_nie_ma_unique_id(files):
    """Regresja: unique_id w helperze input_number byl odrzucany przez HA."""
    for name, config in files.items():
        numbers = config['input_number']
        items = numbers.items() if isinstance(numbers, dict) else [
            (key, value) for entry in numbers for key, value in entry.items()]
        for slug, conf in items:
            assert 'unique_id' not in conf, (
                f'{name}: input_number.{slug} nie moze miec unique_id'
            )
