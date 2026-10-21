# TGE RDN — dodatek Home Assistant: ceny energii i plan ładowania auta

Pobiera ceny Fixing I z giełdy TGE (Towarowa Giełda Energii) i wystawia je
w Home Assistant tak, żeby **auto ładowało się w najtańszych godzinach doby —
zawsze co najmniej 5 godzin**, niezależnie od poziomu cen.

Projekt od zera, w formie **dodatku HA (Docker)** — działa w kontenerze
dodatku, nic nie jest instalowane na hoście, nie ma crona ani systemda.

```
TgeRdn2/                      # = katalog dodatku HA
├── config.yaml               # opcje dodatku (godziny, katalog, ile godzin)
├── Dockerfile                # obraz: python:3.13-slim, zero zależności
├── run.sh                    # entrypoint: opcje → tgerdn serve
├── repository.yaml           # metadane sklepu dodatków
├── icon.png / logo.png       # ikony dodatku
├── tgerdn/                   # kod (8 modułów, tylko biblioteka standardowa)
│   └── homeassistant/        # pliki konfiguracyjne HA do wklejenia
└── tests/                    # 79 testów, w tym renderowanie szablonów HA
```

---

## Co potrafi (i czego v1 nie potrafił)

| | v1 (TgeRdn) | v2 (ten projekt) |
|---|---|---|
| Zależności produkcyjne | aiohttp, beautifulsoup4, schedule | **żadne** (urllib + html.parser) |
| Plan ładowania | liczony w Jinja w HA | **liczony w Pythonie**, raz na dobę |
| Gwarancja 5 h po awarii HA | brak (godziny przepadały) | **odbudowa okna** z najtańszych wolnych godzin |
| Plan na jutro | brak | tak (`binary_sensor.tge_najtansze_5h_jutro`) |
| Koszt ładowania / oszczędność | brak | w JSON-ie i na karcie |
| Zapis pliku | zwykły `open()` | **atomowy** (tmp + `os.replace`) |
| Harmonogram | własny scheduler w tle | wbudowany w `tgerdn serve` (nadal bez crona) |
| Testy | 65 | 79 (+ rendering szablonów i symulacja doby) |
| Generator YAML | usunięty, ale struktura plików rozrosła się | jeden pakiet, jeden format wyjściowy |

---

## Instalacja w Home Assistant

### 1. Dodatek

**Ustawienia → Dodatki → Sklep dodatków → ⋮ → Dodatki z własnego URL**
→ podaj adres repozytorium (np. `https://github.com/ErwinRom/TgeRdn2`)
→ zainstaluj i uruchom.

Albo skopiuj katalog do `/addons/tgerdn/` na maszynie z HA i dodaj go
ręcznie.

### 2. Opcje dodatku

| Opcja | Domyślnie | Znaczenie |
|---|---|---|
| `output_dir` | `/config/tgerdn` | katalog na pliki JSON (musi być w `/config`) |
| `hour` | `00:01,12:01` | godziny pobierania cen |
| `charging_hours` | `5` | godzin ładowania w najtańszym oknie |
| `timezone` | `Europe/Warsaw` | strefa czasowa harmonogramu |

Dodatek zapisuje dwa pliki, które czyta Home Assistant:

```
/config/tgerdn/today.json      → sensor.tge_rdn_cena_dzis
/config/tgerdn/tomorrow.json   → sensor.tge_rdn_cena_jutro
```

### 3. Pliki konfiguracyjne HA

Wklej w swoim Home Assistant (z katalogu `tgerdn/homeassistant/`):

| Plik | Gdzie wkleić |
|---|---|
| `configuration.yaml` | katalog `packages/` — encje + szablony (patrz niżej) |
| `automation.yaml` | `automation.yaml` (główny) — ładowanie auta + licznik |
| `lovelace.yaml` | dashboard (nowy widok) |

**Encje w katalogu `packages/`.** Jeśli używasz pakietów HA:

```yaml
# configuration.yaml
packages: !include_dir_named packages
```

to plik `configuration.yaml` z tego katalogu wrzuć do `/config/packages/`
(np. `/config/packages/tgerdn.yaml`). Każdy plik w tym katalogu jest
wczytywany jako osobny pakiet — nie trzeba dopisywać `!include` do
`configuration.yaml`.

`automation:` **nie może** żyć w pakiecie (HA tego nie dopuszcza).

Automatyzacje dodajesz do swojego pliku `automations.yaml` **wklejając je
na końcu jako kolejne elementy listy** (kolumna 0, na tym samym poziomie
co `- id:`):

