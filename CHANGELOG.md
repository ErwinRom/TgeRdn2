# Changelog

Wersjonowanie: każda zmiana w repo podnosi `version` w `config.yaml`
i `io.hass.version` w `Dockerfile` (muszą być zgodne), a tutaj trafia
opis zmian. Supervisor HA porównuje `version` przy aktualizacji dodatku —
bez zmiany numeru HA nie pobierze nowej wersji.

## 2.1.10

- **Marginesy z faktury (Energa, G12, 2026).** `window_margin` 0,05 -> 0,0993
  i `day_margin` 0,28 -> 0,3276 PLN/kWh netto. Margines to teraz wszystkie
  oplaty zmienne za kWh: skladnik zmienny stawki sieciowej (0,0558 noc /
  0,2841 dzien) + jakosciowa 0,0332 + OZE 0,0073 + kogeneracyjna 0,0030.
  Wczesniej brakowalo ~0,0435 PLN/kWh w obu strefach.
- **Progi ladowania dopasowane do realnych cen.** `charge_below` 0,2 -> 0,4,
  `stop_above` 0,4 -> 0,5 (cena spot + margines, netto). Przy nowych
  marginesach 0,2 wymagalby spotu <= 0,10 w nocy lub ujemnego w dzien, wiec
  praktycznie nie dzialal. Na cenach RCE z 2026-08-01..2026-10-22 okno 5 h
  kosztowalo srednio 0,44-0,58, mediana doby 0,78-0,85; 0,4/0,5 = dokladanie
  ladowania tylko taniej niz przecietne okno.
- **Kolory w Lovelace wg ceny z marginesem i progow z danych.** Siatka
  godzin i wykresy kolorowaly sam kurs spot (`fixing_i_price_pln_kwh`,
  `rce_pln`), choc README opisywalo cene z marginesem - teraz `total` /
  `total_pln`. Progi 0,45/0,75/1,00 -> 0,50/0,80/1,20 (12/35/38/15% godzin
  na cenach 2026-08..10), wskaznik: zolty od 0,8, czerwony od 1,2, max 2.
  Legenda opisuje przedzialy cen zamiast stanow Kompasu PSE, z ktorymi
  kolory nie mialy zwiazku.

## 2.1.9

- `MIGRACJA.md`: migracja zakonczona 2026-10-22. Dokument opisuje stan po
  sprzataniu (w HA dziala tylko v2) i przebieg sprzatania zamiast planu.
  Kod dodatku bez zmian.

## 2.1.8

- **Poprawiono automatyzacje `tge_v2_charging_car`.** Galaz wylaczajaca
  ladowanie byla w `default:` w ksztalcie galezi `choose`
  (`conditions` + `sequence`), a `default` to **lista akcji**. HA odrzucal
  cala automatyzacje: `not a valid option at 'actions[0].default[0].conditions'`
  - automatyzacja v2 nigdy nie dzialala, przelacznikiem sterowala tylko
  automatyzacja v1. Wylaczanie jest teraz druga galezia `choose` (warunki
  wlaczania i wylaczania wykluczaja sie - wymagaja przelacznika odpowiednio
  `off` i `on`, wiec dzialanie jest takie samo jak zamierzone).
- Symulator czyta warunek wylaczania z drugiej galezi `choose`.
- Nowy test `test_listy_akcji_zawieraja_akcje_nie_galezie` - zaden element
  listy akcji (`actions`, `sequence`, `default`, `then`, `else`) nie moze miec
  `conditions`. Test zweryfikowany: na poprzedniej wersji pliku pada.

## 2.1.7

- **Testy CLI nie zaleza od daty systemowej.** Fixture zawiera tylko dobe
  2026-10-21, a `fetch` liczy "dzis" z `date.today()` - od 2026-10-22 trzy
  testy padaly (`test_fetch_zapisuje_oba_pliki`,
  `test_fetch_zachowuje_plan_z_poprzedniego_zapisu`, `test_show_z_plikiem`).
  `tests/test_cli.py` zamraza teraz "dzis" na dobe z fixture. Kod dodatku bez
  zmian.
- `MIGRACJA.md`: krok 6 wymienia oba mozliwe helpery do usuniecia -
  `input_number.tge_v2_ladowane_godziny` (obecny) i
  `input_number.tgerdn_v2_ladowane_godziny` (sprzed poprawki sluga w 2.1.3).
