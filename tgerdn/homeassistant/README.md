# Konfiguracja Home Assistant — TGE RDN v2

Pliki leżą w katalogu `tgerdn/homeassistant/` (w repo: `TgeRdn2/tgerdn/homeassistant/`).
Trzy pliki do wklejenia, w kolejności:

| Plik | Co wkleić | Gdzie |
|---|---|---|
| `configuration.yaml` | encje `command_line`, `input_number`, szablony | `configuration.yaml` (główny) |
| `automation.yaml` | ładowanie auta + licznik godzin | `automation.yaml` (główny) |
| `lovelace.yaml` | karty | dashboard (widok) |

---

## 1. Pliki JSON

Scraper zapisuje dwa pliki:

| Plik | Zawartość | Sensor |
|---|---|---|
| `today.json` | ceny na dziś + plan | `sensor.tge_rdn_cena_dzis` |
| `tomorrow.json` | ceny na jutro + plan | `sensor.tge_rdn_cena_jutro` |

Domyślna ścieżka w przykładzie: `/config/tgerdn/` (katalog `config` w
kontenerze HA). Jeśli HA nie jest w kontenerze, zmień `command:` na
np. `cat /home/erwin/.local/share/tgerdn/today.json`.

Ważne: `json_attributes` **musi** zawierać `fixing_i_prices` i `plan` —
szablony czytają z nich ceny i okno ładowania.

---

## 2. Encje

| Encja | Typ | Rola |
|---|---|---|
| `sensor.tge_rdn_cena_dzis` | command_line | ceny dziś + atrybuty (`fixing_i_prices`, `plan`, …) |
| `sensor.tge_rdn_cena_jutro` | command_line | ceny jutro |
| `sensor.tge_rdn_reguly` | template | progi, marginesy, ile godzin — **jedyne miejsce do edycji** |
| `sensor.tge_rdn_aktualna_cena` | template | cena bieżącej godziny (z marginesem) |
| `binary_sensor.tge_najtansze_5h` | template | czy teraz jest okno ładowania |
| `binary_sensor.tge_najtansze_5h_jutro` | template | okno ładowania na jutro |
| `input_number.tge_ladowane_godziny` | input_number | licznik godzin ładowania (doda go automatyzacja) |

---

## 3. Automatyzacje

**`tge_charging_car`** — steruje przełącznikiem:

* **ON**: jesteśmy w oknie najtańszych godzin **lub** cena spadła poniżej
  progu `charge_below` (histereza),
* **OFF**: wyszliśmy z okna **i** cena jest wysoka (powyżej `stop_above`),
* gdy cena jest nieznana → poza oknem ładowanie jest **wyłączane** (nie palimy
  prądu w ciemno), wewnątrz okna zostaje włączone.

**`tge_charging_counter`** — co godzinę zwiększa licznik, gdy przełącznik jest
włączony; o 00:00 zeruje go. Licznik służy do odbudowy okna po awarii.

### Co zmienić w automatyzacji

`switch.0xb40ecfd05e500000` to **Twój** przełącznik ładowania — podmień
entity_id w obu automatyzacjach.

---

## 4. Reguły (jedno miejsce do edycji)

`Sensor tge_rdn_reguly` w `configuration.yaml`:

```yaml
charging_hours: 5      # godzin ładowania dziennie
charge_below: 0.2      # włącz gdy cena <= tego
stop_above: 0.4        # wyłącz gdy cena >= tego
max_charge_price: 0    # twardy limit ceny (0 = wyłączony)
window_margin: 0.05    # margines dostawy w godzinach okienkowych
day_margin: 0.28       # margines dostawy w godzinach dziennych
window_hours: [0, 1, 2, 3, 4, 5, 13, 14, 22, 23]
```

Te same wartości muszą być ustawione w scraperze (zmienne `TGERDN_*`),
bo to Python liczy plan, a HA tylko go odtwarza.

---

## 5. Karty

`lovelace.yaml` zawiera dwa widoki:

* **Kompas Energetyczny** — siatka 24 godzin na dziś i jutro (kolor = cena
  z marginesem), wskaźnik ceny bieżącej, **plan ładowania** (okno, koszt
  20 kWh, oszczędność, ile godzin już naładowane) i wskaźniki poboru prądu.
* **Ceny Energii** — dwa wykresy apexcharts (dziś / jutro).

Makro `price_cell` jest zdefiniowane dwa razy (raz na kartę) — Lovelace nie
pozwala dzielić makr między kartami.

Wykresy czytają `total_pln` (cena z marginesem). Jeśli wolisz sam kurs
Fixing I, zamień w `data_generator` `p.total_pln ?? p.rce_pln` na `p.rce_pln`.

---

## 6. Kompatybilność z v1

| Element v1 | Stan w v2 |
|---|---|
| `sensor.tge_rdn_cena_dzis` / `_jutro` | te same `entity_id` |
| `sensor.tge_rdn_aktualna_cena` | ten sam `entity_id` (+ atrybuty z planem) |
| `binary_sensor.tge_najtansze_5h` | ten sam `entity_id` |
| `fixing_i_prices[].hour` / `.fixing_i_price_pln_kwh` | bez zmian |
| `prices[].dtime` / `.period` / `.rce_pln` | bez zmian |
| `data_points`, `data_fetched`, `last_update`, `friendly_name` | bez zmian |
| `sensor.tge_biezaca_cena_godzinowa` | **usuń** (duplikat) |
| `tgerdn_prices.json`, `tgerdn_prices_tomorrow.json` | → `today.json`, `tomorrow.json` |
| `tge_rdn_scraper/config.yaml` | → zmienne środowiskowe / `sensor.tge_rdn_reguly` |

Jeśli masz w HA własny `sensor.tge_rdn_aktualna_cena` (template), usuń go —
w v2 tę nazwę przejmuje szablon z pliku `configuration.yaml`.

---

## 7. Troubleshooting

**Karta „Jutro” pokazuje „Brak danych”** — normalne przed 12:00; TGE
publikuje ceny na jutro około południa.

**`binary_sensor` ciągle `off`** — brakuje atrybutu `fixing_i_prices` albo
`plan` w `json_attributes` sensora `command_line`. Sprawdź:

```bash
cat /config/tgerdn/today.json | python3 -m json.tool | head -40
```

**Cena pokazuje `unavailable`** — plik JSON nie istnieje, jest pusty albo
`data_fetched` = false (TGE nie opublikował jeszcze tej doby).

**Przełącznik nie włącza się** — sprawdź encję `sensor.tge_rdn_reguly`
i to, czy `sensor.tge_rdn_aktualna_cena` pokazuje liczbę, a nie `unavailable`.
