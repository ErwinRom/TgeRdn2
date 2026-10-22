"""Repo jest publiczne - prywatne dane srodowiska nie moga trafic do gita.

Skill `tgerdn` trzyma je w `.claude/local/` (poza gitem). Te testy pilnuja,
ze katalog jest ignorowany, a sledzone pliki `.claude/` nie zawieraja
adresow sieci lokalnej ani tokenow.
"""

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

SECRETS = {
    'adres IP sieci lokalnej': re.compile(
        r'\b(?:10|192\.168|172\.(?:1[6-9]|2\d|3[01]))(?:\.\d{1,3}){2,3}\b'
    ),
    'token JWT (np. long-lived token HA)': re.compile(r'\beyJ[\w-]{10,}\.[\w-]{10,}'),
    'naglowek Bearer': re.compile(r'Bearer\s+[\w.-]{20,}'),
    'klucz prywatny': re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
}


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(['git', *args], cwd=REPO, capture_output=True, text=True)


@pytest.fixture(scope='module')
def git_available():
    if _git('rev-parse', '--git-dir').returncode != 0:
        pytest.skip('poza repozytorium git')


def test_katalog_prywatny_jest_ignorowany(git_available):
    result = _git('check-ignore', '-q', '.claude/local/srodowisko.md')
    assert result.returncode == 0, '.claude/local/ musi byc w .gitignore'


def test_sledzone_pliki_claude_bez_sekretow(git_available):
    tracked = _git('ls-files', '.claude').stdout.split()
    for name in tracked:
        text = (REPO / name).read_text(encoding='utf-8', errors='replace')
        for label, pattern in SECRETS.items():
            assert not pattern.search(text), f'{name}: wyglada na {label}'
