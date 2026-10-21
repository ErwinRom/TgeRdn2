#!/usr/bin/env python3
"""Generuje pliki konfiguracyjne HA w repo z poprawnym formatem HA.

Format jest inny dla pliku glownego i dla pakietu (`packages/`):
  command_line:  lista wpisow, kazdy {platform: POJEDYNCZY dict}
  template:      lista platform, kazda {platform: LISTA encji}
  input_number:  plik glowny - lista; pakiet - slownik

Jeden generator, dwa warianty -> nie da sie rozsynchronizowac.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HA = REPO / 'tgerdn' / 'homeassistant'

HEADER = """# =============================================================================
#  TGE RDN v2 - {title}
# =============================================================================
#
#  {intro}
#
#  Wymagania wstępne:
#    1. Pliki JSON w /config/tgerdn/ - robi je dodatek "TGE RDN" (v2).
#    2. Automatyzacje z tgerdn{automation_suffix}_automation.yaml.
# =============================================================================
"""

COMMAND_LINE = """
command_line:
  - sensor:
      name: "{name_dzis}"
      unique_id: {uid_dzis}
      command: "cat /config/tgerdn/today.json"
      value_template: "{{{{ value_json.data_points if value_json.data_fetched else 'unknown' }}}}"
      scan_interval: 300
      json_attributes:
        - fixing_i_prices
        - prices
        - plan
        - tariff
        - stats
        - day
        - fetched_at
        - data_fetched
        - data_points
        - unit_of_measurement
        - friendly_name

  - sensor:
      name: "{name_jutro}"
      unique_id: {uid_jutro}
      command: "cat /config/tgerdn/tomorrow.json"
      value_template: "{{{{ value_json.data_points if value_json.data_fetched else 'unknown' }}}}"
      scan_interval: 300
      json_attributes:
        - fixing_i_prices
        - prices
        - plan
        - tariff
        - stats
        - day
        - fetched_at
        - data_fetched
        - data_points
        - unit_of_measurement
        - friendly_name
