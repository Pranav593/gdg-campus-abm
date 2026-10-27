import json
import math
import pickle
import random
from pathlib import Path
import mesa
import networkx as nx


REPO_ROOT = Path(__file__).resolve().parents[2]
GRAPH_PATH = REPO_ROOT / "utd-graph" / "utd_graph.pkl"


def find_courses_file():
    """Search the repo (skipping .venv) for spring_2026_courses.json."""
    for p in REPO_ROOT.rglob("spring_2026_courses.json"):
        if ".venv" not in p.parts:
            return p
    return REPO_ROOT / "data" / "spring_2026_courses.json"


_known = REPO_ROOT / "data" / "coursebook" / "processed" / "spring_2026_courses.json"
COURSES_PATH = _known if _known.exists() else find_courses_file()

# ---------------------------------------------------------------------------
# Campus places (graph node names).  >>> CHECK THESE AGAINST YOUR GRAPH <<<
# main() prints a warning + suggestions if any of them is not a node.
# ---------------------------------------------------------------------------
LIBRARY_NODE = "MC"            # McDermott Library
STUDENT_UNION_NODE = "SU"      # Student Union
DINING_HALL_WEST_NODE = "DHW"  # Dining Hall West

PLACE_NAMES = {
    LIBRARY_NODE: "the library",
    STUDENT_UNION_NODE: "the Student Union",
    DINING_HALL_WEST_NODE: "Dining Hall West",
}
MEAL_VENUE_NODES = [STUDENT_UNION_NODE, DINING_HALL_WEST_NODE]
STAY_VENUE_NODES = [LIBRARY_NODE, STUDENT_UNION_NODE]
PLACE_HINTS = {LIBRARY_NODE: ["MC", "LIB"], STUDENT_UNION_NODE: ["SU", "UNION"],
               DINING_HALL_WEST_NODE: ["DH", "DIN", "WEST"]}


STEP_SECONDS = 5                 # one step = 10 simulated seconds
WALK_SPEED_M_PER_S = 1.4          # typical walking speed
DEFAULT_EDGE_LENGTH_M = 50.0      # fill-in value when an edge has no "length"
DAY_START = 7 * 3600              # sim day runs 7:00 AM ...
DAY_END = 21 * 3600               # ... to 9:00 PM (seconds since midnight)
LEAVE_BUFFER_S = 60               # leave this many seconds earlier than strictly needed
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DAYS_TO_RUN = 5                   # how many days main() simulates
PRINT_EVERY_STEP = False          # True = print the status line every 10 sim seconds
                                  # False = print only when the status changes

# --- dorm trips (fill-in values until we have real commute data) ---
COMMUTE_S = 8 * 60                # one-way trip between campus and dorm
HOME_MIN_S = 20 * 60              # must be able to spend at least this long at the dorm
ARRIVE_EARLY_S = 20 * 60          # each morning the student shows up this long before first class

# --- staying on campus (library / SU) ---
STAY_MIN_S = 20 * 60
STAY_MAX_S = 90 * 60

# --- meals: (window_start, window_end, (min_duration, max_duration)) ---
MEALS = {
    "lunch":  (11 * 3600, 14 * 3600, (25 * 60, 40 * 60)),
    "dinner": (17 * 3600, 19 * 3600 + 1800, (30 * 60, 50 * 60)),
}

DECISION_INTERVAL_S = 10 * 60     # while idle, re-check "should I eat?" this often

IN_CLASS, WALKING, IDLE = "IN_CLASS", "WALKING", "IDLE"
EATING, STAYING, OFF_CAMPUS = "EATING", "STAYING", "OFF_CAMPUS"


def load_graph(path=GRAPH_PATH):
    with open(path, "rb") as f:
        return pickle.load(f)


def to_seconds(t):
    """'10:30' -> 37800"""
    h, m = t.split(":")[:2]
    return int(h) * 3600 + int(m) * 60


def clock(seconds):
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def place(node):
    return PLACE_NAMES.get(node, str(node))


