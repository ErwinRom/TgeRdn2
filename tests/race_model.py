"""Model wyscigu o pelnej godzinie na PRAWDZIWYCH szablonach z homeassistant/.

To jest MODEL, nie pomiar: prawdziwej kolejnosci zdarzen w HA nie znamy, wiec
sprawdzamy wszystkie (losowe) kolejnosci. O pelnej godzinie w tej samej sekundzie
dzieje sie:

  EW   okno (binary_sensor) przelicza sie, bo now() zmienilo godzine
  EP   cena (sensor) przelicza sie
  CT   automatyzacja licznika: jesli przelacznik ON -> licznik + 1
       (zmiana licznika przelicza okno)
  RUN  uruchomienie automatyzacji ladowania; ocenia warunki na stanie z chwili
       wykonania

Bez opoznienia kazde zdarzenie daje wlasne uruchomienie (RUN), a wynik zalezy od
kolejnosci. Z `mode: restart` + `delay` decyzja zapada raz, po ustaniu zdarzen.
"""

import random
from datetime import datetime

from tgerdn.config import Tariff
from tgerdn.planner import build_day_prices, build_plan
from tgerdn.publisher import build_payload
from tgerdn.simulate import (SWITCH, FakeClock, build_env, build_states,
                             slugify)
from tgerdn.tge import RawFixing

W_ID = 'binary_sensor.tge_v2_najtansze_5h'
P_ID = 'sensor.tge_v2_aktualna_cena'
R_ID = 'sensor.tge_v2_reguly'
C_ID = 'input_number.tge_v2_ladowane_godziny'
DAY = '2026-11-12'

TARIFF = Tariff()


def make_payload(spots, day=DAY):
    fixings = [RawFixing(day, h + 1, spots[h] * 1000) for h in range(24)]
    prices = build_day_prices(day, fixings, TARIFF, fetched_at='x', source_url='x')
    return build_payload(prices, build_plan(prices, TARIFF), TARIFF, label='today')


def synthetic_day(rng):
    """Ksztalt doby: tania noc, dolina w dzien, wieczorny szczyt."""
    level = rng.choice([0.15, 0.25, 0.4, 0.6, 0.8])
    spots = []
    for hour in range(24):
        base = level
        if hour <= 5:
            base *= 0.55
        elif 11 <= hour <= 15:
            base *= rng.choice([0.2, 0.5, 0.9])
        elif 17 <= hour <= 21:
            base *= 1.5
        spots.append(round(max(-0.05, base + rng.uniform(-0.08, 0.08)), 4))
    return spots


def uses_debounce(car):
    """Czy automatyzacja ladowania czeka na ustalenie sie stanu (restart + delay)?"""
    actions = car.get('actions') or []
    return (car.get('mode') == 'restart' and bool(actions)
            and 'delay' in actions[0])


