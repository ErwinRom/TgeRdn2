#!/usr/bin/env bash
# Entrypoint dodatku Home Assistant.
#
#   - w dodatku HA: opcje z /data/options.json
#   - w samodzielnym kontenerze: zmienne srodowiskowe
#     (OUTPUT_DIR, HOUR, CHARGING_HOURS, TIMEZONE)
#
# Nie ma tu crona ani systemda - harmonogram realizuje sam tgerdn
# (`tgerdn serve`), wiec w dodatku nie zostaje nic dodatkowego.

set -euo pipefail

# Opcje dodatku -> zmienne srodowiskowe.
eval "$(python3 - <<'PY'
import json
import os
import shlex
import sys
from pathlib import Path

options = {}
options_file = Path('/data/options.json')
if options_file.is_file():
    try:
        options = json.loads(options_file.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        print(f'[tgerdn] Nie udalo sie wczytac opcji: {error}', file=sys.stderr, flush=True)


def value(name, default):
    return os.environ.get(name.upper()) or str(options.get(name) or default)


print(f'OUTPUT_DIR={shlex.quote(value("output_dir", "/config/tgerdn"))}')
print(f'HOUR={shlex.quote(value("hour", "00:01,12:01"))}')
print(f'CHARGING_HOURS={shlex.quote(value("charging_hours", 5))}')
print(f'TIMEZONE={shlex.quote(value("timezone", "Europe/Warsaw"))}')
PY
)"

export TZ="${TIMEZONE}"
export TGERDN_OUTPUT_DIR="${OUTPUT_DIR}"
export TGERDN_CHARGING_HOURS="${CHARGING_HOURS}"

echo "[tgerdn] katalog: ${OUTPUT_DIR}"
echo "[tgerdn] godziny pobierania: ${HOUR} (${TZ})"
echo "[tgerdn] godzin ladowania dziennie: ${CHARGING_HOURS}"

exec python3 -m tgerdn serve \
    --output-dir "${OUTPUT_DIR}" \
    --hour "${HOUR}" \
    --charging-hours "${CHARGING_HOURS}"
