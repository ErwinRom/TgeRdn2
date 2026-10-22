---
name: tgerdn
description: Praca w repo TgeRdn2 - dodatek Home Assistant (TGE RDN, ceny Fixing I, plan ładowania auta). Używaj przy każdej zmianie kodu Pythona, plików HA (pakiet, automatyzacje, Lovelace), wersji dodatku, przy analizie ostrzeżeń i błędów z logów Home Assistant oraz przy pytaniach o progi, marginesy i taryfę.
---

# TgeRdn2 - dodatek HA: ceny TGE i ładowanie auta

## Najpierw: środowisko lokalne (prywatne)

Repo jest **publiczne**. Szczegóły środowiska użytkownika (adres i dostęp do
HA, sprzęt, wersja HA, dane z faktury, wszystko, czego nie wolno pokazać)
są w pliku `.claude/local/srodowisko.md`, który jest w `.gitignore`.

- Jeśli plik istnieje, przeczytaj go przed pracą wymagającą wiedzy
  o instalacji HA.
- Nowe prywatne fakty dopisuj **tylko tam**. Nigdy do plików w gicie:
  kodu, YAML, README, CHANGELOG, commitów, tego skilla.
- Nie wolno commitować: adresów IP i hostów, tokenów, haseł, kluczy SSH,
  numerów PPE/liczników i umów, adresu zamieszkania, danych z faktur poza
  stawkami taryfowymi (te są publiczne w taryfie OSD).
- `switch.0xb40ecfd05e500000` jest już publiczny w repo. To nie jest sekret.

## Architektura

```
dodatek HA (kontener, python:3.13-slim, zero zależności)
  run.sh -> python -m tgerdn serve        (harmonogram w Pythonie, bez crona)
    tge.py        pobiera stronę tge.pl i parsuje tabelę Fixing I (html.parser)
    planner.py    ceny + margines -> N najtańszych godzin doby (Plan)
    publisher.py  atomowy zapis /config/tgerdn/today.json, tomorrow.json
HA
  command_line  sensor.tge_v2_ceny_dzis / _jutro   (cat pliku JSON)
  template      sensor.tge_v2_reguly (progi), sensor.tge_v2_aktualna_cena,
                binary_sensor.tge_v2_najtansze_5h (_jutro)
  input_number  tge_v2_ladowane_godziny (licznik godzin ładowania)
  automatyzacje tge_v2_charging_car (przełącznik), tge_v2_charging_counter
```

Moduły: `config.py` (Tariff, Settings, zmienne `TGERDN_*`), `model.py`,
`cli.py` (`fetch`, `serve`, `show`, `simulate`, `doctor`), `simulate.py`
(doba renderowana na prawdziwych szablonach HA).

**Plan liczy Python, HA tylko go odtwarza.** Progi i marginesy muszą być
zgodne w dwóch miejscach: `Tariff` w `tgerdn/config.py` (i opcje/zmienne
dodatku) oraz `sensor.tge_v2_reguly` w generatorze.

## Pliki HA i jak trafiają do HA

| Plik w repo | W HA | Uwagi |
|---|---|---|
| `tgerdn/homeassistant/tgerdn_v2.yaml` | `/config/packages/tgerdn_v2.yaml` | **generowany**: edytuj `tools/generate_ha_config.py`, potem `python3 tools/generate_ha_config.py` |
| `tgerdn/homeassistant/tgerdn_v2_automation.yaml` | koniec `/config/automations.yaml` | automatyzacje nie mogą być w pakiecie |
| `tgerdn/homeassistant/lovelace_v2.yaml` | `/config/ui-lovelace.yaml` | 2 widoki |

Aktualizacja dodatku zmienia **tylko kod pobierający ceny**. Zmiany w YAML-ach
HA użytkownik wkleja ręcznie, a potem przeładowuje (automatyzacje / encje
szablonów) albo restartuje HA (`command_line`, `input_number` w pakiecie).
Po każdej zmianie YAML powiedz wprost, co wkleić gdzie i co przeładować.

## Pułapki HA (każda już raz kosztowała rundę)

Pełna lista z kontekstem: `MIGRACJA.md`, sekcja „Pułapki”. Najważniejsze:

- `!include` wewnątrz listy YAML jest błędem składni i HA odrzuca cały plik.
- W `choose` gałąź z `conditions` + `sequence` jest elementem `choose`,
  a `default:` to sama lista akcji.
- `command_line: - sensor: {…}`: platforma mapuje do pojedynczego słownika.
- `input_number` w pakiecie jest słownikiem i nie ma `unique_id`.
- Wartości `attributes:` w template sensorze muszą być stringami-szablonami.
- Literówka w `entity_id` w szablonie: `states()` zwraca `unknown`,
  a `| float(0)` zamienia to po cichu w 0. Testy referencji tego pilnują.
- **Tryb automatyzacji:** o pełnej godzinie kilka triggerów przychodzi
  w tej samej sekundzie (time_pattern, cena, okno, licznik). `mode: single`
  daje w logach „Already running” i gubi wywołania. Automatyzacje reagujące
  na stan powinny mieć `queued` (akcje idempotentne).
- Ceny na jutro TGE publikuje około 12:00, więc „Brak danych” rano to norma.

Przy nowej pułapce dodaj ją do `MIGRACJA.md` i zakoduj w teście
`tests/test_ha_*.py`, jeśli da się ją sprawdzić statycznie.

## Środowisko deweloperskie

- Kod produkcyjny: tylko biblioteka standardowa, Python >= 3.11 (obraz ma
  3.13). Nie dodawaj zależności produkcyjnych.
- Dev: `pytest`, `jinja2`, `pyyaml` (`pip install -e .[dev]`).
- Testy: `python3 -m pytest -q`. Muszą przechodzić przed każdym commitem.
  Testy HA (`test_ha_*`) sprawdzają strukturę wobec schematów HA, referencje
  encji i renderują szablony Jinja. `tgerdn simulate` przechodzi dobę na
  prawdziwych plikach HA.
- Diagnostyka danych: `python3 -m tgerdn doctor`, `python3 -m tgerdn show`.
- Testy nie mogą zależeć od dzisiejszej daty (fixture `tests/fixtures/`).

## Konwencje

- Język: polski. Komentarze i komunikaty w kodzie bez polskich znaków,
  dokumentacja (README, CHANGELOG, MIGRACJA) z polskimi znakami.
- **Każda zmiana w repo podnosi wersję**: `version` w `config.yaml`,
  `io.hass.version` w `Dockerfile`, nowa sekcja `## X.Y.Z` na górze
  `CHANGELOG.md` i krótki `changelog:` w `config.yaml` (widać go w UI
  supervisora). `tests/test_manifest.py` pilnuje zgodności. Bez nowego
  numeru supervisor nie pobierze aktualizacji.
- Commit: `vX.Y.Z: krótki opis po polsku`, jeden commit na wersję.
  Commituj tylko na prośbę użytkownika.
- Wpis w CHANGELOG wyjaśnia **dlaczego**: objaw, przyczynę i skutek.
- Komentarz w YAML przy nieoczywistej decyzji (jak `mode: queued`).

## Analiza zgłoszeń z HA

Użytkownik wkleja ostrzeżenia z „Ustawienia → System → Logi”. Rejestrator
`homeassistant.components.automation.<slug_aliasu>` wskazuje automatyzację
po aliasie. Ustal przyczynę w YAML-u z repo, popraw ją, dodaj test
regresyjny, podbij wersję i podaj, co trzeba wkleić w HA.