def check_places(graph):
    """Warn about configured venues that are not nodes in the graph."""
    for node, hints in PLACE_HINTS.items():
        if node not in graph:
            guesses = [n for n in graph.nodes if any(h in str(n).upper() for h in hints)][:10]
            print(f"WARNING: '{node}' ({PLACE_NAMES[node]}) is not a node in the graph. "
                  f"Possible matches: {guesses}")


# ---------------------------------------------------------------------------
# Schedule: section IDs from CourseBook (format: prefix+number.section.26s)
# ---------------------------------------------------------------------------
MY_SECTIONS = [
    "engr2300.006.26s",
    "math2414.020.26s",
    "ee1202.310.26s",
    "phys2325.003.26s",
    "math2414.318.26s",
    "phys2125.119.26s",
    "ee1202.001.26s",
]

DAY_ABBR = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri"}


def build_schedule(section_ids, courses_path=None):
    """Look each section up in the CourseBook JSON; every meeting becomes one schedule entry."""
    courses_path = courses_path or COURSES_PATH
    with open(courses_path) as f:
        sections = {s["section_id"].lower(): s for s in json.load(f)}

    schedule = []
    for sid in section_ids:
        s = sections.get(sid.lower())
        if s is None:
            close = [k for k in sections if k.startswith(sid.lower().split(".")[0])][:8]
            raise SystemExit(f"Section '{sid}' not in dataset. Sections for that course: {close}")
        for m in s["meetings"]:
            if m["day"] not in DAY_ABBR:   # skip Sat/Sun/TBA
                continue
            schedule.append({
                "course": f"{s['prefix']} {s['course_number']}.{s['section']}",
                "days": [DAY_ABBR[m["day"]]],
                "start": m["start_time"],
                "end": m["end_time"],
                "building": m["building"],
                "room": f"{m.get('floor', '')}.{m.get('room', '')}",
            })
    return schedule


def validate_schedule(schedule, graph):
    """Checks: buildings exist in the graph, and no two classes overlap."""
    problems = []
    for c in schedule:
        if c["building"] not in graph:
            problems.append(f"{c['course']}: building {c['building']} not in graph")
    for i, a in enumerate(schedule):
        for b in schedule[i + 1:]:
            if set(a["days"]) & set(b["days"]):
                if to_seconds(a["start"]) < to_seconds(b["end"]) and to_seconds(b["start"]) < to_seconds(a["end"]):
                    problems.append(f"overlap: {a['course']} and {b['course']}")
    return problems