- `MIGRACJA.md`: **docelowy jest wariant `tge_v2_`.** Plan sprzatania usuwa
  tylko konfiguracje v1, a pakiet, automatyzacje i widoki v2 zostaja.
- **Usunieto kanoniczne pliki HA** (`configuration.yaml`, `automation.yaml`,
  `lovelace.yaml`). Jedynym wariantem jest v2: `tgerdn_v2.yaml`,
  `tgerdn_v2_automation.yaml`, `lovelace_v2.yaml`. Encje i `unique_id` v2 bez
  zmian - zmienil sie tylko naglowek `tgerdn_v2.yaml`.
- Generator tworzy tylko `tgerdn_v2.yaml`. Naglowek wskazuje poprawna nazwe
  pliku automatyzacji (bylo `tgerdn_v2__automation.yaml`).
- Symulator (`tgerdn simulate`) i testy renderowania szablonow dzialaja na
  plikach i encjach v2 (`sensor.tge_v2_*`, `binary_sensor.tge_v2_*`,
  `input_number.tge_v2_ladowane_godziny`). Usunieto testy kolizji miedzy
  wariantami - 105 testow.
- README (glowne i `tgerdn/homeassistant/`) opisuja instalacje plikow v2.

## 2.1.6

- **Kanoniczny `lovelace.yaml` zawiera ulepszone widoki** - karte „Plan
  ladowania" (okno godzin, stan, naładowane godziny, najtańsza/najdroższa
  cena, średnia doby, oszczędność) oraz wykresy czytajace `dtime` z pliku
  JSON zamiast liczyc daty w JavaScript. Wskazuja na docelowe encje
  (`sensor.tge_rdn_*`), wiec po sprzataniu wariantow rownoleglych widoki
  dzialaja bez zmian.
- Warianty rownolegle (`tgerdn_v2.yaml`, `tgerdn_v2_automation.yaml`,
  `lovelace_v2.yaml`) zostaja w repo jako instrukcja migracji - encje maja
  prefiks `tge_v2_`, wiec dzialaja obok starej konfiguracji bez kolizji
  `unique_id`.

## 2.1.5

- **Poprawiono wartosci atrybutow encji `Reguly`.** W template sensorze
  kazda wartosc w `attributes:` musi byc **template'em** (stringiem) - lista
  albo liczba powoduja blad
  `template value should be a string for dictionary value 'sensor->0->attributes->window_hours'`.
  Wartosci `window_hours`, `charging_hours`, `charge_below`, `stop_above`,
  `max_charge_price`, `window_margin` i `day_margin` sa teraz templatami;
  renderowany JSON jest parsowany przez HA do listy/liczby.
- Testy kluczy sprawdzaja teraz takze **typy wartosci** atrybutow, nie tylko
  nazwy kluczy. Test zweryfikowany: po wstawieniu liczby zamiast template'a
  pada.

## 2.1.4

- **Poprawiono instrukcje instalacji automatyzacji.** `!include` w miejscu
  elementu listy YAML jest **bledny składniowo** - HA odrzuca wtedy caly plik
  `automations.yaml` bledem `could not find expected ':'`, a automatyzacje
  sa oznaczane jako nieaktywne ("konfiguracja zawiera bledy"). `!include`
  dziala tylko jako jedyna zawartosc pliku albo jako wartosc klucza
  (np. `automation: !include_dir_list automations/`). Automatyzacje z pliku
  `tgerdn_v2_automation.yaml` nalezy **wkleic na koncu** listy w
  `/config/automations.yaml`.
- Dodano `tests/test_ha_automation.py` - sprawdza strukture automatyzacji wobec
  schematu integracji `automation`: dozwolone klucze, `choose` i `default` jako
  rodzenstwa, listy w `conditions`/`sequence`/`triggers`, brak kolizji `id`
  miedzy wariantami i ten sam przelacznik w obu.

## 2.1.3

