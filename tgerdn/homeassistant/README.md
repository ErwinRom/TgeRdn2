# Konfiguracja Home Assistant — TGE RDN v2

Pliki leżą w katalogu `tgerdn/homeassistant/` (w repo: `TgeRdn2/tgerdn/homeassistant/`).
Trzy pliki do wklejenia, w kolejności:

| Plik | Co wkleić | Gdzie |
|---|---|---|
| `tgerdn_v2.yaml` | encje `command_line`, `input_number`, szablony | katalog `packages/` (patrz niżej) |
| `tgerdn_v2_automation.yaml` | ładowanie auta + licznik godzin + strażnik braku cen | `automations.yaml` (główny) |
| `lovelace_v2.yaml` | karty | dashboard (widok) |
| `lovelace_v2_auto.yaml` | sekcje | dwie sekcje z godzinami ładowania nad kartę auta |

`tgerdn_v2.yaml` jest generowany przez `tools/generate_ha_config.py` —
zmiany wprowadzaj w generatorze, nie w pliku.

---

### Gdzie wkleić encje

Encje (`tgerdn_v2.yaml`) w katalogu `packages/`:

```yaml
# configuration.yaml
packages: !include_dir_named packages
```

plik z encjami → `/config/packages/tgerdn_v2.yaml`. Nie dopisuj `!include`
do `configuration.yaml` — katalog wczytuje się sam.

Automatyzacje **nie mogą** być w pakiecie. Zawartość `tgerdn_v2_automation.yaml`
wklej **na końcu** swojego `/config/automations.yaml` jako kolejne elementy
listy (kolumna 0, na poziomie `- id:`).

> ⚠️ Nie używaj `!include` wewnątrz listy — to błędny YAML i HA odrzuci
> cały plik. `!include` działa jako jedyna zawartość pliku albo jako
> wartość klucza (np. `automation: !include_dir_list automations/`).

## 1. Pliki JSON

Scraper zapisuje dwa pliki:

| Plik | Zawartość | Sensor |
|---|---|---|
| `today.json` | ceny na dziś + plan | `sensor.tge_v2_ceny_dzis` |
| `tomorrow.json` | ceny na jutro + plan | `sensor.tge_v2_ceny_jutro` |

Domyślna ścieżka w przykładzie: `/config/tgerdn/` (katalog `config` w
kontenerze HA). Jeśli HA nie jest w kontenerze, zmień `command:` na
np. `cat /home/erwin/.local/share/tgerdn/today.json`.

Ważne: `json_attributes` **musi** zawierać `fixing_i_prices` i `plan` —
szablony czytają z nich ceny i okno ładowania.

---

## 2. Encje

| Encja | Typ | Rola |
|---|---|---|
| `sensor.tge_v2_ceny_dzis` | command_line | ceny dziś + atrybuty (`fixing_i_prices`, `plan`, …) |
| `sensor.tge_v2_ceny_jutro` | command_line | ceny jutro |
| `sensor.tge_v2_reguly` | template | progi, marginesy, ile godzin — **jedyne miejsce do edycji** |
| `sensor.tge_v2_aktualna_cena` | template | cena bieżącej godziny (z marginesem) |
| `binary_sensor.tge_v2_najtansze_5h` | template | czy teraz jest okno ładowania |
| `binary_sensor.tge_v2_najtansze_5h_jutro` | template | okno ładowania na jutro |
| `input_number.tge_v2_ladowane_godziny` | input_number | licznik godzin ładowania (doda go automatyzacja) |

---

## 3. Automatyzacje

**`tge_v2_charging_car`** — steruje przełącznikiem:

* **ON**: jesteśmy w oknie najtańszych godzin **lub** cena spadła poniżej
  progu `charge_below` (histereza),
* **OFF**: wyszliśmy z okna **i** cena jest wysoka (powyżej `stop_above`),
* gdy cena jest nieznana (`unknown`/`unavailable`) → **nic nie robi**,
  przełącznik zostaje, jaki jest. Chwilowy brak danych (restart HA, błąd
  odczytu pliku) nie przerywa ładowania,
* decyzja zapada **10 s po wyzwalaczu** (`mode: restart` + `delay`): o pełnej
  godzinie cena, okno i licznik zmieniają się w tej samej sekundzie, a kolejność
  nie jest gwarantowana,
* każde włączenie i wyłączenie zostawia wpis w Dzienniku („Ładowanie auta
  (TGE)”) z powodem: stan okna, cena, próg, wyzwalacz.

**`tge_v2_charging_watchdog`** — gdy `sensor.tge_v2_aktualna_cena` jest
`unavailable` nieprzerwanie przez 2 godziny, wyłącza przełącznik.

**`tge_v2_charging_counter`** — co godzinę zwiększa licznik, gdy przełącznik jest
włączony; o 00:00 zeruje go. Licznik służy do odbudowy okna po awarii.

### Skąd HA bierze ceny

Szablony wybierają plik po dacie: `sensor.tge_v2_ceny_dzis`, jeśli jego `day` to
dzisiaj, w przeciwnym razie `sensor.tge_v2_ceny_jutro`, jeśli jego `day` to
dzisiaj (tak jest po północy, zanim `today.json` się odświeży), inaczej brak
danych. Pliki odczytywane są co 60 s.

Porównanie dat wymaga, żeby **strefa czasowa dodatku** (opcja `timezone`,
domyślnie `Europe/Warsaw`) była taka sama jak strefa HA. Przy rozjeździe cena
będzie `unavailable` wokół północy, a po 2 godzinach strażnik wyłączy ładowanie.

