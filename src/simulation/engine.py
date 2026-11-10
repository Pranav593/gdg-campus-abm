"""Discrete event day planner using actual NetworkX walking routes and activity durations."""
from __future__ import annotations

import math
import random
from array import array
import networkx as nx

DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
SEATED = {"study", "meal", "socialize", "event"}


class CampusSimulation:
    def __init__(self, graph, buildings, parking_lots, events, population, seed=42, capacity_scale=1.0,
                 record_callback=None, agent_callback=None, retain_log=True):
        self.graph, self.buildings, self.parking_lots = graph, buildings, parking_lots
        self.events, self.population, self.rng = events, population, random.Random(seed)
        self.capacity_scale = capacity_scale
        self.seat_capacity = max(1, round(100 * capacity_scale))
        self.seat_reservations = {}
        self.log = []
        self.retain_log = retain_log
        self.record_callback = record_callback
        self.agent_callback = agent_callback
        self.route_tables = {}
        self.modifier_cache = {}
        self.activity_records = 0
        self.active_agents = 0
        self.archetypes_seen = set()

    def _routes_from(self, start):
        if start not in self.route_tables:
            distances, paths = nx.single_source_dijkstra(self.graph, start, weight="length")
            self.route_tables[start] = (distances, paths)
        return self.route_tables[start]

    def travel(self, start, end, speed, floor_delta=0):
        if start == end:
            return 0.0, [start]
        distances, paths = self._routes_from(start)
        if end not in distances:
            raise nx.NetworkXNoPath(f"No walking route from {start} to {end}")
        distance, route = distances[end], paths[end]
        return distance / speed / 60 + abs(floor_delta) * .5, route

    def _distance(self, start, end):
        if start == end:
            return 0.0
        distances, _ = self._routes_from(start)
        if end not in distances:
            raise nx.NetworkXNoPath(f"No walking route from {start} to {end}")
        return distances[end]

    def _record(self, row):
        self.activity_records += 1
        if self.retain_log:
            self.log.append(row)
        if self.record_callback is not None:
            self.record_callback(row)

    def _walk(self, agent, destination, minute, day_index, activity):
        state, speed = agent["state"], agent["traits"]["walking_speed_mps"]
        origin = state["current_location"]
        floor_delta = abs(state.get("current_floor", 0) - state.get("destination_floor", 0))
        duration, route = self.travel(origin, destination, speed, floor_delta)
        state.update(destination=destination, current_activity="walking")
        self._record(self._row(agent, day_index, minute, minute + duration, "walk", origin, destination, route=route))
        state.update(current_location=destination, destination=None, current_activity=activity)
        return minute + duration

    def _row(self, agent, day, start, end, activity, origin, destination, **extra):
        return {"agent_id": agent["agent_id"], "day": day, "start_minute": round(start, 2), "end_minute": round(end, 2), "activity": activity, "origin": origin, "destination": destination, **extra}

    def _exam_modifiers(self, day):
        cached = self.modifier_cache.get(day)
        if cached is not None:
            return cached
        study, attendance = 1.0, 0.0
        for event in self.events:
            if event["type"] != "exam_period":
                continue
            midpoint = (event["start_day"] + event["end_day"]) / 2
            effect = math.exp(-.5 * ((day - midpoint) / 7) ** 2)
            study *= 1 + (event["study_multiplier"] - 1) * effect
            attendance += .12 * effect
        result = study, attendance
        self.modifier_cache[day] = result
        return result

    def _attends(self, agent, day):
        study, exam_attendance = self._exam_modifiers(day)
        base = agent["traits"]["attendance"] * (1 - agent["traits"]["class_skip_tendency"])
        return self.rng.random() < min(1, max(0, base - .12 * day / 112 + exam_attendance)), study

    def _parking_choice(self, agent, classes):
        first, last = classes[0], classes[-1]
        target = first if agent["parking_preference"] == "first" else last
        scores = []
        for lot in self.parking_lots:
            eligibility = self.graph.nodes[lot].get("permit_eligibility")
            if eligibility and agent.get("parking_permit") not in eligibility:
                continue
            try:
                dist = self._distance(lot, target["building"])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            delay = max(0, self.rng.gauss(5 + 12 * agent["traits"]["commute_friction"], 4))
            scores.append((dist / agent["traits"]["walking_speed_mps"] / 60 + delay * (1 - .5 * agent["traits"]["parking_loyalty"]), lot))
        return min(scores)[1] if scores else self.parking_lots[0]

    def _free_block(self, agent, day, start, end, next_class, study_multiplier, event_counts):
        if end - start < 25:
            return start, agent["state"]["current_location"]
        traits, state = agent["traits"], agent["state"]
        # Scheduled events compete for the same free time and capacity, and
        # students physically walk to and from the event location.
        for event in self.events:
            if event["type"] != "campus_event" or event.get("day") != day or self.rng.random() >= traits["event_interest"]:
                continue
            building = event["building"]
            event_start = int(event["start_time"][:2]) * 60 + int(event["start_time"][3:])
            event_end = int(event["end_time"][:2]) * 60 + int(event["end_time"][3:])
            cap = max(1, round(event["attendance_capacity"] * getattr(self, "capacity_scale", 1.0)))
            key = (day, event["name"])
            attendees = event_counts.setdefault(key, set())
            if len(attendees) >= cap or agent["agent_id"] in attendees:
                continue
            try:
                to_event, _ = self.travel(state["current_location"], building, traits["walking_speed_mps"])
                to_class, _ = self.travel(building, next_class["building"], traits["walking_speed_mps"]) if next_class else (0, [])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            expected_arrival = max(start + to_event, event_start + max(0, self.rng.gauss(10, 15)))
            duration = max(10, self.rng.gauss(45, 20))
            if expected_arrival + duration + to_class <= min(end, event_end):
                arrival = self._walk(agent, building, start, day, "event")
                arrival = max(arrival, expected_arrival)
                leave = min(arrival + duration, event_end)
                if leave + to_class <= end:
                    attendees.add(agent["agent_id"])
                    self._record(self._row(agent, day, arrival, leave, "event", building, building, event=event["name"]))
                    state["current_location"], state["current_activity"] = building, "event"
                    return leave, building
        hunger = state["hunger"]
        weights = [traits["studiousness"] * study_multiplier * state["energy"], traits["sociability"] * state["energy"], hunger, .15 + traits["campus_stay_tendency"]]
        activity = self.rng.choices(["study", "socialize", "meal", "rest"], weights=weights, k=1)[0]
        if activity == "rest":
            return start, state["current_location"]
        mu, sd = {"study": (45 + 30 * traits["studiousness"], 20), "socialize": (30 + 30 * traits["sociability"], 15), "meal": (30, 10)}[activity]
        duration = max(10, self.rng.gauss(mu, sd))
        if activity == "meal":
            preferred = min(15 * 60, max(12 * 60, self.rng.gauss(13.5 * 60, 75 * (1 - .7 * traits["meal_regularness"]))))
            start = max(start, preferred)
            duration = min(duration, end - start)
        candidates = []
        for building in self.buildings:
            try:
                to_place, _ = self.travel(state["current_location"], building, traits["walking_speed_mps"])
                from_place, _ = self.travel(building, next_class["building"], traits["walking_speed_mps"]) if next_class else (0, [])
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                continue
            planned_start = start + to_place
            planned_end = planned_start + duration
            if planned_end + from_place + 5 <= end:
                if not self._seat_available(day, building, planned_start, planned_end):
                    continue
                weight = math.exp(-to_place / max(1, (1 - traits["route_consistency"]) * 15 + 6))
                if building == state["current_location"]:
                    weight *= 2
                candidates.append((building, weight))
        if not candidates:
            return start, state["current_location"]
        destination = self.rng.choices([x[0] for x in candidates], weights=[x[1] for x in candidates], k=1)[0]
        arrive = self._walk(agent, destination, start, day, activity)
        actual_duration = min(duration, end - arrive - 5)
        if actual_duration <= 0:
            return arrive, destination
        self._record(self._row(agent, day, arrive, arrive + actual_duration, activity, destination, destination))
        self._reserve_seat(day, destination, arrive, arrive + actual_duration)
        state["hunger"] = min(1, hunger + .05) if activity != "meal" else max(0, hunger - .7)
        state["energy"] = max(0, state["energy"] - .08 if activity == "study" else state["energy"] - .03)
        return arrive + actual_duration, destination

    @staticmethod
    def _minute_range(start, end):
        first = max(0, min(1439, int(start)))
        stop = max(first + 1, min(1440, math.ceil(end)))
        return range(first, stop)

    def _seat_available(self, day, building, start, end):
        occupancy = self.seat_reservations.get((day, building))
        return occupancy is None or all(occupancy[minute] < self.seat_capacity for minute in self._minute_range(start, end))

    def _reserve_seat(self, day, building, start, end):
        occupancy = self.seat_reservations.get((day, building))
        if occupancy is None:
            occupancy = self.seat_reservations[(day, building)] = array("H", [0]) * 1440
        for minute in self._minute_range(start, end):
            occupancy[minute] += 1

    def run(self, days=112):
        event_counts = {}
        for agent in self.population:
            self.archetypes_seen.add(agent["archetype_name"])
            by_day = {day: sorted([m for m in agent["schedule"] if m["day"] == day], key=lambda m: m["start_time"]) for day in DAYS}
            active_days = [d for d in DAYS if by_day[d]]
            if not active_days:
                if self.agent_callback is not None:
                    self.agent_callback(agent)
                continue
            self.active_agents += 1
            weekly_classes = sorted(agent["schedule"], key=lambda m: (DAYS.index(m["day"]), m["start_time"]))
            agent["parking_lot"] = self._parking_choice(agent, weekly_classes)
            for day_number in range(days):
                weekday = day_number % 7
                if weekday >= 5:
                    continue
                day_name = DAYS[weekday]
                classes = by_day[day_name]
                if not classes:
                    continue
                state = agent["state"]
                state.update(current_location=agent["parking_lot"], destination=None, current_activity="parking")
                first = classes[0]
                first_start = int(first["start_time"][:2]) * 60 + int(first["start_time"][3:])
                parking_delay = max(0, self.rng.gauss(5 + 12 * agent["traits"]["commute_friction"], 4))
                walk_to_first, _ = self.travel(agent["parking_lot"], first["building"], agent["traits"]["walking_speed_mps"])
                target_arrival = first_start - agent["traits"]["punctuality"] * 12
                campus_arrival = target_arrival - walk_to_first - parking_delay + self.rng.gauss(0, 8)
                now = max(4 * 60, campus_arrival + parking_delay)
                study_multiplier, _ = self._exam_modifiers(day_number)
                for index, meeting in enumerate(classes):
                    start = int(meeting["start_time"][:2]) * 60 + int(meeting["start_time"][3:])
                    end = int(meeting["end_time"][:2]) * 60 + int(meeting["end_time"][3:])
                    if start < now:
                        continue
                    attended, study_multiplier = self._attends(agent, day_number)
                    punctuality = agent["traits"]["punctuality"]
                    target = start - punctuality * 12 + self.rng.gauss(0, 5)
                    travel, _ = self.travel(state["current_location"], meeting["building"], agent["traits"]["walking_speed_mps"])
                    arrive_at = max(now + travel, target)
                    if arrive_at > start + 10:
                        attended = False
                    if attended:
                        state["destination_floor"] = meeting.get("floor") or 0
                        arrive_at = self._walk(agent, meeting["building"], now, day_number, "class")
                        class_arrival = arrive_at if index == 0 else max(arrive_at, start - punctuality * 12 + self.rng.gauss(0, 5))
                        self._record(self._row(agent, day_number, class_arrival, end + self.rng.gauss(0, 3), "class", meeting["building"], meeting["building"], section_id=meeting["section_id"]))
                        state.update(current_location=meeting["building"], current_floor=meeting.get("floor") or 0, current_activity="class")
                        now = end + max(-3, self.rng.gauss(0, 3))
                    else:
                        state["current_activity"] = "free"
                        now = max(now, start)
                    next_class = classes[index + 1] if index + 1 < len(classes) else None
                    until = (int(next_class["start_time"][:2]) * 60 + int(next_class["start_time"][3:])) if next_class else end + 90
                    now, _ = self._free_block(agent, day_number, now, until, next_class, study_multiplier, event_counts)
                last = classes[-1]
                if now < 22 * 60:
                    stay = max(0, self.rng.gauss((30 if agent["commuter_tag"]["type"] == "commuter" else 90) + 60 * agent["traits"]["sociability"] + 45 * agent["traits"]["campus_stay_tendency"] - 30 * agent["traits"]["leave_campus_tendency"], 20))
                    now, _ = self._free_block(agent, day_number, now, min(22 * 60, now + stay), None, study_multiplier, event_counts)
                    now = self._walk(agent, agent["parking_lot"], now, day_number, "parking")
                    self._record(self._row(agent, day_number, now, now + 1, "depart", agent["parking_lot"], "off_campus"))
                    state.update(current_location=None, destination=None, current_activity="off_campus")
            if self.agent_callback is not None:
                self.agent_callback(agent)
        return self.log
