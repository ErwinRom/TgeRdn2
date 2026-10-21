"""Testy struktury automatyzacji.

HA odrzuca automatyzacje z bledami w konfiguracji ("nie jest aktywna, poniewaz
konfiguracja zawiera bledy"), wiec struktura musi byc zgodna ze schematem
integracji `automation` (homeassistant/components/automation/config.py):

  - poziom najwyzszy to LISTA automatyzacji
  - kazda automatyzacja: id, alias, triggers, actions, mode, ...
  - `choose` i `default` to RODZESTWA w ramach jednej akcji (nie `default`
    wewnatrz listy `choose`)
  - `conditions` i `sequence` to listy
  - akcje: action/service + target + data
"""

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
HA = REPO / 'tgerdn' / 'homeassistant'

AUTOMATION_KEYS = {
    'id', 'alias', 'description', 'mode', 'max', 'max_exceeded', 'variables',
    'trigger_variables', 'triggers', 'trigger', 'conditions', 'condition',
    'actions', 'action',
}


def _load(name: str) -> list:
    data = yaml.safe_load((HA / name).read_text(encoding='utf-8'))
    assert isinstance(data, list), f'{name}: najwyzszy poziom musi byc lista'
    return data


@pytest.fixture(scope='module')
def canonical():
    return _load('automation.yaml')


@pytest.fixture(scope='module')
def parallel():
    return _load('tgerdn_v2_automation.yaml')


@pytest.mark.parametrize('name', ['automation.yaml', 'tgerdn_v2_automation.yaml'])
def test_plik_to_lista_automatyzacji(name):
    assert _load(name)


@pytest.mark.parametrize('name', ['automation.yaml', 'tgerdn_v2_automation.yaml'])
def test_każda_automatyzacja_ma_dozwolone_klucze(name):
    for automation in _load(name):
        extra = set(automation) - AUTOMATION_KEYS
        assert not extra, f'{name}: automatyzacja {automation.get("id")} ma niedozwolone klucze {extra}'


@pytest.mark.parametrize('name', ['automation.yaml', 'tgerdn_v2_automation.yaml'])
def test_każda_automatyzacja_ma_id_alias_i_akcje(name):
    for automation in _load(name):
        assert automation.get('id'), 'automatyzacja bez id'
        assert automation.get('alias'), f'automatyzacja {automation.get("id")} bez alias'
        assert automation.get('actions') or automation.get('action'), (
            f'automatyzacja {automation.get("id")} bez akcji'
        )


@pytest.mark.parametrize('name', ['automation.yaml', 'tgerdn_v2_automation.yaml'])
def test_choose_i_default_sa_rodzestwami(name):
    """`default` jest rodzenstwem `choose` w ramach jednej akcji.

    W blednej wersji `default` byl wpisem listy `choose` - wtedy HA
    interpretowalby go jako kolejna galaz i `default` bylby nieuzywany.
    """
    for automation in _load(name):
        for action in automation.get('actions', []):
            if 'choose' not in action:
                continue
            assert isinstance(action['choose'], list)
            assert 'default' not in action['choose'], (
                f'automatyzacja {automation.get("id")}: `default` musi byc rodzenstwem '
                '`choose`, nie elementem listy `choose`'
            )
            if 'default' in action:
                assert isinstance(action['default'], list)
                assert action['default'], 'pusty `default`'


@pytest.mark.parametrize('name', ['automation.yaml', 'tgerdn_v2_automation.yaml'])
def test_warunki_i_akcje_sa_listami(name):
    for automation in _load(name):
        for action in automation.get('actions', []):
            for choice in action.get('choose', []):
                assert isinstance(choice.get('conditions', []), list)
                assert isinstance(choice.get('sequence', []), list)
            if 'if' in action:
                assert isinstance(action['if'], list)
                assert isinstance(action.get('then', []), list)


@pytest.mark.parametrize('name', ['automation.yaml', 'tgerdn_v2_automation.yaml'])
def test_triggery_sa_lista(name):
    for automation in _load(name):
        triggers = automation.get('triggers', automation.get('trigger'))
        assert isinstance(triggers, list) and triggers, (
            f'automatyzacja {automation.get("id")} bez triggerow'
        )


def test_warianty_nie_maja_tego_samego_id(canonical, parallel):
    canonical_ids = {a['id'] for a in canonical}
    parallel_ids = {a['id'] for a in parallel}
    assert not (canonical_ids & parallel_ids), (
        f'kolizja id miedzy wariantami: {canonical_ids & parallel_ids}'
    )


def test_przelaczniki_sa_te_same_w_obie_wariantach(canonical, parallel):
    """Oba warianty steruja tym samym przelacznikiem - inaczej dwa niezalezne
    uklady laduja auto w roznych godzinach."""
    def switches(automations):
        found = set()
        for automation in automations:
            for action in automation.get('actions', []):
                for step in _walk(action):
                    target = step.get('target') or {}
                    entities = target.get('entity_id') or []
                    if isinstance(entities, str):
                        entities = [entities]
                    for entity in entities:
                        if entity.startswith('switch.'):
                            found.add(entity)
        return found

    assert switches(canonical) == switches(parallel)
    assert switches(canonical), 'zadna automatyzacja nie steruje przelacznikiem'


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)
