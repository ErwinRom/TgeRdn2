# Stan migracji HA

> Dokument powstał 2026-10-21 podczas migracji v1 → v2. **Migracja
> zakończona 2026-10-22**: konfiguracja v1 usunięta z HA, działa tylko v2.

## TL;DR

- Dodatek **v2.1.9** pobiera ceny z tge.pl i zapisuje pliki JSON.
- W HA działa **wyłącznie wariant v2** (encje `tge_v2_*`). Dodatek v1
  i cała jego konfiguracja są usunięte.
- Historia encji v1 przepadła. Encje `tge_v2_*` mają historię od 2026-10-21.

## Co jest zainstalowane w HA

| Plik | Zawartość |
|---|---|
| `/config/packages/tgerdn_v2.yaml` | encje v2 (z `tgerdn/homeassistant/tgerdn_v2.yaml`) |
| `/config/automations.yaml` | `tge_v2_charging_car`, `tge_v2_charging_counter` (z `tgerdn_v2_automation.yaml`) |
| `/config/ui-lovelace.yaml` | 2 widoki z `lovelace_v2.yaml` |

Dodatek: `TGE RDN` (v2) z repo `ErwinRom/TgeRdn2` → `/config/tgerdn/today.json`,
`/config/tgerdn/tomorrow.json`.

Zmiana w repo w tych plikach **nie trafia do HA sama**: pakiet, automatyzacje
i widoki trzeba po każdej zmianie wkleić ręcznie. Aktualizacja dodatku
zmienia tylko kod pobierający ceny.

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

## Przebieg sprzątania (wykonane 2026-10-22)

1. Wyłączona stara automatyzacja (`id: '1791711498340'`). Wcześniej
   naprawiono `tge_v2_charging_car` (2.1.8): przez błąd w `default:` nigdy
   nie była aktywna, a ładowaniem sterowała tylko automatyzacja v1.
2. Zatrzymany dodatek v1 („TGE RDN Scraper”, repo `ErwinRom/TgeRdn`).
3. Usunięta stara automatyzacja z `automations.yaml`.
4. Usunięte 2 stare widoki z `ui-lovelace.yaml`.
5. Usunięty `/config/packages/tgerdn.yaml`.
6. Usunięty blok `template:` (2 stare encje) z `/config/configuration.yaml`.
7. Sprawdzenie konfiguracji i restart HA.
8. Wyczyszczone osierocone encje v1 z rejestru.
9. Odinstalowany dodatek v1.

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

- Wersja **2.1.9** spójna w `config.yaml`, `Dockerfile`, `CHANGELOG.md`
  (pilnuje tego `tests/test_manifest.py`).
- **106 testów** przechodzi (`python3 -m pytest tests/ -q`).
- W repo jest tylko wariant v2: `tgerdn_v2.yaml` (generowany przez
  `tools/generate_ha_config.py`), `tgerdn_v2_automation.yaml`,
  `lovelace_v2.yaml`. Kanoniczne pliki usunięto w 2.1.7. Symulator
  (`tgerdn simulate`) i testy renderowania działają na v2.

## Do zrobienia przy okazji

- Rozważyć walidację configu schematem HA (venv z Home Assistantem) —
  eliminuje tę klasę błędów zanim trafią do HA.
