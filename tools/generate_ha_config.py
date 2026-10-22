#!/usr/bin/env python3
"""Generuje pakiet HA `tgerdn_v2.yaml` z poprawnym formatem HA.

Format pakietu (`packages/`):
  command_line:  lista wpisow, kazdy {platform: POJEDYNCZY dict}
  template:      lista platform, kazda {platform: LISTA encji}
  input_number:  slownik (lista jest odrzucana przy laczeniu pakietow)
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
#    2. Automatyzacje z {automation_file}.
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
          # Kazda wartosc atrybutu template sensora musi byc SZTAKIEM
          # (template'em) - HA odrzuca listy i liczby jako "template value
          # should be a string". Renderowany JSON jest parsowany do listy.
          charging_hours: "{{{{ 5 }}}}"
          charge_below: "{{{{ 0.4 }}}}"
          stop_above: "{{{{ 0.5 }}}}"
          max_charge_price: "{{{{ 0 }}}}"
          window_margin: "{{{{ 0.0993 }}}}"
          day_margin: "{{{{ 0.3276 }}}}"
          window_hours: "{{{{ [0, 1, 2, 3, 4, 5, 13, 14, 22, 23] }}}}" 

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
    'tgerdn_v2.yaml': {
        'title': 'encje v2',
        'intro': ('Do katalogu /config/packages/ - encje maja prefiks tge_v2_.\n'
                  '#  input_number jest slownikiem - w pakiecie lista jest\n'
                  '#  odrzucana przez HA.'),
        'automation_file': 'tgerdn_v2_automation.yaml',
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
    },
}

IN_NUMBER_CONF = """    name: TGE v2 Ladowane godziny
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

    body = f"  {v['eids']['licznik']}:\n" + IN_NUMBER_CONF

    text = HEADER.format(**v)
    text += COMMAND_LINE.format(**fields)
    text += INPUT_NUMBER.format(input_number_body=body)
    text += TEMPLATE.format(**fields)
    return text


for variant in VARIANTS:
    path = HA / variant
    path.write_text(build(variant), encoding='utf-8')
    print(f'zapisano: {variant}')