### Co zmienić w automatyzacjach

`switch.0xb40ecfd05e500000` to **Twój** przełącznik ładowania — podmień
entity_id we wszystkich trzech automatyzacjach (w tym w `logbook.log`).

Po wklejeniu zmian w `tgerdn_v2.yaml` (`command_line`) **zrestartuj HA**;
same automatyzacje wystarczy przeładować.

---

## 4. Reguły (jedno miejsce do edycji)

`sensor.tge_v2_reguly` w `tgerdn_v2.yaml` (zmieniaj w generatorze):

```yaml
charging_hours: 5      # godzin ładowania dziennie
charge_below: 0.4      # włącz gdy cena <= tego (spot + margines, netto)
stop_above: 0.5        # wyłącz gdy cena >= tego
max_charge_price: 0    # twardy limit ceny (0 = wyłączony)
window_margin: 0.0993  # opłaty zmienne netto, strefa nocna G12 (Energa 2026)
day_margin: 0.3276     # opłaty zmienne netto, strefa dzienna G12 (Energa 2026)
window_hours: [0, 1, 2, 3, 4, 5, 13, 14, 22, 23]
```

Te same wartości muszą być ustawione w scraperze (zmienne `TGERDN_*`),
bo to Python liczy plan, a HA tylko go odtwarza.

---

## 5. Karty

`lovelace_v2.yaml` zawiera dwa widoki:

* **Kompas Energetyczny** — siatka 24 godzin na dziś i jutro (kolor = cena
  z marginesem), wskaźnik ceny bieżącej, **plan ładowania na dziś i na jutro** (okna z godzinami, średnia cena
  okna, oszczędność, ile godzin już naładowane, pasek 24 h) i wskaźniki poboru prądu.
* **Ceny Energii** — dwa wykresy apexcharts (dziś / jutro).

Osobny `lovelace_v2_auto.yaml` to dwie sekcje (dziś i jutro obok siebie) z
oknami i paskiem 24 h, do wklejenia nad kartę auta we własnym widoku.

Makro `price_cell` jest zdefiniowane dwa razy (raz na kartę) — Lovelace nie
pozwala dzielić makr między kartami.

Siatka, wykresy i wskaźnik pokazują cenę z marginesem (`total`,
`total_pln`), netto. Progi kolorów: **< 0,50** ciemnozielony (taniej niż
`stop_above`, ładowanie), **0,50–0,80** jasnozielony, **0,80–1,20** żółty,
**≥ 1,20** czerwony. Na cenach z 2026-08..10 to ok. 12% / 35% / 38% / 15%
godzin (mediana 0,82). Progi są w czterech miejscach: dwa makra
`price_cell`, `colors.ranges` obu wykresów i `severity` wskaźnika. Jeśli
wolisz sam kurs Fixing I, zamień w `data_generator` `p.total_pln` na
`p.rce_pln`.

---

## 6. Przejście z v1

Encje v2 mają prefiks `tge_v2_` i własne `unique_id` — **nie przejmują**
`entity_id` ani historii encji v1. Klucze w plikach JSON zostały zachowane
(`fixing_i_prices[].hour`, `.fixing_i_price_pln_kwh`, `prices[].dtime`,
`.rce_pln`, `data_points`, `data_fetched`), więc własne karty da się
przepiąć, zmieniając tylko `entity_id`.

| Element v1 | Odpowiednik w v2 |
|---|---|
| `sensor.tge_rdn_cena_dzis` / `_jutro` | `sensor.tge_v2_ceny_dzis` / `_jutro` |
| `sensor.tge_rdn_aktualna_cena` | `sensor.tge_v2_aktualna_cena` (+ atrybuty z planem) |
| `binary_sensor.tge_najtansze_5h` | `binary_sensor.tge_v2_najtansze_5h` |
| `sensor.tge_biezaca_cena_godzinowa` | **usuń** (duplikat) |
| `tgerdn_prices.json`, `tgerdn_prices_tomorrow.json` | `today.json`, `tomorrow.json` |
| `tge_rdn_scraper/config.yaml` | opcje dodatku / `sensor.tge_v2_reguly` |

Sprzątanie konfiguracji v1 krok po kroku: [`MIGRACJA.md`](../../MIGRACJA.md).

---

## 7. Troubleshooting

**Karta „Jutro” pokazuje „Brak danych”** — normalne przed 12:01: TGE publikuje
godzinowe Fixing I od 10:30, a dodatek pobiera ceny na jutro o 12:01 (po
porażce ponawia). Jeśli po 12:05 nadal brak danych, sprawdź log dodatku
i `python3 -m tgerdn doctor`.

**Gniazdko nie reaguje o pełnej godzinie** — to normalne opóźnienie 10 s.
Powód każdego przełączenia jest w Dzienniku (wpis „Ładowanie auta (TGE)”).

**`binary_sensor` ciągle `off`** — brakuje atrybutu `fixing_i_prices` albo
`plan` w `json_attributes` sensora `command_line`. Sprawdź:

```bash
cat /config/tgerdn/today.json | python3 -m json.tool | head -40
```

**Cena pokazuje `unavailable`** — plik JSON nie istnieje, jest pusty albo
`data_fetched` = false (TGE nie opublikował jeszcze tej doby).

**Przełącznik nie włącza się** — sprawdź encję `sensor.tge_v2_reguly`
i to, czy `sensor.tge_v2_aktualna_cena` pokazuje liczbę, a nie `unavailable`.
