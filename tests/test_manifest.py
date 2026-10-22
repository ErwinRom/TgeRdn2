"""Testy manifestu dodatku.

Supervisor HA porownuje `version` z `config.yaml` przy aktualizacji dodatku.
Jesli numer sie nie zmieni, HA nie pobierze nowej wersji - a uzytkownik nie
dostanie zmian. Dlatego wersje musza byc zgodne w trzech miejscach:
config.yaml, etykieta w Dockerfile i CHANGELOG.md.
"""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope='module')
def manifest():
    return yaml.safe_load((REPO / 'config.yaml').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def dockerfile():
    return (REPO / 'Dockerfile').read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def changelog():
    path = REPO / 'CHANGELOG.md'
    assert path.is_file(), 'brak CHANGELOG.md - supervisor pokazuje zmiany w UI'
    return path.read_text(encoding='utf-8')


def _changelog_version(changelog: str) -> str:
    match = re.search(r'^## (\S+)', changelog, re.M)
    assert match, 'CHANGELOG.md nie zawiera sekcji "## <wersja>"'
    return match.group(1)


def test_manifest_ma_wersje(manifest):
    assert manifest.get('version'), 'config.yaml musi miec pole version'


def test_manifest_ma_opis_zmian(manifest):
    """Klucz `changelog` jest opcjonalny dla schematu, ale supervisor pokazuje
    go uzytkownikowi przy aktualizacji - bez niego nie wiadomo co sie zmienilo."""
    assert manifest.get('changelog', '').strip(), 'config.yaml powinien miec klucz changelog'


def test_wersje_wszystkich_plikow_sa_zgodne(manifest, dockerfile, changelog):
    version = manifest['version']
    label = re.search(r'io\.hass\.version="([^"]+)"', dockerfile)
    assert label, 'brak etykiety io.hass.version w Dockerfile'
    assert label.group(1) == version, (
        f'Dockerfile ma {label.group(1)}, config.yaml {version}'
    )
    assert _changelog_version(changelog) == version, (
        f'CHANGELOG.md opisuje inna wersje niz config.yaml ({version})'
    )


def test_changelog_opisuje_biezaca_wersje(changelog, manifest):
    sekcje = re.findall(r'^## (\S+)', changelog, re.M)
    assert sekcje[0] == manifest['version']
    assert len(sekcje) == len(set(sekcje)), 'powtorzona wersja w CHANGELOG.md'


def test_pliki_konfiguracyjne_ha_sa_w_repozytorium():
    """Komplet do wklejenia w HA musi byc w repo - inaczej uzytkownik nie ma skad
    go wziac, a my nie mamy jak go testowac."""
    ha = REPO / 'tgerdn' / 'homeassistant'
    for name in ('tgerdn_v2.yaml', 'tgerdn_v2_automation.yaml', 'lovelace_v2.yaml'):
        path = ha / name
        assert path.is_file(), f'brak pliku {name}'
        yaml.safe_load(path.read_text(encoding='utf-8'))
