"""UTD campus agent-based simulation (Mesa 3 + NetworkX).

Run:  python campus_sim.py --days 5 --scale 2
Dev:  python campus_sim.py --agents 200 --days 2 --verbose-ids 2
"""
import argparse
import csv
import hashlib
import itertools
import json
import math
import os
import pickle
import random
import resource
import sys
import time
from collections import defaultdict

import mesa
import networkx as nx

import campus_config as cfg
from campus_config import clock, to_seconds
from population import load_section_pool, make_population, strip_for_json

IN_CLASS, WALKING, IDLE, OFF_CAMPUS = "IN_CLASS", "WALKING", "IDLE", "OFF_CAMPUS"
EATING, STUDYING, SOCIALIZING, EVENT = "EATING", "STUDYING", "SOCIALIZING", "EVENT"
SEATED = {EATING, STUDYING, SOCIALIZING}
ACT_STATE = {"eat": EATING, "study": STUDYING, "social": SOCIALIZING}
INFO_NAME = {IN_CLASS: "in_class", WALKING: "walking", IDLE: "idle", OFF_CAMPUS: "off_campus",
             EATING: "eating", STUDYING: "studying", SOCIALIZING: "socializing", EVENT: "at_event"}
INF = float("inf")


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


class StudentAgent(mesa.Agent):
    def __init__(self, model, spec):
        super().__init__(model)
        self.agent_id = spec["agent_id"]
        self.archetype = spec["archetype_tag"]
        self.t = spec["traits"]
        self.commuter = spec["commuter_tag"]["type"] == "commuter"
        self.permit = spec["commuter_tag"]["parking_permit"]
        self.parks_near_first = spec["parks_near_first"]
        self.meetings = spec["schedule"]
        self.speed = self.t["walking_speed_mps"]
        self.dice = random.Random(model.seed_base * 100003 + self.agent_id)
        self.info = dict(spec["state"])           # current_location/destination/current_activity/hunger/energy
        self.verbose = self.agent_id in model.verbose_ids
        self.log = []

        self.state = OFF_CAMPUS
        self.wake_at = 0
        self.off_until = 0
        self.departed = True
        self.loc, self.floor = None, 1
        self.route, self.route_index, self.progress_m, self.delay_s = [], 0, 0.0, 0.0
        self.walk = None
        self.until = 0
        self.held_seat = None                     # (building, floor, represented students)
        self.held_event = None                    # ((day, event_id), represented students)
        self.agenda, self.agenda_i = [], 0
        self.depart_at = None
        self.next_decision_at = 0
        self.lot = None
        self.usual_lot = None
        self.visits = defaultdict(int)
        self.alt_pref = {}
        self.meals = {}
        self.h0, self.h_t = 0.2, cfg.DAY_START
        self.e0 = self.info.get("energy", 0.85)
        self.hunger_level = clamp(self.info.get("hunger", 0.2), 0, 1)
        self.energy_level = clamp(self.info.get("energy", 0.85), 0, 1)
        self.state_updated_at = cfg.DAY_START
        self.class_occupancy_weight = model.represented_students
        self.arrived_at = 0
        self.study_mod = 1.0
        self.stay_s = 0
        self.base_hunger = self.info.get("hunger", 0.2)

    # ---------------------------------------------------------------- utilities
    def _say(self, msg):
        if self.verbose:
            line = f"[{self.model.day_name} {clock(self.model.time_s)}] agent {self.agent_id} ({self.archetype}): {msg}"
            self.log.append(line)
            print(line)

    def _set_state(self, new, msg=None):
        self.state = new
        self.info["current_activity"] = INFO_NAME[new]
        self.info["current_location"] = self.loc
        if self.verbose:
            self._say(msg or f"{INFO_NAME[new]} at {self.loc}")

    def _sync_state(self):
        self.hunger_level = clamp(self.hunger_level, 0, 1)
        self.energy_level = clamp(self.energy_level, 0, 1)
        self.info["hunger"] = self.hunger_level
        self.info["energy"] = self.energy_level

    def _update_metabolism(self, now):
        """Advance cheap hunger/energy state based on the state just elapsed."""
        elapsed_h = max(0, now - self.state_updated_at) / 3600
        if elapsed_h <= 0:
            self._sync_state()
            return
        self.hunger_level += cfg.HUNGER_PER_H * elapsed_h
        if self.state == OFF_CAMPUS:
            self.energy_level += cfg.OFF_CAMPUS_ENERGY_RECOVERY_PER_H * elapsed_h
        elif self.state == EATING:
            self.energy_level += cfg.MEAL_ENERGY_RECOVERY_PER_H * elapsed_h
        elif self.state == IDLE:
            self.energy_level += cfg.IDLE_ENERGY_RECOVERY_PER_H * elapsed_h
        else:
            self.energy_level -= cfg.ENERGY_DROP_PER_H * elapsed_h
            if self.state == WALKING:
                self.energy_level -= cfg.WALK_ENERGY_DROP_PER_H * elapsed_h
            elif self.state == STUDYING:
                self.energy_level -= cfg.STUDY_ENERGY_DROP_PER_H * elapsed_h
        self.state_updated_at = now
        self._sync_state()

    def hunger(self, now):
        self._update_metabolism(now)
        return self.hunger_level

    def energy(self, now):
        self._update_metabolism(now)
        return self.energy_level

    def _consume_meal(self, now):
        self.h0, self.h_t = 0.05, now
        self.hunger_level = 0.05
        self.energy_level = min(1.0, self.energy_level + 0.04)
        self._sync_state()

    def _travel(self, a, fa, b, fb):
        return self.model.walk_s(a, fa, b, fb, self.speed)

    def _release_seat(self):
        if self.held_seat:
            self.model.release(*self.held_seat)
            self.held_seat = None

    def _release_event(self):
        if self.held_event:
            key, count = self.held_event
            self.model.event_present[key] -= count
            self.held_event = None

    # ---------------------------------------------------------------- daily plan
    def new_day(self):
        m = self.model
        self._release_seat()
        self._release_event()
        self.walk = None
        self.state = OFF_CAMPUS
        self.departed = True
        self.depart_at = None
        self.agenda, self.agenda_i = [], 0
        self.next_decision_at = 0
        self.info["current_activity"] = "off_campus"
        self.info["destination"] = None
        t, d = self.t, self.dice

        # --- attendance (4.10) and classes with arrival/exit bell curves (4.3, 4.4)
        p_att = clamp(t["attendance"] * (1 - t["class_skip_tendency"]) - m.semester_decline + m.exam_boost, 0, 1)
        early_mean = (t["punctuality"] - cfg.PUNCT_NEUTRAL) / (1 - cfg.PUNCT_NEUTRAL) * cfg.MAX_EARLY_S
        for mt in sorted((x for x in self.meetings if x["day"] == m.day_name), key=lambda x: x["start_s"]):
            if d.random() >= p_att:
                continue
            dur = mt["end_s"] - mt["start_s"]
            arrive = mt["start_s"] - early_mean + d.gauss(0, cfg.CLASS_ARRIVAL_STD_S)
            arrive = min(arrive, mt["start_s"] + 0.3 * dur)
            exit_t = max(mt["end_s"] + d.gauss(0, cfg.CLASS_EXIT_STD_S), mt["start_s"] + 0.5 * dur)
            self.agenda.append({"kind": "class", "name": mt["section_id"], "building": mt["building"],
                                "floor": mt["floor"], "start": mt["start_s"], "end": mt["end_s"],
                                "arrive_target": arrive, "exit_target": exit_t,
                                "represented_enrollment": mt.get("represented_enrollment", m.represented_students)})

        # --- campus events (4.8): interest roll, bell-curve arrival/duration, must fit around agenda
        for ev in m.events_today:
            if d.random() >= t["event_interest"] * ev["p_scale"]:
                continue
            arrival = ev["start_s"] + 10 * 60 + d.gauss(0, 15 * 60)
            arrival = clamp(arrival, ev["start_s"] - 15 * 60, ev["end_s"] - 15 * 60)
            end = arrival + max(10 * 60, d.gauss(45 * 60, 20 * 60))
            end = min(end, ev["end_s"] + 15 * 60)
            if self._event_fits(ev["building"], arrival, end):
                self.agenda.append({"kind": "event", "name": ev.get("name", "campus_event"), "id": ev["id"],
                                    "building": ev["building"], "floor": 1, "start": ev["start_s"],
                                    "end": ev["end_s"], "arrive_target": arrival, "exit_target": end})
        self.agenda.sort(key=lambda x: x["arrive_target"])

        # --- per-day behavior weights
        mod = 1.0
        for term in m.exam_study_terms:
            mod *= 1 + t["study_spike_response"] * term
        self.study_mod = mod
        self.meals = {}
        std_h = cfg.BASE_MEAL_STD_H * (1 - 0.7 * t["meal_regularness"])
        for name, mc in cfg.MEALS.items():
            self.meals[name] = {
                "time": clamp(d.gauss(mc["mean_h"], std_h), mc["lo_h"], mc["hi_h"]) * 3600,
                "end": mc["hi_h"] * 3600,
                "eat": d.random() < 0.5 + 0.45 * t["meal_regularness"],
                "done": False}
        self.h0, self.h_t = clamp(d.gauss(self.base_hunger, 0.05), 0, 1), cfg.DAY_START
        self.hunger_level = self.h0
        self.energy_level = clamp(d.gauss(self.e0, 0.04), 0, 1)
        self.state_updated_at = cfg.DAY_START
        self._sync_state()
        base = 30 if self.commuter else 90
        exp_stay = base + 60 * t["sociability"] + 45 * t["campus_stay_tendency"] - 30 * t["leave_campus_tendency"]
        self.stay_s = max(0, d.gauss(exp_stay, 20)) * 60

        if not self.agenda:
            self.off_until = INF
            self.wake_at = INF
            return

        # --- parking lot + campus arrival (4.2)
        first, last = self.agenda[0], self.agenda[-1]
        self.lot = self._choose_lot(first if self.parks_near_first else last)
        lot = m.lots[self.lot]
        walk_s = self._travel(self.lot, 1, first["building"], first["floor"]) or 0
        delay = max(0, d.gauss(cfg.BASE_PARKING_DELAY_S * lot["delay_min"] / 5, cfg.PARKING_STD_S))
        arrival = first["arrive_target"] - walk_s - delay + d.gauss(0, cfg.ARRIVAL_STD_S)
        self.off_until = max(cfg.DAY_START, arrival)
        self.departed = False
        self.wake_at = self.off_until
        self.e0 = clamp(self.e0, 0, 1)

    def _event_fits(self, bld, arrival, end):
        for it in self.agenda:
            gap1 = (self.model.walk_s(bld, 1, it["building"], it["floor"], self.speed) or 0) + cfg.LEAVE_BUFFER_S
            gap2 = (self.model.walk_s(it["building"], it["floor"], bld, 1, self.speed) or 0) + cfg.LEAVE_BUFFER_S
            if not (end + gap1 <= it["arrive_target"] or it["exit_target"] + gap2 <= arrival):
                return False
        return True

    def _choose_lot(self, target):
        m = self.model
        eligible = m.lots_for(self.permit)
        if self.usual_lot in eligible and self.dice.random() < self.t["parking_loyalty"]:
            return self.usual_lot
        weights = []
        for lot in eligible:
            walk = (m.dist(lot, target["building"]) or 1e5) / self.speed
            weights.append(math.exp(-(walk + m.lots[lot]["delay_min"] * 60) / 600))
        choice = self.dice.choices(eligible, weights)[0]
        if self.usual_lot is None:
            self.usual_lot = choice
        return choice

    # ---------------------------------------------------------------- stepping
    def step(self):
        now = self.model.time_s
        self._update_metabolism(now)
        s = self.state
        if s == WALKING:
            self._walk()
            return
        if s == OFF_CAMPUS:
            if now >= self.off_until and not self.departed:
                self.loc, self.floor = self.lot, 1
                if self.arrived_at == 0 or now - self.arrived_at > 12 * 3600:
                    self.arrived_at = now
                self.next_decision_at = 0
                self._set_state(IDLE, f"ARRIVED at lot {self.lot}")
                self.wake_at = 0
            else:
                self.wake_at = self.off_until if not self.departed else INF
                return
        elif s in (IN_CLASS, EVENT):
            if now < self.until:
                self.wake_at = self.until
                return
            self._finish_item(now)
        elif s in SEATED:
            if now < self.until:
                self.wake_at = self.until
                return
            if s == EATING:
                self._consume_meal(now)
            self._release_seat()
            self.next_decision_at = 0
            self._set_state(IDLE)
        if self.state == IDLE:
            self._plan(now)

    def _finish_item(self, now):
        self._release_event()
        self.agenda_i += 1
        self.next_decision_at = 0
        if self.agenda_i >= len(self.agenda):
            self.depart_at = now + self.stay_s
        self._set_state(IDLE)

    def _plan(self, now):
        item = self.agenda[self.agenda_i] if self.agenda_i < len(self.agenda) else None
        m = self.model
        if item is None:
            to_lot = self._travel(self.loc, self.floor, self.lot, 1) or 0
            depart = min(self.depart_at if self.depart_at is not None else now,
                         cfg.DAY_END - to_lot - 120)
            if now >= depart:
                self._start_walk(self.lot, 1, {"purpose": "depart"})
                return
            if now >= self.next_decision_at:
                self.next_decision_at = now + cfg.DECISION_INTERVAL_S
                if self._free_time(None, now, depart):
                    return
            self.wake_at = max(now + cfg.STEP_SECONDS, min(self.next_decision_at, depart))
            return

        travel = self._travel(self.loc, self.floor, item["building"], item["floor"]) or 0
        leave_at = item["arrive_target"] - travel
        if now >= leave_at:
            self._start_walk(item["building"], item["floor"], {"purpose": "item", "item": item})
            return
        if now >= self.next_decision_at:
            self.next_decision_at = now + cfg.DECISION_INTERVAL_S
            if self._free_time(item, now, item["arrive_target"]):
                return
        self.wake_at = max(now + cfg.STEP_SECONDS, min(self.next_decision_at, leave_at))

    # ---------------------------------------------------------------- free time (5.x)
    def _due_meal(self, now):
        for name, ml in self.meals.items():
            if ml["eat"] and not ml["done"] and ml["time"] <= now < ml["end"]:
                return name
        return None

    def _free_time(self, item, now, deadline):
        gap = deadline - now
        if gap < cfg.MIN_ACTIVITY_S + 60:
            return False
        if item is None:
            bnode, bfl = self.lot, 1
        else:
            bnode, bfl = item["building"], item["floor"]
        t = self.t
        meal = self._due_meal(now)
        current_hunger, current_energy = self.hunger(now), self.energy(now)
        if meal is None and current_hunger >= cfg.HUNGRY_MEAL_THRESHOLD:
            meal = "hunger"
        opts = {"study": t["studiousness"] * self.study_mod * (0.4 + 0.6 * current_energy),
                "social": t["sociability"],
                "stay": 0.15 + 0.5 * t["campus_stay_tendency"]}
        if meal:
            opts["eat"] = 0.6 + 3 * current_hunger
        if current_energy < 0.55:
            opts["rest"] = 1.5 * (0.55 - current_energy)
        if item is not None and gap >= cfg.LEAVE_MIN_GAP_S:
            opts["leave"] = (t["leave_campus_tendency"] * (1 - 0.8 * t["commute_friction"])
                             * (1.3 - self.energy(now)) * (1.0 if self.commuter else 0.6))
        while opts:
            names = list(opts)
            pick = self.dice.choices(names, [max(opts[n], 1e-6) for n in names])[0]
            if pick in ("stay", "rest"):
                return False
            if pick == "leave":
                if self._try_leave(item, now):
                    return True
            else:
                if self._try_seated(pick, meal, now, deadline, bnode, bfl):
                    return True
            del opts[pick]
        return False

    def _duration(self, kind):
        d, t = self.dice, self.t
        if kind == "eat":
            return max(10, d.gauss(30, 10)) * 60
        if kind == "study":
            base = max(10, d.gauss(45 + 30 * t["studiousness"], 20))
            return base * (0.65 + 0.35 * self.energy_level) * 60
        return max(10, d.gauss(30 + 30 * t["sociability"], 15)) * 60

    def _try_seated(self, kind, meal, now, deadline, bnode, bfl):
        m = self.model
        dur = self._duration(kind)
        cands, weights = [], []
        for b in m.seat_nodes:
            if m.free_total[b] <= 0:
                continue
            est = m.est_floor_s[b]
            d_to = m.dist(self.loc, b)
            d_back = m.dist(b, bnode)
            if d_to is None or d_back is None:
                continue
            to = d_to / self.speed + est + cfg.FLOOR_SECONDS * m.floors_out(self.loc, self.floor)
            back = d_back / self.speed + est + cfg.FLOOR_SECONDS * m.floors_out(bnode, bfl)
            avail = deadline - now - to - back - cfg.LEAVE_BUFFER_S
            if avail < cfg.MIN_ACTIVITY_S:
                continue
            scale = 150 + 0.25 * avail
            familiar = self.visits[b] / (1 + max(self.visits.values(), default=0))
            w = (math.exp(-to / scale) * (m.free_total[b] / m.seat_cap[b]) ** 0.5
                 * (1 + 1.5 * self.t["route_consistency"] * familiar)
                 * (3.0 if b == self.loc else 1.0))
            cands.append((b, avail))
            weights.append(w)
        if not cands:
            return False
        (b, avail), = self.dice.choices(cands, weights)
        floor = m.claim(b, self.dice, m.represented_students)
        if floor is None:
            return False
        self.held_seat = (b, floor, m.represented_students)
        if kind == "eat" and meal in self.meals:
            self.meals[meal]["done"] = True
        dur = min(dur, avail)
        self._start_walk(b, floor, {"purpose": "activity", "kind": kind, "dur": dur, "deadline": deadline,
                                    "back_node": bnode, "back_floor": bfl})
        return True

    def _try_leave(self, item, now):
        m = self.model
        commute = cfg.COMMUTE_S["commuter" if self.commuter else "dormer"]
        to_lot = self._travel(self.loc, self.floor, self.lot, 1)
        lot_to_item = self._travel(self.lot, 1, item["building"], item["floor"])
        if to_lot is None or lot_to_item is None:
            return False
        return_at = item["arrive_target"] - lot_to_item - cfg.LEAVE_BUFFER_S
        if return_at - (now + to_lot) < 2 * commute + cfg.HOME_MIN_S:
            return False
        self._start_walk(self.lot, 1, {"purpose": "home", "return_at": return_at})
        return True

    # ---------------------------------------------------------------- movement
    def _start_walk(self, node, floor, walk):
        m = self.model
        floors = m.floors_between(self.loc, self.floor, node, floor)
        route = m.route(self, self.loc, node)
        if route is None:
            m.teleports += 1
            self.loc = node
            route = [node]
        self.route, self.route_index, self.progress_m = route, 0, 0.0
        self.delay_s = cfg.FLOOR_SECONDS * floors
        walk.update(node=node, floor=floor)
        self.walk = walk
        self.info["destination"] = node
        self._set_state(WALKING, f"walking to {node} for {walk['purpose']}")
        self.wake_at = 0
        self._walk()

    def _walk(self):
        if self.delay_s > 0:
            self.delay_s -= cfg.STEP_SECONDS
            if self.delay_s > 0:
                return
        budget = self.speed * cfg.STEP_SECONDS
        while budget > 0 and self.route_index < len(self.route) - 1:
            u, v = self.route[self.route_index], self.route[self.route_index + 1]
            remaining = self.model.edge_len(u, v) - self.progress_m
            if budget >= remaining:
                budget -= remaining
                self.route_index += 1
                self.progress_m = 0.0
                self.loc = v
            else:
                self.progress_m += budget
                budget = 0
        if self.route_index >= len(self.route) - 1:
            self._arrive()

    def _arrive(self):
        w, self.walk = self.walk, None
        now = self.model.time_s
        self.loc, self.floor = w["node"], w["floor"]
        self.info["destination"] = None
        p = w["purpose"]
        if p == "item":
            item = w["item"]
            if item["kind"] == "class":
                self.class_occupancy_weight = item.get("represented_enrollment", self.model.represented_students)
                self.until = max(item["exit_target"], now + 60)
                self._set_state(IN_CLASS, f"IN CLASS {item['name']} in {self.loc}")
            else:
                ev = self.model.event_by_id[item["id"]]
                key = (self.model.day_index, ev["id"])
                count = self.model.represented_students
                if self.model.event_present[key] + count > ev["cap"]:
                    self.model.event_turned_away[key] += 1
                    self._finish_item(now)          # full: gives up, acts like free time
                    return
                self.model.event_present[key] += count
                self.model.event_attended[key] += count
                self.model.event_peak[key] = max(self.model.event_peak[key], self.model.event_present[key])
                self.held_event = (key, count)
                self.until = now + max(10 * 60, item["exit_target"] - item["arrive_target"])
                self._set_state(EVENT, f"AT EVENT {item['name']}")
            self.wake_at = self.until
        elif p == "activity":
            back = self.model.walk_s(self.loc, self.floor, w["back_node"], w["back_floor"], self.speed) or 0
            end = min(now + w["dur"], w["deadline"] - back - cfg.LEAVE_BUFFER_S)
            self.until = max(end, now + 60)
            self.visits[self.loc] += 1
            self._set_state(ACT_STATE[w["kind"]], f"{w['kind']} at {self.loc} until {clock(self.until)}")
            self.wake_at = self.until
        elif p == "home":
            self.off_until = w["return_at"]
            self._set_state(OFF_CAMPUS, f"LEFT campus for a break, back ~{clock(w['return_at'])}")
            self.wake_at = self.off_until
        else:  # depart
            self.departed = True
            self.off_until = INF
            self._set_state(OFF_CAMPUS, "DEPARTED campus")
            self.wake_at = INF


