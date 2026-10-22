# Stan migracji HA i plan sprzątania

> Dokument powstał 2026-10-21 podczas migracji v1 → v2. Opisuje **co jest
> zainstalowane**, **co działa** i **co zostało do sprzątania**.

## TL;DR

- Dodatek **v2.1.8** działa, pobiera ceny z tge.pl i zapisuje pliki JSON.
- W HA działają **dwa komplety encji równolegle** (stary i nowy) — celowo,
  żeby dało się bezpiecznie porównać działanie przed sprzątaniem.
- Sprzątanie **nie zostało wykonane**. Wszystko stare działa i może zostać.

## Co jest zainstalowane w HA

| Plik | Zawartość | Stan |
|---|---|---|
| `/config/packages/tgerdn.yaml` | **stare** encje (command_line + template) | do usunięcia w sprzątaniu |
| `/config/packages/tgerdn_v2.yaml` | **nowe** encje, prefiks `tge_v2_` | **docelowy**, zostaje |
| `/config/automations.yaml` | stara automatyzacja + 2 nowe z wariantu v2 | usunąć starą, v2 zostają |
| `/config/configuration.yaml` | blok `template:` w roocie (2 stare encje) | do usunięcia |
| `/config/ui-lovelace.yaml` | 4 widoki (2 stare + 2 z wariantu v2) | usunąć 2 stare, v2 zostają |

Dodatek: `TGE RDN` (v2) z repo `ErwinRom/TgeRdn2` → `/config/tgerdn/today.json`,
`/config/tgerdn/tomorrow.json`.

## Encje nowego wariantu (prefiks `tge_v2_`)

```
sensor.tge_v2_ceny_dzis          stan: 24 (liczba cen)
sensor.tge_v2_ceny_jutro         stan: 24
sensor.tge_v2_aktualna_cena       stan: cena bieżącej godziny (spot + margines)
sensor.tge_v2_aktualna_cena_jutro stan: jutrzejsza cena w bieżącej godzinie
sensor.tge_v2_reguly              stan: ok
binary_sensor.tge_v2_najtansze_5h         stan: on/off (okno ładowania)
binary_sensor.tge_v2_najtansze_5h_jutro   stan: on/off (plan na jutro)
input_number.tge_v2_ladowane_godziny      licznik godzin ładowania
```

## Plan sprzątania (6 kroków)

**Docelowy jest wariant `tge_v2_`** (decyzja z 2026-10-22). Działa i dalej
będzie rozwijany, więc zostaje w HA w obecnej postaci, a usuwamy tylko
konfigurację v1. Historia encji v1 przepadnie. Encje `tge_v2_*` mają
własną historię od 2026-10-21.

Zostaje w HA bez zmian: `/config/packages/tgerdn_v2.yaml`, automatyzacje
`tge_v2_charging_car` i `tge_v2_charging_counter`, oba widoki z
`lovelace_v2.yaml`.

1. Wyłączyć, a potem usunąć stary dodatek **v1** („TGE RDN Scraper" z repo
   `ErwinRom/TgeRdn`) — inaczej oba dodatki pobierają z tge.pl.
2. Usunąć `/config/packages/tgerdn.yaml` (stare encje command_line + template).
3. Usunąć blok `template:` (2 stare encje) z roota `/config/configuration.yaml`.
4. `automations.yaml`: usunąć starą automatyzację (`id: '1791711498340'`).
   Wariantowe `tge_v2_*` zostają.
5. `ui-lovelace.yaml`: usunąć 2 stare widoki, zostawić 2 widoki v2.
6. Wyczyścić z rejestru encje osierocone po krokach 2–3 (stare `sensor.*`
   i `binary_sensor.*` z v1). Jeśli w HA jeszcze widnieje
   `input_number.tgerdn_v2_ladowane_godziny` (nazwa sprzed poprawki sluga
   w 2.1.3), też ją usunąć. Właściwy licznik to
   `input_number.tge_v2_ladowane_godziny`.

Po każdym kroku: *Narzędzia deweloperskie → Sprawdź konfigurację*, potem
restart.

## Pułapki (każda z nich kosztowała rundę)

- **`!include` wewnątrz listy YAML jest błędny.** HA odrzuca cały plik:
  `could not find expected ':'`. `!include` działa tylko jako jedyna zawartość
  pliku albo jako wartość klucza (`automation: !include_dir_list automations/`).
  Automatyzacje wklejać **na końcu listy** w `automations.yaml`.
- **`default:` w `choose` to lista akcji, nie gałęzi.** Element z
  `conditions` + `sequence` w `default` → HA odrzuca automatyzację:
  `not a valid option at 'actions[0].default[0].conditions'`. Gałąź
  z warunkami musi być kolejnym elementem `choose`.
- **`command_line:`** — klucz platformy (`sensor:`) mapuje do **pojedynczego
  słownika**, nie listy.
- **`input_number:`** — w pliku głównym lista, w katalogu `packages/` słownik.
  Helper **nie przyjmuje `unique_id`** (schemat go nie ma).
- **Atrybuty template sensora** — każda wartość w `attributes:` musi być
  **template'em** (stringiem). Lista/liczba → `template value should be a string`.
- **`entity_id` helpera `input_number`** = `input_number.<slug klucza>` —
  slug musi się zgadzać z tym, o czym mówią szablony, inaczej `states()`
  zwraca `unknown` i `| float(0)` zamienia to w zero (błąd bez śladu).

Te reguły są zakodowane w testach `tests/test_ha_config_shape.py`,
`tests/test_ha_config_keys.py`, `tests/test_ha_references.py`,
`tests/test_ha_automation.py`.

## Stan repo

- Wersja **2.1.8** spójna w `config.yaml`, `Dockerfile`, `CHANGELOG.md`
  (pilnuje tego `tests/test_manifest.py`).
- **106 testów** przechodzi (`python3 -m pytest tests/ -q`).
- W repo jest tylko wariant v2: `tgerdn_v2.yaml` (generowany przez
  `tools/generate_ha_config.py`), `tgerdn_v2_automation.yaml`,
  `lovelace_v2.yaml`. Kanoniczne pliki usunięto w 2.1.7. Symulator
  (`tgerdn simulate`) i testy renderowania działają na v2.

## Do zrobienia przy okazji

- Wyłączyć stary dodatek v1 już teraz (krok 1) — dwie instancje pobierają
  z tge.pl w tym samym czasie.
- Rozważyć walidację configu schematem HA (venv z Home Assistantem) —
  eliminuje tę klasę błędów zanim trafią do HA.