- **Poprawiono klucz sluga helpera `input_number`.** HA tworzy encje
  `input_number.<slug>` - a szablony i automatyzacja odwolywaly sie do
  `input_number.tge_v2_ladowane_godziny`, podczas gdy encja powstawala jako
  `input_number.tgerdn_v2_ladowane_godziny`. Blad byl cichy: `states()` zwraca
  `unknown`, a `| float(0)` zamienia to w zero, wiec licznik godzin ladowania
  nigdy sie nie inkrementowal, a odbudowa okna po awarii HA nie dzialala.
- Dodano `tests/test_ha_references.py` - sprawdza, czy **kazda** referencja
  w szablonach i automatyzacji wskazuje na encje, ktora faktycznie istnieje.
  Test zweryfikowany: po wprowadzeniu starego sluga pada na dwa asercje.

## 2.1.2

- **Usunieto `unique_id` z helpera `input_number`** - schema helpera nie zawiera
  tego klucza i HA odrzucal cala konfiguracje bledem
  `'unique_id' is an invalid option for 'input_number'`.
- Dodano `tests/test_ha_config_keys.py` - sprawdza **kazdy klucz** w plikach
  konfiguracyjnych wobec schematow HA (`command_line`, `input_number`,
  `template`). Klucze, ktore HA odrzuca, sa teraz wykrywane przez testy,
  a nie przez uzytkownika przy wklejaniu do HA.

## 2.1.1

- **Poprawiono format plikow konfiguracyjnych Home Assistant** - wersja 2.1.0
  wysyla pliki, ktorych HA nie przyjmowal:
  - `command_line`: platforma (`sensor:`) musi mapowac do **pojedynczego
    slownika**, nie do listy - inaczej blad
    `expected a mapping for dictionary value 'command_line->N->sensor'`,
  - `input_number`: w pliku glownym to lista, ale **w katalogu `packages/`
    musi byc slownikiem** - inaczej blad
    `integration 'input_number' cannot be merged, expected a dict`.
  Blad dotyczyl rowniez kanonicznego `configuration.yaml` w repo, nie tylko
  wariantu rownoleglego.
- Dodano generator `tools/generate_ha_config.py` - oba warianty plikow HA
  powstaja z jednego zrodla, wiec formaty nie moga sie rozjechac.
- Dodano testy `tests/test_ha_config_shape.py` kodujace reguly formatu pakietow
  HA (`command_line` jako lista dictow, `input_number` jako slownik w pakiecie,
  `template` jako lista, brak kolizji `unique_id` miedzy wariantami).

## 2.1.0

- Dodano gotową konfigurację Home Assistant w `tgerdn/homeassistant/`:
  encje, automatyzację ładowania i widoki dashboardu (`configuration.yaml`,
  `automation.yaml`, `lovelace.yaml`) — do wklejenia bez pisania od zera.
- Dodano warianty równoległe `tgerdn_v2.yaml`, `tgerdn_v2_automation.yaml`
  i `lovelace_v2.yaml`: encje z prefiksem `tge_v2_`, dzięki czemu stara i nowa
  konfiguracja mogą działać obok siebie (bez kolizji `unique_id`).
- Kanoniczny `configuration.yaml` używa teraz `unique_id` z poprzedniej wersji
  projektu (`tgerdn_cena_dzis`, `tge_cheapest_5h_window`, …), żeby przy
  migracji przejąć encje z rejestru wraz z historią.
- Automatyzacja zachowuje dotychczasowe `id: 1791711498340` — historia
  uruchomień zostaje ciągła.
- Widok „Kompas Energetyczny" dostał kartę **Plan ładowania**: okno godzin,
  stan ładowania, liczbę naładowanych godzin, najtańszą/najdroższą cenę,
  średnią doby i oszczędność w oknie.
- Poprawiono wykres „ceny jutro": daty były cofane o 25 godzin (dwie doby),
  przez co słupki wypadały poza zakres osi. Teraz oś jest przesunięta na
  jutro (`offset: '+1d'`), a daty brane są z pola `dtime`.
- Generator wykresu uproszczony z sześciu linii JavaScriptu do trzech —
  korzysta z atrybutu `prices` zamiast liczyć daty w przeglądarce.

## 2.0.0

- Pierwsza wersja 2.x: dodatek HA w kontenerze, zero zależności produkcyjnych
  (tylko biblioteka standardowa Pythona), plan ładowania liczony w Pythonie
  i zapisywany w pliku JSON, odbudowa okna po awarii HA z licznikiem godzin.