class CampusModel(mesa.Model):
    def __init__(self, graph, events, scale_ratio=2, seed=0, verbose_ids=()):
        super().__init__(seed=seed)
        self.G = graph
        self.multi = graph.is_multigraph()
        self.scale = scale_ratio
        self.seed_base = seed
        self.verbose_ids = set(verbose_ids)
        self.day_index, self.time_s = 0, cfg.DAY_START
        self.students = []
        self.teleports = 0
        self._day_started = False
        self._dist, self._paths = {}, {}

        # Physical seats never scale with simulated population.  An agent claims the
        # number of people it represents, so occupancy remains physically meaningful.
        self.seats, self.seat_cap, self.free_total, self.est_floor_s = {}, {}, {}, {}
        self.missing_seat_nodes = []
        for key, floors in cfg.SEATING_FULL.items():
            node = cfg.NODE_ALIAS.get(key, key)
            if node not in graph:
                self.missing_seat_nodes.append(key)
                continue
            d = self.seats.setdefault(node, {})
            for fl, n in floors.items():
                d[fl] = d.get(fl, 0) + n
        # Accessible academic map nodes omitted from the measured inventory retain
        # the agreed temporary 100-seat fallback.  Inaccessible/closed/construction
        # nodes are excluded explicitly.
        self.default_seat_nodes = []
        for node, attrs in graph.nodes(data=True):
            if (attrs.get("type") == "building" and attrs.get("category") == "academic"
                    and attrs.get("status") == "active" and attrs.get("routable")
                    and node not in cfg.INACCESSIBLE_BUILDINGS and node not in self.seats):
                self.seats[node] = {1: cfg.DEFAULT_SEATS_PER_BUILDING}
                self.default_seat_nodes.append(node)
        for node, d in list(self.seats.items()):
            total = sum(d.values())
            if total <= 0:
                del self.seats[node]
                continue
            self.seat_cap[node] = total
            self.free_total[node] = total
            g = cfg.GROUND_FLOOR.get(node, 1)
            self.est_floor_s[node] = cfg.FLOOR_SECONDS * sum(abs(f - g) * n for f, n in d.items()) / total
        self.seat_nodes = list(self.seats)
        self.represented_students = cfg.represented_students(scale_ratio)

        self.lots = self._resolve_lots()
        self.missing_lots = []
        if not self.lots:
            raise SystemExit("No usable PARKING_LOTS - edit them in campus_config.py")

        # events
        self.exam_periods = [e for e in events if e["type"] == "exam_period"]
        self.campus_events = []
        self.invalid_events = []
        for i, e in enumerate(e for e in events if e["type"] == "campus_event"):
            if e["building"] not in graph:
                self.invalid_events.append(e)
                continue
            ev = dict(e, id=i, start_s=to_seconds(e["start_time"]), end_s=to_seconds(e["end_time"]),
                      cap=e["attendance_capacity"])
            self.campus_events.append(ev)
        self.event_by_id = {e["id"]: e for e in self.campus_events}
        self.event_present = defaultdict(int)
        self.event_attended = defaultdict(int)
        self.event_peak = defaultdict(int)
        self.event_turned_away = defaultdict(int)
        self.events_today, self.exam_study_terms = [], []
        self.exam_boost = self.semester_decline = 0.0
        self.snapshots = []
        self.occupancy_nodes = sorted(
            (n for n, attrs in graph.nodes(data=True)
             if attrs.get("type") == "building" and attrs.get("status") == "active"
             and attrs.get("routable") and n not in cfg.INACCESSIBLE_BUILDINGS),
            key=str,
        )

    def _resolve_lots(self):
        """Lots can be existing nodes, or positions (lat/lon or bbox fraction) snapped to the nearest walkable path node."""
        G = self.G
        bnodes = [n for n, d in G.nodes(data=True) if d.get("type") == "building" and "x" in d]
        comp = max(nx.connected_components(G), key=len) if not nx.is_directed(G) else set(G.nodes)
        paths = [(n, d["x"], d["y"]) for n, d in G.nodes(data=True)
                 if n in comp and d.get("type") != "building" and "x" in d]
        if bnodes:
            xs = [G.nodes[n]["x"] for n in bnodes]
            ys = [G.nodes[n]["y"] for n in bnodes]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        lots = {}
        for name, v in cfg.PARKING_LOTS.items():
            if name in G:
                lots[name] = v
                continue
            if "lon" in v and "lat" in v:
                x, y = v["lon"], v["lat"]
            elif "frac" in v and bnodes:
                x, y = x0 + v["frac"][0] * (x1 - x0), y0 + v["frac"][1] * (y1 - y0)
            else:
                continue
            if not paths:
                continue
            node = min(paths, key=lambda p: (p[1] - x) ** 2 + ((p[2] - y) * 1.2) ** 2)[0]
            lots[node] = dict(v, name=name)
        return lots

    @property
    def day_name(self):
        return cfg.DAYS[self.day_index % 5]

    # ---------------------------------------------------------------- graph helpers
    def edge_len(self, u, v):
        return self._w(u, v, self.G[u][v])

    def _w(self, u, v, d):
        if self.multi:
            return min(float(x.get("length", cfg.DEFAULT_EDGE_LENGTH_M)) for x in d.values())
        return float(d.get("length", cfg.DEFAULT_EDGE_LENGTH_M))

    def dist(self, a, b):
        if a == b:
            return 0.0
        if a not in self._dist:
            self._dist[a] = nx.single_source_dijkstra_path_length(self.G, a, weight=self._w)
        return self._dist[a].get(b)

    def floors_out(self, node, floor):
        return abs(floor - cfg.GROUND_FLOOR.get(node, 1))

    def floors_between(self, a, fa, b, fb):
        if a == b:
            return abs(fa - fb)
        return self.floors_out(a, fa) + self.floors_out(b, fb)

    def walk_s(self, a, fa, b, fb, speed):
        d = self.dist(a, b)
        if d is None:
            return None
        return d / speed + cfg.FLOOR_SECONDS * self.floors_between(a, fa, b, fb)

    def route(self, agent, a, b):
        if a == b:
            return [a]
        if (a, b) not in self._paths:
            try:
                paths = [nx.shortest_path(self.G, a, b, weight=self._w)]
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                self._paths[(a, b)] = None
                return None
            if cfg.ALT_ROUTES:
                try:
                    for p in itertools.islice(nx.shortest_simple_paths(self.G, a, b, weight=self._w), 2):
                        if p != paths[0] and self._len(p) <= cfg.ALT_ROUTE_MAX_RATIO * self._len(paths[0]):
                            paths.append(p)
                            break
                except Exception:
                    pass
            self._paths[(a, b)] = paths
        paths = self._paths[(a, b)]
        if paths is None:
            return None
        if len(paths) == 1:
            return paths[0]
        key = (a, b)
        if key not in agent.alt_pref:       # familiar-route choice is fixed per agent per pair
            agent.alt_pref[key] = agent.dice.random() < (1 - agent.t["route_consistency"]) * 0.5
        return paths[1] if agent.alt_pref[key] else paths[0]

    def _len(self, p):
        return sum(self.edge_len(u, v) for u, v in zip(p, p[1:]))

    def lots_for(self, permit):
        zones = set(cfg.PERMIT_ACCESS[permit])
        out = [n for n, v in self.lots.items() if v["zone"] in zones]
        return out or list(self.lots)

    # ---------------------------------------------------------------- seats
    def claim(self, b, dice, count=1):
        floors = [(f, n) for f, n in self.seats[b].items() if n >= count]
        if not floors:
            return None
        f = dice.choices([x[0] for x in floors], [x[1] for x in floors])[0]
        self.seats[b][f] -= count
        self.free_total[b] -= count
        return f

    def release(self, b, f, count=1):
        self.seats[b][f] += count
        self.free_total[b] += count

    # ---------------------------------------------------------------- day / step
    def start_day(self):
        d = self.day_index
        self.semester_decline = cfg.DECLINE_RATE * d / cfg.TOTAL_SEMESTER_DAYS
        self.exam_boost, self.exam_study_terms = 0.0, []
        for e in self.exam_periods:
            mid = (e["start_day"] + e["end_day"]) / 2
            eff = math.exp(-0.5 * ((d - mid) / cfg.EXAM_STD_DAYS) ** 2)
            self.exam_boost += cfg.EXAM_ATTENDANCE_BOOST * eff
            self.exam_study_terms.append((e["study_multiplier"] - 1) * eff)
        self.events_today = [e for e in self.campus_events if e["day"] == d]
        # Raw `random() < event_interest` would send ~half of campus to every event. Scale each event's interested
        # crowd to about EVENT_OVERSUBSCRIBE x its capacity (so a few people still get turned away).
        total_interest = sum(a.t["event_interest"] for a in self.students) or 1.0
        for e in self.events_today:
            e["p_scale"] = min(1.0, cfg.EVENT_OVERSUBSCRIBE * e["cap"] / total_interest)
        for a in self.students:
            a.new_day()
        self._day_started = True

    def step(self):
        if not self._day_started:
            self.start_day()
        now = self.time_s
        for a in self.students:
            if now >= a.wake_at:
                a.step()
        if now % cfg.SNAPSHOT_S == 0:
            self.record()
        self.time_s += cfg.STEP_SECONDS
        if self.time_s >= cfg.DAY_END:
            self.time_s = cfg.DAY_START
            self.day_index += 1
            self._day_started = False

    def record(self):
        cnt = {node: [0, 0, 0, 0] for node in self.occupancy_nodes}
        walking = 0
        for a in self.students:
            s = a.state
            if s == OFF_CAMPUS:
                continue
            if s == WALKING:
                walking += self.represented_students
                continue
            row = cnt.setdefault(a.loc, [0, 0, 0, 0])
            weight = a.class_occupancy_weight if s == IN_CLASS else self.represented_students
            row[0 if s == IN_CLASS else 1 if s in SEATED else 2 if s == EVENT else 3] += weight
        day = self.day_index
        for b, r in cnt.items():
            self.snapshots.append((day, self.day_name, self.time_s, clock(self.time_s), b, *r, sum(r)))
        self.snapshots.append((day, self.day_name, self.time_s, clock(self.time_s),
                               "_WALKING", 0, 0, 0, walking, walking))

    def check_seats(self):
        for b, fl in self.seats.items():
            for f, n in fl.items():
                assert n >= 0, f"seat underflow {b} floor {f}"
        total_held = sum(a.held_seat[2] for a in self.students if a.held_seat)
        total_free = sum(self.free_total.values())
        assert total_free + total_held == sum(self.seat_cap.values()), "seat accounting mismatch"


