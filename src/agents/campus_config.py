"""Shared constants, seating data, parking data. EDIT THE >>> CHECK <<< SECTIONS FOR YOUR GRAPH."""
from pathlib import Path

try:
    REPO_ROOT = Path(__file__).resolve().parents[2]
except IndexError:
    REPO_ROOT = Path(__file__).resolve().parent

# Consolidated verified graph: academic additions + named parking from src/mapping,
# plus the Student Union connector retained from the earlier verified graph.
GRAPH_PATH = REPO_ROOT / "src" / "mapping" / "utd-graph" / "utd_graph_simulation.pkl"
_known = REPO_ROOT / "data" / "coursebook" / "processed" / "spring_2026_courses.json"
COURSES_PATH = _known
HERE = Path(__file__).resolve().parent
ARCHETYPES_PATH = HERE / "archetypes.json"
EVENTS_PATH = HERE / "events.json"

# ---------------------------------------------------------------- scale
TOTAL_STUDENTS = 30_000          # 15k agents at 2:1
SCALE_RATIO = 2                  # real students per agent (CLI --scale overrides)

# ---------------------------------------------------------------- time
STEP_SECONDS = 15                # smaller = smoother walking, slower runs
DAY_START = 6 * 3600
DAY_END = 23 * 3600
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
TOTAL_SEMESTER_DAYS = 75         # 15 weeks x 5 school days. events.json days are 0-based school days.
SNAPSHOT_S = 5 * 60              # occupancy snapshot interval
OUTPUT_SCHEMA_VERSION = "2.0"
CONFIG_VERSION = "enrollment-aware-2026-11"

# ---------------------------------------------------------------- movement
DEFAULT_EDGE_LENGTH_M = 50.0
FLOOR_SECONDS = 30               # per floor traveled (spec)
LEAVE_BUFFER_S = 60

# ---------------------------------------------------------------- bell curves (all seconds unless noted)
TRAIT_STD = 0.10                 # ~95% of agents within +-0.20 of archetype base
WALK_STD = 0.15
MAX_EARLY_S = 15 * 60            # punctuality 1.0 -> aims to arrive this early
PUNCT_NEUTRAL = 0.35             # punctuality at/below this -> arrives at start time or late
CLASS_ARRIVAL_STD_S = 3 * 60
CLASS_EXIT_STD_S = 2.5 * 60
BASE_PARKING_DELAY_S = 6 * 60
PARKING_STD_S = 3 * 60
ARRIVAL_STD_S = 5 * 60

# ---------------------------------------------------------------- meals (hours of day)
MEALS = {
    "lunch":  dict(mean_h=13.5, lo_h=12.0, hi_h=15.0),
    "dinner": dict(mean_h=18.5, lo_h=17.0, hi_h=20.0),
}
BASE_MEAL_STD_H = 1.0            # std = BASE * (1 - 0.7 * meal_regularness)
HUNGER_PER_H = 0.09
ENERGY_DROP_PER_H = 0.05
WALK_ENERGY_DROP_PER_H = 0.03
STUDY_ENERGY_DROP_PER_H = 0.02
IDLE_ENERGY_RECOVERY_PER_H = 0.02
MEAL_ENERGY_RECOVERY_PER_H = 0.04
OFF_CAMPUS_ENERGY_RECOVERY_PER_H = 0.08
HUNGRY_MEAL_THRESHOLD = 0.72

# ---------------------------------------------------------------- free time
MIN_ACTIVITY_S = 10 * 60
DECISION_INTERVAL_S = 10 * 60
LEAVE_MIN_GAP_S = 2 * 3600       # mid-day trips off campus only for gaps at least this long
HOME_MIN_S = 20 * 60
COMMUTE_S = {"commuter": 15 * 60, "dormer": 5 * 60}   # one-way, lot <-> home
ALT_ROUTES = True                # route_consistency picks between shortest and 2nd-shortest path
ALT_ROUTE_MAX_RATIO = 1.25

# ---------------------------------------------------------------- events
EVENT_OVERSUBSCRIBE = 1.5        # interested crowd ~ 1.5 x capacity (the extra get turned away)