"""

INPUT_NUMBER = """
input_number:
{input_number_body}
"""

TEMPLATE = """
template:
  - sensor:
      # ---------------------------------------------------------------------
      # 1. Reguly - JEDNO miejsce na progi i marginesy.
      #    Zmiana taryfy to jedna edycja tego bloku.
      # ---------------------------------------------------------------------
      - name: "{name_reguly}"
        unique_id: {uid_reguly}
        state: "ok"
        attributes:
          charging_hours: 5
          charge_below: 0.2
          stop_above: 0.4
          max_charge_price: 0
          window_margin: 0.05
          day_margin: 0.28
          window_hours: [0, 1, 2, 3, 4, 5, 13, 14, 22, 23]

      # ---------------------------------------------------------------------
      # 2. Aktualna cena godziny + statystyki dnia.
      #    "total" z JSON-a to cena z marginesem dostawy (taka, ktora realnie
      #    placisz).
      # ---------------------------------------------------------------------
      - name: "{name_cena}"
        unique_id: {uid_cena}
        unit_of_measurement: "PLN/kWh"
        state_class: measurement
        state: >
          {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
          {{%- set cur = now().hour + 1 -%}}
          {{%- set p = (prices | selectattr('hour', 'equalto', cur) | list) -%}}
          {{%- set p = p[0] if p else none -%}}
          {{{{- p.total if p is not none else 'unavailable' -}}}}
        attributes:
          spot: >
            {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
            {{%- set cur = now().hour + 1 -%}}
            {{%- set p = (prices | selectattr('hour', 'equalto', cur) | list) -%}}
            {{%- set p = p[0] if p else none -%}}
            {{{{- p.fixing_i_price_pln_kwh if p is not none else 'unavailable' -}}}}
          margin: >
            {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
            {{%- set cur = now().hour + 1 -%}}
            {{%- set p = (prices | selectattr('hour', 'equalto', cur) | list) -%}}
            {{%- set p = p[0] if p else none -%}}
            {{{{- p.margin if p is not none else 'unavailable' -}}}}
          day: >
            {{{{- state_attr('sensor.{eid_dzis}', 'day') or 'unknown' -}}}}
          cheapest_price: >
            {{{{- (state_attr('sensor.{eid_dzis}', 'plan') or {{}}).get('cheapest_price', 'unavailable') -}}}}
          dearest_price: >
            {{{{- (state_attr('sensor.{eid_dzis}', 'plan') or {{}}).get('dearest_price', 'unavailable') -}}}}
          day_avg: >
            {{{{- (state_attr('sensor.{eid_dzis}', 'plan') or {{}}).get('day_avg', 'unavailable') -}}}}
          plan_hours_count: >
            {{{{- (state_attr('sensor.{eid_dzis}', 'plan') or {{}}).get('count', 0) -}}}}

      # ---------------------------------------------------------------------
      # 3. Cena jutra w biezacej godzinie (do porownania z dzisiejsza).
      # ---------------------------------------------------------------------
      - name: "{name_cena_jutro}"
        unique_id: {uid_cena_jutro}
        unit_of_measurement: "PLN/kWh"
        state_class: measurement
        state: >
          {{%- set prices = state_attr('sensor.{eid_jutro}', 'fixing_i_prices') or [] -%}}
          {{%- set cur = now().hour + 1 -%}}
          {{%- set p = (prices | selectattr('hour', 'equalto', cur) | list) -%}}
          {{%- set p = p[0] if p else none -%}}
          {{{{- p.total if p is not none else 'unavailable' -}}}}

  - binary_sensor:
      # ---------------------------------------------------------------------
      # 4. Czy teraz jestesmy w oknie najtańszych godzin?
      #
      #    Okno = N najtańszych godzin CALEGO dnia (liczy Python, plan jest
      #    stabilny przez dobe, wiec przelacznik nie skacze).
      #
      #    Odbudowa: jesli HA byl wylaczony w czescci okna, godziny te
      #    przepadaja. Wtedy doklejamy najtansze godziny, ktore jeszcze
      #    zostaly w ciagu dnia - dzieki temu dobowy limit N jest dotrzymany.
      # ---------------------------------------------------------------------
      - name: "{name_okno}"
        unique_id: {uid_okno}
        device_class: power
        state: >
          {{%- set rules = state_attr('sensor.{eid_reguly}', 'charging_hours') | int(5) -%}}
          {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
          {{%- set plan = state_attr('sensor.{eid_dzis}', 'plan') or {{}} -%}}
          {{%- set plan_hours = plan.get('hours', []) if plan is mapping else [] -%}}
          {{%- set cur = now().hour + 1 -%}}
          {{%- set future = prices | selectattr('hour', 'ge', cur) | list | sort(attribute='total') -%}}
          {{%- set plan_future = future | selectattr('hour', 'in', plan_hours) | list -%}}
          {{%- set charged = states('input_number.{eid_licznik}') | float(0) | round(0) | int -%}}
          {{%- set missing = [rules - charged - (plan_future | length), 0] | max -%}}
          {{%- set extras = (future | rejectattr('hour', 'in', plan_hours) | list)[:missing] | map(attribute='hour') | list -%}}
          {{%- set window = plan_hours + extras -%}}
          {{{{- cur in window -}}}}
        attributes:
          charged_hours: >
            {{{{- states('input_number.{eid_licznik}') | float(0) | round(2) -}}}}
          window_hours: >
            {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
            {{%- set plan = state_attr('sensor.{eid_dzis}', 'plan') or {{}} -%}}
            {{%- set plan_hours = plan.get('hours', []) if plan is mapping else [] -%}}
            {{%- set cur = now().hour + 1 -%}}
            {{%- set future = prices | selectattr('hour', 'ge', cur) | list | sort(attribute='total') -%}}
            {{%- set plan_future = future | selectattr('hour', 'in', plan_hours) | list -%}}
            {{%- set charged = states('input_number.{eid_licznik}') | float(0) | round(0) | int -%}}
            {{%- set missing = [state_attr('sensor.{eid_reguly}', 'charging_hours') | int(5) - charged - (plan_future | length), 0] | max -%}}
            {{%- set extras = (future | rejectattr('hour', 'in', plan_hours) | list)[:missing] | map(attribute='hour') | list -%}}
            {{{{- (plan_hours + extras) | join(',') -}}}}
          missing_hours: >
            {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
            {{%- set plan = state_attr('sensor.{eid_dzis}', 'plan') or {{}} -%}}
            {{%- set plan_hours = plan.get('hours', []) if plan is mapping else [] -%}}
            {{%- set cur = now().hour + 1 -%}}
            {{%- set future = prices | selectattr('hour', 'ge', cur) | list | sort(attribute='total') -%}}
            {{%- set plan_future = future | selectattr('hour', 'in', plan_hours) | list -%}}
            {{%- set charged = states('input_number.{eid_licznik}') | float(0) | round(0) | int -%}}
            {{{{- [state_attr('sensor.{eid_reguly}', 'charging_hours') | int(5) - charged - (plan_future | length), 0] | max -}}}}
          window_count: >
            {{%- set prices = state_attr('sensor.{eid_dzis}', 'fixing_i_prices') or [] -%}}
            {{%- set plan = state_attr('sensor.{eid_dzis}', 'plan') or {{}} -%}}
            {{%- set plan_hours = plan.get('hours', []) if plan is mapping else [] -%}}
            {{%- set cur = now().hour + 1 -%}}
            {{%- set future = prices | selectattr('hour', 'ge', cur) | list | sort(attribute='total') -%}}
            {{%- set plan_future = future | selectattr('hour', 'in', plan_hours) | list -%}}
            {{%- set charged = states('input_number.{eid_licznik}') | float(0) | round(0) | int -%}}
            {{%- set missing = [state_attr('sensor.{eid_reguly}', 'charging_hours') | int(5) - charged - (plan_future | length), 0] | max -%}}
            {{%- set extras = (future | rejectattr('hour', 'in', plan_hours) | list)[:missing] | map(attribute='hour') | list -%}}
            {{{{- (plan_hours + extras) | length -}}}}

      # ---------------------------------------------------------------------
      # 5. To samo dla jutra - plan na kolejna dobe.
      #    Bez odbudowy: jutro mozemy planowac dokladnie.
      # ---------------------------------------------------------------------
      - name: "{name_okno_jutro}"
        unique_id: {uid_okno_jutro}
        device_class: power
        state: >
          {{%- set plan = state_attr('sensor.{eid_jutro}', 'plan') or {{}} -%}}
          {{%- set plan_hours = plan.get('hours', []) if plan is mapping else [] -%}}
          {{%- set cur = now().hour + 1 -%}}
          {{{{- cur in plan_hours -}}}}
"""

VARIANTS = {
    'configuration.yaml': {
        'title': 'encje dla Home Assistant',
        'intro': ('Wklej do configuration.yaml (albo, jesli uzywasz pakietow,\n'
                  '#  do /config/packages/tgerdn.yaml - wtedy encje wczytaja sie\n'
                  '#  automatycznie przez "packages: !include_dir_named packages").'),
        'automation_suffix': '_',
        'names': {
            'dzis': 'TGE RDN Cena dzis', 'jutro': 'TGE RDN Cena jutro',
            'reguly': 'TGE RDN Reguly', 'cena': 'TGE RDN Aktualna cena',
            'cena_jutro': 'TGE RDN Aktualna Cena Jutro',
            'okno': 'TGE najtansze 5h', 'okno_jutro': 'TGE najtansze 5h jutro',
        },
        'uids': {
            'dzis': 'tgerdn_cena_dzis', 'jutro': 'tgerdn_cena_jutro',
            'reguly': 'tgerdn_reguly', 'cena': 'tgerdn_aktualna_cena',
            'cena_jutro': 'tgerdn_aktualna_cena_jutro',
            'okno': 'tge_cheapest_5h_window', 'okno_jutro': 'tge_najtansze_5h_jutro',
            'licznik': 'tgerdn_ladowane_godziny',
        },
        'eids': {
            'dzis': 'tge_rdn_cena_dzis', 'jutro': 'tge_rdn_cena_jutro',
            'reguly': 'tge_rdn_reguly', 'licznik': 'tge_ladowane_godziny',
        },
        'input_number': 'list',
    },
    'tgerdn_v2.yaml': {
        'title': 'encje v2 - wariant równoległy',
        'intro': ('Do katalogu /config/packages/ - encje maja prefiks tge_v2_, wiec\n'
                  '#  dzialaja obok starej konfiguracji (bez kolizji unique_id).\n'
                  '#  W tym wariancie input_number jest slownikiem - w pakiecie\n'
                  '#  lista jest odrzucana przez HA.'),
        'automation_suffix': '_v2_',
        'names': {
            'dzis': 'TGE v2 Ceny dzis', 'jutro': 'TGE v2 Ceny jutro',
            'reguly': 'TGE v2 Reguly', 'cena': 'TGE v2 Aktualna cena',
            'cena_jutro': 'TGE v2 Aktualna cena jutro',
            'okno': 'TGE v2 najtansze 5h', 'okno_jutro': 'TGE v2 najtansze 5h jutro',
        },
        'uids': {
            'dzis': 'tgerdn_v2_ceny_dzis', 'jutro': 'tgerdn_v2_ceny_jutro',
            'reguly': 'tgerdn_v2_reguly', 'cena': 'tgerdn_v2_aktualna_cena',
            'cena_jutro': 'tgerdn_v2_aktualna_cena_jutro',
            'okno': 'tgerdn_v2_najtansze_5h', 'okno_jutro': 'tgerdn_v2_najtansze_5h_jutro',
            'licznik': 'tgerdn_v2_ladowane_godziny',
        },
        'eids': {
            'dzis': 'tge_v2_ceny_dzis', 'jutro': 'tge_v2_ceny_jutro',
            'reguly': 'tge_v2_reguly', 'licznik': 'tge_v2_ladowane_godziny',
        },
        'input_number': 'dict',
    },
}

IN_NUMBER_CONF = """    name: TGE v2 Ladowane godziny
    min: 0
    max: 24
    step: 1
    unit_of_measurement: "h"
    mode: box
    icon: mdi:timer-sand"""

IN_NUMBER_CONF_CANON = """      name: TGE Ladowane godziny
      min: 0
      max: 24
      step: 1
      unit_of_measurement: "h"
      mode: box
      icon: mdi:timer-sand"""


def build(variant):
    v = VARIANTS[variant]
    fields = {}
    for key, value in v['names'].items():
        fields[f'name_{key}'] = value
    for key, value in v['uids'].items():
        fields[f'uid_{key}'] = value
    for key, value in v['eids'].items():
        fields[f'eid_{key}'] = value

    if v['input_number'] == 'list':
        body = '  - tgerdn_ladowane_godziny:\n' + IN_NUMBER_CONF_CANON
    else:
        body = '  tgerdn_v2_ladowane_godziny:\n' + IN_NUMBER_CONF

    text = HEADER.format(**v)
    text += COMMAND_LINE.format(**fields)
    text += INPUT_NUMBER.format(input_number_body=body)
    text += TEMPLATE.format(**fields)
    return text


for variant in VARIANTS:
    path = HA / variant
    path.write_text(build(variant), encoding='utf-8')
    print(f'zapisano: {variant}')