def load_graph(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=str(cfg.GRAPH_PATH))
    ap.add_argument("--courses", default=str(cfg.COURSES_PATH))
    ap.add_argument("--archetypes", default=str(cfg.ARCHETYPES_PATH))
    ap.add_argument("--events", default=str(cfg.EVENTS_PATH))
    ap.add_argument("--scale", type=int, default=cfg.SCALE_RATIO)
    ap.add_argument("--agents", type=int, default=None, help="override agent count (dev)")
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--start-day", type=int, default=0, help="semester day to start on (0-based)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose-ids", type=int, default=0, help="print the log of the first N agents")
    ap.add_argument("--out", default="out")
    ap.add_argument("--save-population", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    G = load_graph(args.graph)
    with open(args.archetypes) as f:
        archetypes = json.load(f)["archetypes"]
    with open(args.events) as f:
        events = json.load(f)["events"]

    n = args.agents or cfg.TOTAL_STUDENTS // args.scale
    rng = random.Random(args.seed)
    model = CampusModel(G, events, args.scale, args.seed, verbose_ids=range(1, args.verbose_ids + 1))
    model.day_index = args.start_day
    if model.missing_seat_nodes:
        print("WARNING seat keys not in graph (edit SEATING_FULL / NODE_ALIAS):", model.missing_seat_nodes)
    if model.missing_lots:
        print("WARNING parking lots not in graph (edit PARKING_LOTS):", model.missing_lots)
    for ev in model.invalid_events:
        print(f"WARNING event '{ev.get('name', ev['type'])}' building {ev['building']} is not in graph; skipped")

    pool, pool_stats = load_section_pool(args.courses, set(G.nodes))
    specs, enrollment_report = make_population(
        archetypes, n, pool, rng, scale_ratio=args.scale,
        pool_stats=pool_stats, return_report=True,
    )
    for s in specs:
        model.students.append(StudentAgent(model, s))
    setup_s = time.time() - t0
    print(f"{n} agents at {args.scale}:1 | seats {sum(model.seat_cap.values())} across "
          f"{len(model.seat_nodes)} buildings | setup {setup_s:.1f}s")

    if args.save_population:
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "population.json"), "w") as f:
            json.dump(strip_for_json(specs), f)

    steps_per_day = (cfg.DAY_END - cfg.DAY_START) // cfg.STEP_SECONDS
    day_results = []
    simulation_s = 0.0
    for d in range(args.days):
        t1 = time.time()
        for _ in range(steps_per_day):
            model.step()
        model.check_seats()
        on = sum(1 for a in model.students if a.state != OFF_CAMPUS)
        elapsed = time.time() - t1
        simulation_s += elapsed
        day_results.append({"semester_day": args.start_day + d,
                            "weekday": cfg.DAYS[(args.start_day + d) % 5],
                            "runtime_seconds": elapsed,
                            "agents_on_campus_at_close": on})
        print(f"day {args.start_day + d} ({cfg.DAYS[(args.start_day + d) % 5]}) done in {elapsed:.1f}s | "
              f"still on campus at close: {on} | teleports so far: {model.teleports}")

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "occupancy_snapshots.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["semester_day", "weekday", "time_s", "time_of_day", "building_code",
                    "in_class", "seated", "at_event", "idle_or_walking", "total_occupancy"])
        w.writerows(model.snapshots)
    with open(os.path.join(args.out, "enrollment_validation.json"), "w") as f:
        json.dump(enrollment_report, f, indent=2)
    section_fields = ["section_id", "course", "credits", "credit_source", "source_enrollment",
                      "max_enrollment", "target_enrollment", "assigned_enrollment",
                      "unfilled_enrollment", "over_capacity"]
    with open(os.path.join(args.out, "enrollment_by_section.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=section_fields)
        w.writeheader()
        w.writerows(enrollment_report["sections"])
    if args.save_population:
        with open(os.path.join(args.out, "agent_states.json"), "w") as f:
            json.dump([{"agent_id": a.agent_id, **a.info} for a in model.students], f)
    if model.event_attended:
        for key, n_att in sorted(model.event_attended.items()):
            ev = model.event_by_id[key[1]]
            print(f"event '{ev.get('name', 'campus_event')}' day {key[0]}: cumulative {n_att}, peak "
                  f"{model.event_peak[key]}/cap {ev['cap']}, turned away {model.event_turned_away[key]}")
    peak = defaultdict(int)
    for row in model.snapshots:
        if row[4] != "_WALKING":
            peak[row[4]] = max(peak[row[4]], row[9])
    top = sorted(peak.items(), key=lambda x: -x[1])[:8]
    total_s = time.time() - t0
    manifest = {
        "schema_version": cfg.OUTPUT_SCHEMA_VERSION, "configuration_version": cfg.CONFIG_VERSION,
        "seed": args.seed, "scale_ratio": args.scale, "agents": n,
        "represented_students": n * args.scale, "semester_start_day": args.start_day,
        "days": args.days, "snapshot_seconds": cfg.SNAPSHOT_S,
        "graph": os.path.relpath(args.graph, cfg.REPO_ROOT) if os.path.isabs(args.graph) else args.graph,
        "courses": os.path.relpath(args.courses, cfg.REPO_ROOT) if os.path.isabs(args.courses) else args.courses,
        "events": os.path.relpath(args.events, cfg.REPO_ROOT) if os.path.isabs(args.events) else args.events,
        "events_sha256": hashlib.sha256(open(args.events, "rb").read()).hexdigest(),
        "initialization_seconds": setup_s, "simulation_seconds": simulation_s,
        "total_runtime_seconds": total_s, "day_results": day_results,
        "peak_memory_bytes": (resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                              if sys.platform == "darwin"
                              else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
        "occupancy_rows": len(model.snapshots), "teleports": model.teleports,
        "agents_on_campus_at_close": on,
        "seating_capacity_violations": 0,
        "event_capacity_violations": sum(model.event_peak[k] > model.event_by_id[k[1]]["cap"] for k in model.event_peak),
        "enrollment_validation": "enrollment_validation.json",
        "occupancy_file": "occupancy_snapshots.csv",
    }
    with open(os.path.join(args.out, "run_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print("peak occupancy (students):", ", ".join(f"{b}={v}" for b, v in top))
    print(f"enrollment assigned {enrollment_report['assigned_enrollment']}/"
          f"{enrollment_report['target_enrollment_usable']} | exact sections "
          f"{enrollment_report['sections_exact_percent']:.1f}%")
    print(f"wrote {args.out}/occupancy_snapshots.csv | total {total_s:.1f}s")


if __name__ == "__main__":
    main()