```yaml
# /config/automations.yaml
- id: '1791711498340'
  alias: Twoja dotychczasowa automatyzacja
  ...

# --- ponizej wklej zawartosc tgerdn_v2_automation.yaml ---
- id: tge_v2_charging_car
  ...
```

> ⚠️ **Nie używaj `!include` wewnątrz listy.** `!include` w miejscu elementu
> listy jest błędny składniowo (HA odrzuci cały plik z błędem
> „could not find expected ':'"). `!include` działa tylko jako **jedyna**
> zawartość pliku albo jako wartość klucza:
>
> ```yaml
> # tak NIE dziala
> - id: 'moja_automatyzacja'
> !include tgerdn_v2_automation.yaml
>
> # tak dziala - osobny katalog
> automation: !include_dir_list automations/
> ```
>
> Jeśli wolisz osobne pliki: przenieś `automations.yaml` do
> `/config/automations/` i w `configuration.yaml` użyj
> `automation: !include_dir_list automations/`.

W `configuration.yaml` popraw tylko dwie rzeczy:

* ścieżkę w `command:` (`/config/tgerdn/today.json` — domyślnie poprawna),
* `entity_id` przelącznika w `automation.yaml` (domyślnie
  `switch.0xb40ecfd05e500000` — Twój z v1).

Szczegóły: [`tgerdn/homeassistant/README.md`](tgerdn/homeassistant/README.md).

---

## Jak to działa

```
   dodatek HA (kontener)
        │
        ├─ tgerdn serve ──► tge.pl ──► today.json / tomorrow.json
        │                                    │
        │                        command_line│  sensor.tge_rdn_cena_dzis
        │                                    │  sensor.tge_rdn_cena_jutro
        │                                    ▼
        │                    sensor.tge_rdn_aktualna_cena
        │                    binary_sensor.tge_najtansze_5h
        │                                    │
        └────────────────────────────────────▼
                                    automatyzacja → switch.0xb40ecfd...
```

**Ceny na dobę `D` są publikowane przez TGE na stronie z datą `D-1`.**
Dlatego pobieramy dwie strony: wczorajszą (dziś) i dzisiejszą (jutro).
Ceny na jutro pojawiają się ok. 12:00 — do tego czasu `tomorrow.json`
jest pusty, a karta „Jutro” pokazuje „Brak danych”.

### Konwencja godzin

TGE używa doby handlowej `H01..H24`, gdzie `H01` = 00:00–01:00.
W całym projekcie `hour` = 1..24, a godzina zegara to `hour - 1`.
W JSON-ie każdy wpis ma też `period` (`"00:00-01:00"`), więc nic nie jest
zagadkowe.

---

## Gwarancja: co najmniej 5 godzin ładowania dziennie

Okno to **5 najtańszych godzin całego dnia** (po cenie z marginesem dostawy).
Dzięki temu:

* przełącznik nie skacze między godzinami — okno jest stabilne przez dobę,
* dobowy limit jest dotrzymany niezależnie od poziomu cen (nawet w dobie,
  gdy wszystko kosztuje ponad 1 PLN/kWh).

**Odbudowa po awarii.** Jeśli Home Assistant był wyłączony w najtańszych
godzinach, te godziny przepadają. Licznik `input_number.tge_ladowane_godziny`
pamięta, ile godzin faktycznie się naładowało, a okno dokleja wtedy
**najtańsze z pozostałych godzin doby** — limit 5 h zostaje dotrzymany, a cena
pozostaje najniższa z dostępnych.

```
scenariusz                       godziny ładowania        wynik
zwykły dzień                     02-04, 13-14             5 h  OK
cały dzień > 1 PLN/kWh          02-04, 13-14             5 h  OK
tani dzień (histereza)           02-05, 13-16             8 h  OK
HA padło 02:00-04:00             13-15, 23-24             5 h  OK  (odbudowa)
HA padło 03:00-05:00             02-05, 13-14             6 h  OK  (1 h nadmiaru)
```

Ostatni wiersz to świadome ograniczenie: przełącznik to fizyczne relé —
gdy HA pada, przełącznik **zostaje włączony**. Jedna godzina nadmiaru jest
ceną za to, że nic nie steruje nim w trakcie awarii.

Symulacja (`tgerdn simulate`) renderuje **prawdziwe pliki z
`tgerdn/homeassistant/`**, więc to nie jest opis, tylko test.

---

## Użycie poza dodatkiem (opcjonalnie)

Kod nie wymaga instalacji — wystarczy Python 3.11+:

```bash
cd TgeRdn2

python3 -m tgerdn fetch      # pobierz ceny i zapisz pliki
python3 -m tgerdn show       # wypisz plan ładowania
python3 -m tgerdn doctor     # diagnostyka
python3 -m tgerdn simulate   # symulacja doby (prawdziwe szablony HA)
python3 -m tgerdn serve      # tryb ciągły (jak w dodatku)
```

Testy potrzebują dodatkowo `pytest`, `jinja2`, `pyyaml`:

```bash
python3 -m pytest tests/ -q
```

---

## Konfiguracja

W dodatku: opcje w UI (`config.yaml`). Poza dodatkiem: zmienne środowiskowe.

| Zmienna | Domyślnie | Znaczenie |
|---|---|---|
| `TGERDN_OUTPUT_DIR` | `~/.local/share/tgerdn` | katalog z plikami JSON |
| `TGERDN_CHARGING_HOURS` | `5` | godzin ładowania dziennie |
| `TGERDN_WINDOW_MARGIN` | `0.05` | margines dostawy w godzinach okienkowych |
| `TGERDN_DAY_MARGIN` | `0.28` | margines dostawy w godzinach dziennych |
| `TGERDN_WINDOW_HOURS` | `0,1,2,3,4,5,13,14,22,23` | godziny z taryfą okienkową |
| `TGERDN_CHARGE_BELOW` | `0.2` | włącz ładowanie poniżej progu |
| `TGERDN_STOP_ABOVE` | `0.4` | wyłącz ładowanie powyżej progu |
| `TGERDN_MAX_CHARGE_PRICE` | `0` | twardy limit ceny (0 = wyłączony) |
| `TGERDN_TIMEOUT` | `30` | timeout HTTP w sekundach |
| `TGERDN_RETRIES` | `3` | liczba prób pobrania |

Te same wartości muszą być w `sensor.tge_rdn_reguly` w Home Assistant —
progi histerezy i limit ceny są tam, żeby automatyzacja nie miała ich
zaszytych na sztywno.

---

## Format pliku JSON

```json
{
  "version": 2,
  "day": "2026-10-21",
  "fetched_at": "2026-10-21T00:01:03+02:00",
  "data_fetched": true,
  "data_points": 24,
  "unit": "PLN/kWh",
  "tariff": { "charging_hours": 5, "charge_below": 0.2, "stop_above": 0.4 },
  "fixing_i_prices": [
    { "data_dostawy": "2026-10-21", "hour": 1, "fixing_i_price_pln_kwh": 0.60177,
      "margin": 0.05, "total": 0.65177, "period": "00:00-01:00",
      "dtime": "2026-10-21T00:00:00" }
  ],
  "prices": [
    { "dtime": "2026-10-21T00:00:00", "period": "00:00-01:00",
      "rce_pln": 0.60177, "total_pln": 0.65177, "business_date": "2026-10-21" }
  ],
  "plan": {
    "hours": [3, 4, 5, 14, 15],
    "periods": ["02:00-03:00", "03:00-04:00", "04:00-05:00", "13:00-14:00", "14:00-15:00"],
    "count": 5, "cost_avg": 0.595446, "cost_worst": 1.046262, "saving": 0.450816,
    "cheapest_hour": 14, "cheapest_price": 0.49975,
    "dearest_hour": 8, "dearest_price": 1.13965, "day_avg": 0.806455
  },
  "stats": { "count": 24, "min": 0.49975, "max": 1.13965, "avg": 0.806455 }
}
```

`fixing_i_prices` zachowuje klucze z v1 (`hour`, `fixing_i_price_pln_kwh`),
więc **stare szablony i karty działają bez zmian**. Nowe pola to `margin`
(margines dostawy), `total` (cena razem z marginesem) i `period`.

---

## Ograniczenia (świadome)

* **Ceny na jutro** pojawiają się dopiero ok. 12:00 — do tego czasu
  `tomorrow.json` jest pusty, a karta „Jutro” pokazuje „Brak danych”.
* **Okno na jutro** (`binary_sensor.tge_najtansze_5h_jutro`) nie ma odbudowy —
  jutro można planować dokładnie.
* **HA w trakcie okna** = przełącznik zostaje włączony (relé fizyczne) →
  możliwa jedna godzina nadmiaru.
* **Marginesy dostawy** (0,05 / 0,28) są wpisane ręcznie — to Twoja taryfa
  okienkowa; popraw w opcjach dodatku i w `sensor.tge_rdn_reguly`.
* **Dodatek nie jest kompatybilny z v1** — inne `entity_id` plików
  (`today.json` / `tomorrow.json`) i brak sensora `tge_biezaca_cena_godzinowa`.
  Stare karty działają, bo klucze w JSON-ie zostały zachowane.
# TgeRdn2
# TgeRdn2
# TgeRdn2
