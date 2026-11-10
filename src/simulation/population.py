"""Create seeded students with fixed, normally varied archetype traits and real schedules."""
from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHETYPES_PATH = Path(__file__).with_name("archetypes.json")
TRAITS = ("attendance", "punctuality", "studiousness", "sociability", "leave_campus_tendency", "route_consistency", "meal_regularness", "class_skip_tendency", "campus_stay_tendency", "event_interest", "study_spike_response", "commute_friction", "parking_loyalty")
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def _minutes(value):
    hour, minute = map(int, value.split(":"))
    return hour * 60 + minute


def iter_population(count, sections, seed=42, max_courses=5):
    rng = random.Random(seed)
    archetypes = json.loads(ARCHETYPES_PATH.read_text(encoding="utf-8"))["archetypes"]
    if len(archetypes) != 20 or abs(sum(a["population_weight"] for a in archetypes) - 1.0) > 1e-9:
        raise ValueError("archetypes.json must define 20 archetypes whose weights sum to 1.0")
    grouped = {}
    for meeting in sections:
        grouped.setdefault(meeting["section_id"], []).append(meeting)
    course_options = list(grouped.values())
    weights = [a["population_weight"] for a in archetypes]
    for student_id in range(1, count + 1):
        archetype = rng.choices(archetypes, weights=weights, k=1)[0]
        traits = {key: min(1.0, max(0.0, rng.gauss(archetype["traits"][key], .10))) for key in TRAITS}
        traits["walking_speed_mps"] = min(1.8, max(.8, rng.gauss(archetype["traits"]["walking_speed_mps"], .15)))
        chosen = []
        occupied = {day: [] for day in DAYS}
        target_courses = rng.randint(3, max_courses)
        selected_courses = 0
        selected_ids = set()
        attempts = 0
        while selected_courses < target_courses and attempts < target_courses * 50:
            attempts += 1
            course_meetings = course_options[rng.randrange(len(course_options))]
            section_id = course_meetings[0]["section_id"]
            if section_id in selected_ids:
                continue
            conflicts = False
            for section in course_meetings:
                day = section["day"]
                start, end = _minutes(section["start_time"]), _minutes(section["end_time"])
                if any(start < right and end > left for left, right in occupied[day]):
                    conflicts = True
                    break
            if conflicts:
                continue
            chosen.extend(course_meetings)
            for section in course_meetings:
                occupied[section["day"]].append((_minutes(section["start_time"]), _minutes(section["end_time"])))
            selected_ids.add(section_id)
            selected_courses += 1
        schedule = sorted(chosen, key=lambda m: (DAYS.index(m["day"]), m["start_time"]))
        yield {"agent_id": student_id, "archetype_name": archetype["archetype_name"], "commuter_tag": dict(archetype["commuter_tag"]), "traits": traits, "schedule": schedule,
                         "state": {"current_location": None, "destination": None, "current_activity": "off_campus", "hunger": rng.uniform(.1, .3), "energy": rng.uniform(.7, 1.0)},
                         "parking_lot": None, "parking_preference": "first" if rng.random() < .5 else "last",
                         "parking_permit": rng.choices(["green", "gold", "orange", "purple"], weights=[48, 40, 10, 2], k=1)[0]}


def make_population(count, sections, seed=42, max_courses=5):
    """List-returning convenience wrapper; use iter_population for large runs."""
    return list(iter_population(count, sections, seed=seed, max_courses=max_courses))