class StudentAgent(mesa.Agent):
    def __init__(self, model, schedule, start_building,
                 dorm_return_friction=0.5, campus_stay_tendency=0.4, meal_regularness=0.7,
                 seed=None):
        super().__init__(model)
        self.schedule = schedule
        self.dorm_return_friction = dorm_return_friction
        self.campus_stay_tendency = campus_stay_tendency
        self.meal_regularness = meal_regularness
        self.dice = random.Random(seed)

        self.current_location = start_building   # graph node
        self.state = OFF_CAMPUS                  # each morning starts at the dorm
        self.return_at = 0                       # when an OFF_CAMPUS student is back on campus
        self.return_node = start_building        # where they reappear on campus

        self.route, self.route_index, self.progress_m = [], 0, 0.0
        self.walk = None                         # what the current walk is for
        self.target_class = None
        self.class_ends_at = None
        self.activity = None                     # current meal / stay
        self.activity_ends_at = None

        self.day_seen = -1
        self.will_eat = {}                       # meal -> bool (rolled each morning)
        self.eaten = set()
        self.gap_key, self.gap_plan, self.gap_used = None, {}, {}
        self.next_decision_at = 0

        self.log = []
        self._announced = False
        self._route_cache = {}

    # ---------------- status report ----------------
    def status(self):
        """Human-readable report of what the agent is doing right now."""
        if self.state == OFF_CAMPUS:
            if self.return_at > DAY_END:
                return "OFF CAMPUS (at the dorm for the day)"
            return f"OFF CAMPUS (at the dorm, back on campus ~{clock(self.return_at)})"
        if self.state == IN_CLASS:
            c = self.target_class
            return (f"IN CLASS: {c['course']} in {c['building']} {c['room']} "
                    f"(ends {clock(self.class_ends_at)})")
        if self.state == WALKING:
            w = self.walk
            return (f"WALKING to {w['node']} ({w['label']}), near {self.current_location}, "
                    f"~{self._meters_remaining():.0f} m left")
        if self.state == EATING:
            a = self.activity
            return f"EATING {a['label']} at {place(a['node'])} (until {clock(self.activity_ends_at)})"
        if self.state == STAYING:
            a = self.activity
            return f"STAYING at {place(a['node'])} (until {clock(self.activity_ends_at)})"
        nxt = self._next_class()
        if nxt is None:
            return f"IDLE at {self.current_location} (no more classes today)"
        if nxt["building"] == self.current_location:
            return (f"IDLE at {self.current_location}, waiting for {nxt['course']} "
                    f"(starts {nxt['start']})")
        return (f"IDLE at {self.current_location} (next: {nxt['course']} in "
                f"{nxt['building']} at {nxt['start']})")

    # ---------------- helpers ----------------
    def _todays_classes(self):
        day = self.model.day_name
        return sorted((c for c in self.schedule if day in c["days"]),
                      key=lambda c: to_seconds(c["start"]))

    def _next_class(self):
        now = self.model.time_s
        for c in self._todays_classes():
            if to_seconds(c["end"]) > now:
                return c
        return None

    def _edge_length(self, u, v):
        data = self.model.graph.get_edge_data(u, v) or {}
        if data and "length" not in data:
            data = next(iter(data.values()))       # MultiGraph: first parallel edge
        return float(data.get("length", DEFAULT_EDGE_LENGTH_M))

    def _route_meters(self, route):
        return sum(self._edge_length(u, v) for u, v in zip(route, route[1:]))

    def _meters_remaining(self):
        rest = self.route[self.route_index:]
        return max(self._route_meters(rest) - self.progress_m, 0.0)

    def _route(self, a, b):
        if a == b:
            return [a]
        if (a, b) not in self._route_cache:
            try:
                r = nx.shortest_path(self.model.graph, a, b, weight="length")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                r = None
            self._route_cache[(a, b)] = r
        return self._route_cache[(a, b)]

    def _walk_seconds(self, a, b):
        r = self._route(a, b)
        return None if r is None else self._route_meters(r) / WALK_SPEED_M_PER_S

    def _say(self, msg):
        line = f"[{self.model.day_name} {clock(self.model.time_s)}] {msg}"
        self.log.append(line)
        if self.model.verbose:
            print(line)

    def _set_state(self, new_state, msg=None):
        """Switch state and announce it (IDLE is announced at the end of the step instead)."""
        self.state = new_state
        if new_state != IDLE:
            self._say(msg or self.status())
            self._announced = True

    # ---------------- daily reset ----------------
    def _new_day(self):
        self.day_seen = self.model.day_index
        self.eaten = set()
        self.will_eat = {m: self.dice.random() < self.meal_regularness for m in MEALS}
        self.gap_key, self.gap_plan, self.gap_used = None, {}, {}
        self.next_decision_at = 0
        self.walk = self.activity = self.target_class = None
        self.state = OFF_CAMPUS
        classes = self._todays_classes()
        if classes:                                  # shows up shortly before the first class
            self.return_node = classes[0]["building"]
            self.return_at = max(DAY_START, to_seconds(classes[0]["start"]) - ARRIVE_EARLY_S)
        else:
            self.return_at = DAY_END + 1             # no classes today: stays home

    # ---------------- behavior ----------------
    def step(self):
        self._announced = False
        now = self.model.time_s
        if self.day_seen != self.model.day_index:
            self._new_day()
        before = self.state

        # --- things that end ---
        if self.state == IN_CLASS and now >= self.class_ends_at:
            self.state, self.target_class = IDLE, None
            self.next_decision_at = 0
        elif self.state in (EATING, STAYING) and now >= self.activity_ends_at:
            self.state, self.activity = IDLE, None
            self.next_decision_at = 0
        elif self.state == OFF_CAMPUS and now >= self.return_at:
            self.current_location = self.return_node
            self._say(f"RETURNED to campus at {self.current_location}")
            self.state = IDLE
            self.next_decision_at = 0

        # --- things that happen ---
        if self.state == WALKING:
            self._walk()
        elif self.state == IDLE:
            self._plan(now)

        # --- report ---
        if not self._announced and ((self.state == IDLE and before != IDLE) or PRINT_EVERY_STEP):
            self._say(self.status())

    def _plan(self, now):
        nxt = self._next_class()

        # New gap (time until the next class / end of day) -> roll its personality dice once.
        key = (self.model.day_index, nxt["course"], nxt["start"]) if nxt else (self.model.day_index, "EOD")
        if key != self.gap_key:
            self.gap_key = key
            self.gap_plan = {"home": self.dice.random() < (1 - self.dorm_return_friction),
                             "stay": self.dice.random() < self.campus_stay_tendency}
            self.gap_used = {"home": False, "stay": False}
            self.next_decision_at = 0

        if now >= self.next_decision_at:
            self.next_decision_at = now + DECISION_INTERVAL_S
            if self._try_activities(nxt, now):
                return

        if nxt is None:
            return
        dest = nxt["building"]
        if dest == self.current_location:
            if now >= to_seconds(nxt["start"]):
                self._enter_class(nxt)
            return                                       # else: already there, waiting (IDLE)

        route = self._route(self.current_location, dest)
        if route is None:
            return
        leave_at = (to_seconds(nxt["start"])
                    - math.ceil(self._route_meters(route) / WALK_SPEED_M_PER_S) - LEAVE_BUFFER_S)
        if now >= leave_at:
            self.target_class = nxt
            self.walk = {"kind": "class", "node": dest, "label": f"{nxt['course']} class", "class": nxt}
            self.route, self.route_index, self.progress_m = route, 0, 0.0
            self._set_state(WALKING)
            self._walk()

    # ---------------- optional activities during gaps ----------------
    def _spare_seconds(self, nxt, node, now):
        """Free time left if we walk to `node` now and still reach the next class on time."""
        to = self._walk_seconds(self.current_location, node)
        if to is None:
            return None
        if nxt is None:
            return DAY_END - now - to
        back = self._walk_seconds(node, nxt["building"])
        if back is None:
            return None
        return to_seconds(nxt["start"]) - now - to - back - LEAVE_BUFFER_S

    def _try_activities(self, nxt, now):
        model = self.model

        # 1) meals (lunch / dinner) -- only inside the meal window, only if they'd eat today
        for meal, (w0, w1, (dmin, dmax)) in MEALS.items():
            if meal in self.eaten or not self.will_eat.get(meal) or not (w0 <= now < w1):
                continue
            venues = list(model.meal_venues)
            self.dice.shuffle(venues)
            dur = self.dice.randint(dmin, dmax)
            for v in venues:
                spare = self._spare_seconds(nxt, v, now)
                if spare is not None and spare >= dur:
                    self.eaten.add(meal)
                    self._start_trip("meal", v, meal, dur)
                    return True

        # 2) go back to the dorm (low dorm_return_friction => more likely)
        if self.gap_plan.get("home") and not self.gap_used["home"]:
            self.gap_used["home"] = True
            if self._go_home(nxt, now):
                return True

        # 3) hang out at the library / SU (campus_stay_tendency)
        if self.gap_plan.get("stay") and not self.gap_used["stay"] and model.stay_venues:
            self.gap_used["stay"] = True
            v = self.dice.choice(model.stay_venues)
            spare = self._spare_seconds(nxt, v, now)
            if spare is not None and spare >= STAY_MIN_S:
                dur = min(self.dice.randint(STAY_MIN_S, STAY_MAX_S), int(spare))
                self._start_trip("stay", v, "stay", dur)
                return True
        return False

    def _go_home(self, nxt, now):
        if nxt is None:
            self.return_at = DAY_END + 1
            msg = f"LEAVING CAMPUS: heading to the dorm from {self.current_location} for the day"
        else:
            walk_s = self._walk_seconds(self.current_location, nxt["building"]) or 0
            return_at = to_seconds(nxt["start"]) - math.ceil(walk_s) - LEAVE_BUFFER_S
            if return_at - now < 2 * COMMUTE_S + HOME_MIN_S:     # gap too short for a trip home
                return False
            self.return_at = return_at
            msg = (f"LEAVING CAMPUS: heading to the dorm from {self.current_location} "
                   f"(back on campus ~{clock(return_at)})")
        self.return_node = self.current_location
        self._set_state(OFF_CAMPUS, msg)
        return True

    def _start_trip(self, kind, node, label, duration):
        route = self._route(self.current_location, node)
        self.walk = {"kind": kind, "node": node, "label": label, "duration": duration}
        self.route, self.route_index, self.progress_m = route, 0, 0.0
        if len(route) == 1:                       # already there
            self._arrive()
        else:
            self._set_state(WALKING)
            self._walk()

    # ---------------- movement ----------------
    def _walk(self):
        budget = WALK_SPEED_M_PER_S * STEP_SECONDS       # meters we can cover this step
        while budget > 0 and self.route_index < len(self.route) - 1:
            u, v = self.route[self.route_index], self.route[self.route_index + 1]
            remaining = self._edge_length(u, v) - self.progress_m
            if budget >= remaining:
                budget -= remaining
                self.route_index += 1
                self.progress_m = 0.0
                self.current_location = v
            else:
                self.progress_m += budget
                budget = 0
        if self.route_index >= len(self.route) - 1:
            self._arrive()

    def _arrive(self):
        w, self.walk = self.walk, None
        now = self.model.time_s
        if w["kind"] == "class":
            c = w["class"]
            if now >= to_seconds(c["start"]):
                self._enter_class(c)
            else:
                self.state = IDLE                         # early: wait at the building
        else:
            self.activity = {"kind": w["kind"], "label": w["label"], "node": w["node"]}
            self.activity_ends_at = now + w["duration"]
            self._set_state(EATING if w["kind"] == "meal" else STAYING)

    def _enter_class(self, c):
        self.target_class = c
        self.class_ends_at = to_seconds(c["end"])
        self._set_state(IN_CLASS)


