# Changelog

Wersjonowanie: każda zmiana w repo podnosi `version` w `config.yaml`
i `io.hass.version` w `Dockerfile` (muszą być zgodne), a tutaj trafia
opis zmian. Supervisor HA porównuje `version` przy aktualizacji dodatku —
bez zmiany numeru HA nie pobierze nowej wersji.

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