class World:
    """Stan encji HA + szablony skompilowane raz (szybkie renderowanie)."""

    def __init__(self, payload, config):
        self.states = build_states(payload, payload, charged=0, switch_on=False)
        self.env = build_env(self.states, datetime(2026, 11, 12, 0, 0))
        self.S = False
        self.C = 0

        entities = {}
        for block in config.configuration['template']:
            for kind in block:
                for entity in block[kind]:
                    entities[f"{kind}.{slugify(entity['name'])}"] = entity
        compile_ = self.env.from_string
        self.templates = {}
        for entity_id in (W_ID, P_ID, R_ID):
            entity = entities[entity_id]
            self.templates[entity_id] = {
                'state': compile_(entity['state']) if 'state' in entity else None,
                'availability': (compile_(entity['availability'])
                                 if 'availability' in entity else None),
                'attrs': {key: compile_(value)
                          for key, value in (entity.get('attributes') or {}).items()},
            }
        self.cond_on = compile_(config.turn_on_template)
        self.cond_off = compile_(config.turn_off_template)

        clock = FakeClock(datetime(2026, 11, 12, 0, 0))
        self.states[R_ID] = {'state': 'ok', 'attributes': {
            key: tpl.render(now=clock).strip()
            for key, tpl in self.templates[R_ID]['attrs'].items()}}

    def set_switch(self, on):
        self.S = on
        self.states[SWITCH] = {'state': 'on' if on else 'off', 'attributes': {}}

    def set_counter(self, value):
        self.C = value
        self.states[C_ID] = {'state': str(value), 'attributes': {}}

    def render(self, entity_id, moment):
        tpl = self.templates[entity_id]
        clock = FakeClock(moment)
        availability = tpl['availability']
        if availability is not None and availability.render(now=clock).strip() != 'True':
            return ('unavailable', ())
        state = tpl['state'].render(now=clock).strip()
        if entity_id == W_ID:
            state = {'True': 'on', 'False': 'off'}.get(state, state)
        attrs = tuple((key, t.render(now=clock).strip()) for key, t in tpl['attrs'].items())
        return (state, attrs)

    def store(self, entity_id, value):
        state, attrs = value
        self.states[entity_id] = {'state': state, 'attributes': dict(attrs)}

    def stored(self, entity_id):
        entry = self.states.get(entity_id) or {}
        return (entry.get('state'), tuple((entry.get('attributes') or {}).items()))

    def run_automation(self, moment):
        """Jedno uruchomienie automatyzacji ladowania. Zwraca 'on' / 'off' / None."""
        clock = FakeClock(moment)
        if self.cond_on.render(now=clock).strip() == 'True':
            self.set_switch(True)
            return 'on'
        if self.cond_off.render(now=clock).strip() == 'True':
            self.set_switch(False)
            return 'off'
        return None


def settle(world, moment):
    """Stan ustalony: przelicza okno i cene, uruchamia automatyzacje do stabilizacji."""
    for _ in range(4):
        world.store(W_ID, world.render(W_ID, moment))
        world.store(P_ID, world.render(P_ID, moment))
        if world.run_automation(moment) is None:
            return


def boundary(world, hour_new, rng, *, debounce):
    """Przechodzi H:00:00 -> (historia przelacznika, przelacznik przed, licznik przed)."""
    moment = datetime(2026, 11, 12, hour_new, 0, 1)
    before_switch, before_counter = world.S, world.C
    history = [world.S]
    todo = ['EW', 'EP', 'CT']
    queue = ['tp']
    while todo or (queue and not debounce):
        options = list(todo) + (['RUN'] if queue and not debounce else [])
        pick = rng.choice(options)
        if pick == 'EW':
            todo.remove('EW')
            new = world.render(W_ID, moment)
            if new != world.stored(W_ID):
                world.store(W_ID, new)
                queue.append('w')
        elif pick == 'EP':
            todo.remove('EP')
            new = world.render(P_ID, moment)
            if new != world.stored(P_ID):
                world.store(P_ID, new)
                queue.append('p')
        elif pick == 'CT':
            todo.remove('CT')
            if world.S:
                world.set_counter(world.C + 1)
                queue.append('c')
                new = world.render(W_ID, moment)
                if new != world.stored(W_ID):
                    world.store(W_ID, new)
                    queue.append('w')
        else:
            queue.pop(0)
            if world.run_automation(moment):
                history.append(world.S)
    settle(world, moment)
    if history[-1] != world.S:
        history.append(world.S)
    return history, before_switch, before_counter


def simulate(config, days, seed, *, debounce):
    """Zwraca liczniki bledow z `days` symulowanych dob (granice 01:00..23:00)."""
    rng = random.Random(seed)
    result = {'boundaries': 0, 'extra_toggles': 0, 'bad_credit': 0, 'on_hours': 0}
    for _ in range(days):
        world = World(make_payload(synthetic_day(rng)), config)
        world.set_switch(False)
        world.set_counter(0)
        settle(world, datetime(2026, 11, 12, 0, 30))
        for hour in range(1, 24):
            history, was_on, counter = boundary(world, hour, rng, debounce=debounce)
            result['boundaries'] += 1
            minimal = 1 if history[0] != history[-1] else 0
            if len(history) - 1 > minimal:
                result['extra_toggles'] += 1
            if world.C - counter != (1 if was_on else 0):
                result['bad_credit'] += 1
            result['on_hours'] += 1 if world.S else 0
    return result