class CampusModel(mesa.Model):
    """1 step = STEP_SECONDS simulated seconds. Runs Mon-Fri, DAY_START..DAY_END each day."""

    def __init__(self, graph, verbose=True):
        super().__init__()
        self.graph = graph
        self.verbose = verbose
        self.day_index = 0
        self.time_s = DAY_START
        self.meal_venues = [n for n in MEAL_VENUE_NODES if n in graph]
        self.stay_venues = [n for n in STAY_VENUE_NODES if n in graph]
        self.history = []        # (day, time_s, building, state) per agent per step, for analysis later

    @property
    def day_name(self):
        return DAYS[self.day_index % len(DAYS)]

    def occupancy(self):
        """Students physically inside each building right now (not walking, not off campus)."""
        counts = {}
        for a in self.agents:
            if a.state not in (WALKING, OFF_CAMPUS):
                counts[a.current_location] = counts.get(a.current_location, 0) + 1
        return counts

    def step(self):
        self.agents.do("step")
        for a in self.agents:
            self.history.append((self.day_name, self.time_s, a.current_location, a.state))
        self.time_s += STEP_SECONDS
        if self.time_s >= DAY_END:
            self.time_s = DAY_START
            self.day_index += 1
            if self.verbose and self.day_index < DAYS_TO_RUN:
                print(f"\n===== {self.day_name} =====")


if __name__ == "__main__":
    G = load_graph()
    check_places(G)
    MY_SCHEDULE = build_schedule(MY_SECTIONS)

    problems = validate_schedule(MY_SCHEDULE, G)
    if problems:
        for p in problems:
            print("PROBLEM:", p)
        raise SystemExit(1)

    model = CampusModel(G)
    student = StudentAgent(
        model, MY_SCHEDULE, start_building=MY_SCHEDULE[0]["building"],
        dorm_return_friction=0.5,   # 0 = always goes home in a long gap, 1 = never
        campus_stay_tendency=0.4,   # chance a gap is spent at the library / SU
        meal_regularness=0.7,       # chance of eating lunch / dinner on a given day
        seed=42,                    # change (or set None) for different behavior
    )
    print(f"===== {model.day_name} =====")

    steps_per_day = (DAY_END - DAY_START) // STEP_SECONDS
    for _ in range(DAYS_TO_RUN * steps_per_day):
        model.step()