"""Writes archetypes.json: 20 tagged student archetypes (no LLM needed; edit the table to tune).
Trait order: attendance, punctuality, studiousness, sociability, walking_speed_mps, leave_campus_tendency,
route_consistency, meal_regularness, class_skip_tendency, campus_stay_tendency, event_interest,
study_spike_response, commute_friction, parking_loyalty"""
import json
from pathlib import Path

KEYS = ["attendance", "punctuality", "studiousness", "sociability", "walking_speed_mps",
        "leave_campus_tendency", "route_consistency", "meal_regularness", "class_skip_tendency",
        "campus_stay_tendency", "event_interest", "study_spike_response", "commute_friction",
        "parking_loyalty"]

# (name, tag, type, weight, description, traits...)
TABLE = [
    ("Grind Commuter", "COM-GRIND", "commuter", 0.07, "Never misses class, studies hard between lectures, sticks around campus.",
     (.96, .85, .92, .25, 1.35, .30, .85, .65, .04, .60, .30, .90, .55, .85)),
    ("Class-and-Out Commuter", "COM-DASH", "commuter", 0.08, "Arrives for class and leaves the minute it ends.",
     (.88, .70, .45, .20, 1.50, .85, .80, .60, .10, .10, .15, .50, .75, .80)),
    ("Late Rusher Commuter", "COM-LATE", "commuter", 0.06, "Chronically late, fast walker, sprints between buildings.",
     (.80, .20, .50, .35, 1.55, .55, .55, .50, .22, .30, .25, .55, .70, .55)),
    ("Social Commuter", "COM-SOCIAL", "commuter", 0.05, "Drives in to see friends; lingers in common areas.",
     (.82, .60, .40, .90, 1.40, .35, .45, .70, .18, .80, .65, .45, .55, .60)),
    ("Working Commuter", "COM-WORK", "commuter", 0.06, "Holds a job; tight on time, leaves campus quickly.",
     (.78, .65, .45, .25, 1.45, .90, .85, .40, .15, .10, .10, .40, .90, .90)),
    ("Library Commuter", "COM-LIB", "commuter", 0.05, "Treats campus seating as an office; studies for hours.",
     (.92, .75, .95, .20, 1.25, .25, .90, .55, .06, .85, .20, .95, .60, .85)),
    ("Night Owl Commuter", "COM-NIGHT", "commuter", 0.04, "Late riser, irregular meals, stays late.",
     (.65, .30, .60, .40, 1.30, .40, .40, .35, .35, .65, .30, .70, .60, .50)),
    ("Quiet Transfer Commuter", "COM-QUIET", "commuter", 0.05, "Routine-driven, keeps to themselves, same route daily.",
     (.90, .80, .70, .15, 1.30, .60, .90, .60, .08, .35, .10, .65, .65, .90)),
    ("Active Event Commuter", "COM-EVENT", "commuter", 0.04, "Goes to every campus event and fair.",
     (.80, .55, .45, .75, 1.55, .40, .40, .55, .20, .65, .90, .45, .55, .55)),
    ("Capstone Senior Commuter", "COM-SENIOR", "commuter", 0.05, "Upper-level student with a focused, moderate routine.",
     (.85, .70, .80, .45, 1.40, .50, .80, .55, .12, .55, .45, .75, .55, .80)),
    ("Skip-Prone Commuter", "COM-SKIP", "commuter", 0.04, "Frequently skips class; unpredictable schedule.",
     (.45, .35, .30, .50, 1.40, .70, .50, .35, .55, .30, .35, .40, .70, .50)),
    ("Club Officer Commuter", "COM-CLUB", "commuter", 0.05, "Punctual, social, runs organizations and attends events.",
     (.86, .80, .60, .80, 1.45, .30, .55, .75, .10, .80, .80, .60, .50, .65)),
    ("Cramming Commuter", "COM-CRAM", "commuter", 0.06, "Coasts, then studies intensely around exams.",
     (.70, .45, .55, .40, 1.35, .55, .55, .45, .28, .50, .30, .98, .60, .65)),
    ("Studious Dormer", "DORM-STUDY", "dormer", 0.05, "Lives nearby, camps in study spots, rarely leaves.",
     (.94, .80, .90, .35, 1.35, .15, .80, .75, .05, .85, .35, .90, .20, .70)),
    ("Social Dormer", "DORM-SOCIAL", "dormer", 0.06, "Campus is their social life; always hanging out.",
     (.78, .55, .35, .95, 1.40, .10, .40, .80, .20, .95, .75, .40, .15, .50)),
    ("Freshman Explorer Dormer", "DORM-FRESH", "dormer", 0.05, "New to campus, curious, goes to everything.",
     (.88, .70, .55, .70, 1.35, .15, .30, .70, .12, .80, .85, .55, .15, .45)),
    ("Homebody Dormer", "DORM-HOME", "dormer", 0.03, "Goes back to the room between classes.",
     (.75, .60, .50, .20, 1.25, .75, .85, .65, .22, .20, .15, .55, .20, .85)),
    ("Night Gamer Dormer", "DORM-NIGHT", "dormer", 0.04, "Up late, skips mornings, irregular meals.",
     (.58, .25, .35, .55, 1.20, .35, .45, .30, .40, .70, .30, .55, .15, .40)),
    ("Active Athlete Dormer", "DORM-ACTIVE", "dormer", 0.04, "Fast walker, regular meals, social and active.",
     (.84, .75, .45, .80, 1.60, .20, .55, .80, .12, .75, .70, .50, .20, .60)),
    ("Event Hopper Dormer", "DORM-EVENT", "dormer", 0.03, "Lives for campus events and club nights.",
     (.76, .50, .40, .85, 1.45, .15, .35, .60, .20, .90, .95, .45, .15, .45)),
]

PLACEHOLDER_SCHEDULE = [
    {"section_id": "cs2336.001.26s", "day": "Monday", "start_time": "10:00", "end_time": "11:15",
     "building": "ECSW", "floor": 2, "room": "225"},
    {"section_id": "math2418.001.26s", "day": "Monday", "start_time": "13:00", "end_time": "14:15",
     "building": "SCI", "floor": 2, "room": "225"},
]


def build():
    out = []
    for i, (name, tag, typ, w, desc, tr) in enumerate(TABLE, 1):
        assert len(tr) == len(KEYS), name
        out.append({
            "archetype_name": name, "archetype_tag": tag, "archetype_description": desc,
            "population_weight": w,
            "agent_id": i,
            "commuter_tag": {"type": typ, "parking_permit": "gold"},
            "schedule": PLACEHOLDER_SCHEDULE,
            "traits": dict(zip(KEYS, tr)),
            "state": {"current_location": None, "destination": None, "current_activity": "off_campus",
                      "hunger": 0.20, "energy": 0.85},
        })
    total = sum(a["population_weight"] for a in out)
    assert abs(total - 1.0) < 1e-9, total
    assert len({a["archetype_tag"] for a in out}) == 20
    commuter_w = sum(a["population_weight"] for a in out if a["commuter_tag"]["type"] == "commuter")
    print(f"20 archetypes, weights sum {total:.3f}, commuters {commuter_w:.0%}")
    return {"archetypes": out}


if __name__ == "__main__":
    path = Path(__file__).resolve().parent / "archetypes.json"
    path.write_text(json.dumps(build(), indent=2))
    print("wrote", path)