# ---------------------------------------------------------------- semester curves (spec 4.9 / 4.10)
EXAM_STD_DAYS = 2.5
DECLINE_RATE = 0.25              # attendance lost by the end of the semester
EXAM_ATTENDANCE_BOOST = 0.12

# ---------------------------------------------------------------- permits (spec: mostly green/gold, fewer orange, few purple)
PERMIT_DISTRIBUTION = {"gold": 0.38, "green": 0.42, "orange": 0.13, "purple": 0.07}
# Which lot zones each permit may park in (ASSUMPTION - edit if UTD rules differ)
PERMIT_ACCESS = {
    "purple": ["purple", "gold", "green", "orange"],
    "gold":   ["gold", "green", "orange"],
    "green":  ["green", "orange"],
    "orange": ["orange"],
}

# Existing, verified graph destinations. Permit zones and delay values remain
# behavioral assumptions; the location/connector data comes from the map.
PARKING_LOTS = {
    "Lot A1":       {"zone": "gold",   "delay_min": 6},
    "Lot B1":       {"zone": "green",  "delay_min": 4},
    "Lot C1":       {"zone": "green",  "delay_min": 4},
    "Lot D":        {"zone": "orange", "delay_min": 2},
    "Lot M North":  {"zone": "gold",   "delay_min": 6},
    "Lot M South":  {"zone": "green",  "delay_min": 4},
    "Lot R":        {"zone": "orange", "delay_min": 2},
    "Lot V":        {"zone": "purple", "delay_min": 2},
}

# ---------------------------------------------------------------- seating (physical discretionary seats; classrooms excluded)
# {graph_node: {floor: seats}}.  Floor 1 is ground unless GROUND_FLOOR says otherwise.
# >>> CHECK: keys must be graph node names. Use NODE_ALIAS to map a key to a different node. <<<
SEATING_FULL = {
    "JO":    {1: 0, 2: 16, 3: 49, 4: 95, 5: 62},     # 1st floor theater access only
    "GR":    {2: 28, 3: 38, 4: 40},                  # 2nd floor is the ground floor
    "JSOM1": {1: 57, 2: 100, 3: 0, 4: 0},
    "JSOM2": {1: 84, 2: 78, 3: 15, 4: 10},
    "HH":    {1: 47},
    "ML1":   {1: 11},
    "ML2":   {1: 18},                                 # 9 x 2
    "PHYA":  {1: 60},                                 # Physics annex
    "AB":    {1: 40},                                 # Activity Center / Rec building (ASSUMED 40, not 60)
    "ACB":   {1: 60},                                 # Activity Center Bookstore
    "AD":    {1: 20, 2: 50, 3: 30},
    "APC":   {1: 100, 2: 0},                          # level 2 is a museum
    "ATC":   {1: 120, 2: 45, 3: 50},
    "ECSN":  {1: 70},
    "ECSS":  {1: 89},
    "ECSW":  {1: 185},
    "FO":    {1: 85},                                 # Founders building
    "FA":    {1: 20},                                 # Founders annex
    "FN":    {1: 40},                                 # Founders north
}
# Buildings with no access / zero seats (kept for documentation): North office, North lab, Police, APC2 (construction)
GROUND_FLOOR = {"GR": 2}
# The graph has one JSOM destination.  The two physical seating inventories remain
# distinct in this table and are deliberately aggregated only at the shared map node.
NODE_ALIAS = {"JSOM1": "JSOM", "JSOM2": "JSOM", "PHYA": "PHA"}

# Never give the academic fallback to these locations.  AB and ACB are retained in
# SEATING_FULL, but are not present in the supplied graph, so they are reported rather
# than being assigned invented coordinates or walk links.
INACCESSIBLE_BUILDINGS = {"NB", "NL", "POLICE", "APC2"}
DEFAULT_SEATS_PER_BUILDING = 100


def represented_students(scale_ratio):
    """Number of real students represented by one simulation agent."""
    return max(1, int(scale_ratio))


def to_seconds(t):
    h, m = str(t).split(":")[:2]
    return int(h) * 3600 + int(m) * 60


def clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"
