# gdg-campus-abm
Agent-based UTD digital twin to simulate semester-long campus activity and predict location demand with regression.

## Campus metadata

The current mapping pipeline is in `src/mapping/utd-graph`; `utd-graph` retains
the academic map variant. Both support the same complete simulation graph:

```powershell
python src/mapping/utd-graph/build_simulation_graph.py
python scripts/test_mapping.py
```

See `src/mapping/utd-graph/README.md` for distance units, floor and capacity
provenance, unknown values, and generated CSV schemas.

## Scheduled student simulation (Mesa)

Run from the repository root in PowerShell. Mesa 3.5.1 was used for verification.
The minimal runtime is Mesa 3, NetworkX and Shapely (needed to load this graph's
geometry objects). The full requirements file also includes optional scraping,
analytics and notebook packages.

```powershell
# Optional: create a project environment, then activate it
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install "mesa>=3,<4" networkx shapely
python -c "import mesa; print(mesa.__version__)"

# Run four fictional student schedules from Housing and PS1/PS3/PS4
python -m src.simulation.run --start 08:00 --end 13:00 --output simulation_output/events.csv

# Simulation regression tests; mapping tests
python -m unittest discover -s tests -p "test_*.py"
python scripts/test_mapping.py
```

On macOS/Linux, activate with `source .venv/bin/activate` instead. If the existing
Python environment already has these packages, the demo can run directly without
creating a new environment. To install all project dependencies, use
`python -m pip install -r requirements.txt`.

The default graph is `src/mapping/utd-graph/utd_simulation_graph.pkl`, resolved
relative to the package. The default schedules are in
`data/demo_student_schedules.json`. These are fictional demonstrations, not
actual course offerings or student enrollment. Override them with `--schedule`;
each student's record contains `student_id`, `initial_location`, a `classes`
array, and optionally `walking_speed_m_s`. Each class supplies `destination`,
`start`, `end` (HH:MM or numeric minutes), and an optional `course` label.
Schedules are sorted; overlapping classes, duplicate IDs, closed/unknown
buildings, missing directed routes and invalid numbers fail before a partial
simulation starts. Empty schedules are allowed.

Other options are `--graph`, `--step-minutes` (default 1), `--speed-m-s` (1.4),
`--arrival-buffer-minutes` (0), `--fallback-distance-m` (10) and `--seed` (42).
The CLI uses HH:MM for start/end flags. The Python model accepts fractional
minutes and supports a partial final interval.

`CampusModel` maintains `current_minute`, the authoritative clock in minutes
from midnight, and calls its Mesa agents every tick. Mesa's own step/time fields
track activation ticks; they are not wall-clock minutes. `StudentAgent` waits,
walks edge by edge, waits for class, attends, then chooses the next class.
Walking uses distance_m (or legacy length) divided by the student's speed;
parallel edges and shortest-path calculations use the same canonical meter
weight. Missing distances explicitly use the configured fallback and are counted
in the summary. Malformed, negative and nonfinite distances are rejected.
Current enriched-graph demo routes need no fallback values.

Students depart early enough to arrive at class start, minus an optional arrival
buffer. Those starting late attend the remainder of a class where possible.
If class ends during a trip, the student records a missed class, finishes the
current edge, and selects the next class from its reached node. Travel, arrivals
and attendance retain fractional times, and results are invariant to reasonable
tick-size changes. Boundary transitions at an interval's end are settled without
consuming time after that endpoint. While walking, current_location is the last
reached graph node; current_edge and remaining_edge_distance_m describe progress.

The CSV records departure, arrival, class_start, class_end, missed_class and
finished events. time_minute preserves numeric precision, clock_time displays
HH:MM:SS.mmm, and student_id, location, destination, course and lateness_minutes
identify the transition. Arrival events are emitted for completed journeys to an
active target; abandoned routes produce a missed-class event and finish their
current edge without claiming arrival at the abandoned destination. Events are
sorted by time with stable ordering for simultaneous transitions.

The terminal summary reports students, completed and missed classes, late
arrivals, actual distance walked and fallback edges. Late arrivals count late
attendance starts, including a student already at the class location at startup.
It does not count a completely missed class as a late attendance.

This is a one-day terminal simulation. It does not enforce occupancy or parking
permit limits, simulate driving, generate enrollment, or animate the static
browser map. Students starting at a garage are already parked; Housing is the
existing generic representative node. Existing graph capacity/permit metadata
is available for later features.

Numerical limits: a tick too small to advance the floating-point minute clock
raises a descriptive error instead of looping. Edge durations below clock
precision complete at the current representable time while consuming their full
distance. Later class deadlines continue to produce missed-class events at their
actual deadlines while a student finishes an abandoned edge.

The CLI also prints a per-class student report with departure/arrival clocks,
simulated walking minutes, ON TIME/LATE/PENDING/MISSED arrival status and
COMPLETED/IN CLASS/WAITING/WALKING/PENDING/MISSED class status. Early counts as
on time; unfinished or missed journeys mark elapsed walking minutes with *.
A separate execution timer reports real seconds, including setup/export, and
the simulation-loop portion. CSV event fields are unchanged.
