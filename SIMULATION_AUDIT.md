# Simulation, map, and architecture audit

Audit date: 2026-11-12. Work occurred on `integration/map-seating`; no PR was merged, pushed, or applied to `main`.

## 1. Map comparison

The repository has two duplicated map trees. `src/mapping/utd-graph` is the richer academic/parking build. Cached OSM JSON supplies footprints/metadata only, and CSVs are route exports rather than alternate networks.

| Graph | Nodes / edges / components | Coverage / routing | Verdict |
|---|---:|---|---|
| `utd-graph/utd_graph_original.pkl` | 3,723 / 10,126 / 1 | 26 building destinations incl. SU; connected directed OSM walking graph; no expanded catalog/named lots | Best original connectivity, reduced coverage. |
| `utd-graph/utd_graph_with_parking.pkl` | 3,736 / 10,148 / 3 | 39 destinations, SU and PS1/PS3/PS4; GC/APC2 isolated | Retains SU, fewer academics/lots. |
| `utd-graph/utd_graph.pkl` (old PR #7 default) | 3,732 / 10,140 / 3 | 38 destinations, 36 active academics; no SU/named parking | Inadequate for SU events and real lot arrival. |
| `src/mapping/utd-graph/utd_graph.pkl` | 3,761 / 10,198 / 3 | 67 destinations: 36 active academics plus 29 named lots/residential lots; verified codes/coordinates/floors/entrances when available | Best coverage, but SU removed; directed arcs cause reverse-trip failures. |
| `src/mapping/utd-graph/utd_graph_simulation.pkl` **selected** | 3,762 / 5,105 / 3 | Rich graph + verified SU node/connector from `with_parking`; bidirectional `MultiGraph`; 3,760-node usable component, only closed GC/construction APC2 isolated | Best usable simulation graph. |

`scripts/consolidate_simulation_graph.py` copies the existing verified SU node and connector to walkway `11207111804`; it adds no geometry. It makes existing OSM pedestrian arcs bidirectional for walking. The directed graph produced 233 route fallbacks in a 1,000-agent run; selected graph produced zero. Representative selected shortest routes: SU→ECSW 434.1 m, SU→JSOM 459.9 m, Lot A1→ECSW 900.0 m, Lot M North→JSOM 517.8 m, Res Lot North→SCI 546.5 m. Edges retain lengths; walking time is distance / individual speed + floor time. The regenerated visualization is `src/mapping/utd-graph/utd_routes_simulation.png` with interactive `utd_map.html`.

The map includes parking (`Res Lot North`, `Res Lot North West`) but does not identify or route residence halls as homes. The road/home segment is therefore correctly off-graph, but dormers incorrectly appear at a parking lot. Commuters now select verified named lots and walk from lot to class; their 15-minute road commute remains abstract. CourseBook loading found 1,573 usable pools and excluded 713 online/TBA/unmapped sections. AB/ACB have no verified node, and all active destinations are in the usable component.

## 2. Agent schema audit

| Field | Status / active implementation |
|---|---|
| `agent_id` | Full: stable per-agent random seed and trace identity. |
| `commuter_tag.type` | Full: 15-minute commuter vs 5-minute dormer off-graph travel and stay baseline. |
| `commuter_tag.parking_permit` | Full: randomized permit filters assumed lot zones. |
| Schedule section/day/time/building/floor/room | Full: CourseBook fields preserved; agenda, day filter, floor time and routing use them. |
| `attendance`, `class_skip_tendency` | Full: per-meeting attendance probability. |
| `punctuality` | Full: early-arrival target. |
| `studiousness` | Full: study option weight and duration. |
| `sociability` | Full: social option, duration, and stay length. |
| `walking_speed_mps` | Full: route traversal/time. |
| `leave_campus_tendency`, `commute_friction` | Full: home-break choice and stay length. |
| `route_consistency` | Full: shortest/second-route and repeat-place preference. |
| `meal_regularness` | Full: meal-time variance and meal probability. |
| `campus_stay_tendency` | Full: stay choice and duration. |
| `event_interest` | Full: event interest roll. |
| `study_spike_response` | Full: individual exam study multiplier. |
| `parking_loyalty` | Full: usual-lot retention. |
| State location/destination/activity | Full under `StudentAgent.info`, updated at transitions. |
| State hunger | Partial: daily baseline and dynamic formula affect eating; `info["hunger"]` is not synchronized. |
| State energy | Partial: daily baseline and decline affect leaving; no recovery and `info["energy"]` is not synchronized. |

`load_section_pool` reads CourseBook, rejects any weekday section with missing graph destination/time, and `pick_schedule` samples 2–6 courses while rejecting same-day overlaps. In the 15,000-agent run all 15,000 schedules were nonempty: 741/2 courses, 2,974/3, 5,282/4, 4,485/5, 1,518/6. This is varied but has no major, cohort, level, prerequisite, enrollment, or preferred-time model. Attendance is sampled before travel; late arrival does not turn into a missed class, and class rooms have no capacity.

## 3. Archetypes and state machine

There are 20 manually authored archetypes (`make_archetypes.py` literal `TABLE`), weights sum to 1.0, and largest-remainder allocation gives exact weighted counts. `population.py` samples every unit trait with Gaussian sd 0.10, clamped [0,1], and walking speed with sd 0.15, clamped [0.8,1.8] m/s. Hunger/energy seeds use Gaussian sd 0.08. Every listed trait has a behavior reference; none is decorative. Archetypes remain simplified weights/timing rather than majors, friends, or class cohorts.

Lifecycle: (1) `new_day` samples attendance, Gaussian class arrival/exit, compatible events, meals, and stay time; (2) OFF_CAMPUS waits, appears at lot, then WALKING consumes `speed * 15 s` through route edges; (3) IN_CLASS waits to sampled exit; (4) IDLE evaluates deadline, distance/floor return time, and available seats every 10 minutes; (5) EATING/STUDYING/SOCIALIZING holds/release represented seats after Gaussian, deadline-capped duration; (6) a long gap can go through the lot OFF_CAMPUS and return, while final activity triggers departure. Full locations are skipped for alternatives. Unreachable routing would teleport, but selected-map tests had zero.

Hunger rises 0.09/hour, increases eat weight, and resets to 0.05 after eating. Energy drops 0.05/hour from arrival, increases leave propensity, and does not recover. Attendance is `attendance * (1 - class_skip_tendency) - semester_decline + exam_boost`, clamped; decline reaches 0.25 at day 75. Punctuality changes planned arrival, while commute friction does not affect attendance itself.

Observed day-37 traces: commuter agent 2 (COM-GRIND) moved Lot B1 08:02 → GR class 08:13 → SCI social 09:57 → CR study 10:43 → home break 11:54 → return 13:39 → SU event 13:49 → CR study 14:16 → depart 14:57. Dormer agent 800 (DORM-SOCIAL) moved Lot D 08:48 → ECSS 09:03 → JSOM 10:04 → GR 13:00 → JSOM social 14:18 → GR social 15:20 → AD social 16:20 → Lot D depart 17:10. The second trace proves the residence model is only an off-graph timing approximation.

## 4. Events

`main` loads JSON; `CampusModel` separates exam periods and campus events. The exact unnamed schema is supported after the targeted fallback name fix. On day 37, `event_interest * p_scale` selects interest, where `p_scale` targets 1.5× capacity interest. Interested agents sample a bounded Gaussian arrival around 14:10 and duration, add the event only if it fits the travel-buffered class agenda, then physically walk to it. Entry checks current represented attendance + 2 against capacity. Full events count as turned-away and continue normal agenda. Individual duration implements late arrival/early exit; class conflicts prevent event insertion rather than interruption. Missing nodes are warned/skipped.

Exam influence is Gaussian around the period midpoint: attendance boost up to 0.12, and study weight multiplier `1 + study_spike_response * term`. At day 37 / 15,000 agents / scale 2, exact SU input had 302 cumulative attendee-students, peak concurrent 200/200, and 75 turned-away agents (150 students).

## 5. Full-scale benchmark

Command:

```sh
/usr/bin/time -l python3 src/agents/campus_sim.py --agents 15000 --scale 2 --days 1 --start-day 37 --seed 42 --events tests/events_exact.json --out /tmp/gdg-fullscale-day37 --save-population
```

| Measure | Actual result |
|---|---:|
| Agents / represented students | 15,000 / 30,000 |
| Initialization / day runtime / wall time | 0.6 s / 18.7 s / 21.38 s |
| Peak resident memory | 294,977,536 bytes (~281 MiB) |
| Schedules / teleports / still on campus | 15,000 nonempty / 0 / 3 agents |
| Outputs | occupancy CSV: 6,701 rows, 231,530 bytes; population: 27,210,183 bytes |
| Seat violations | 0; peak total seated 3,274 / 3,512 active/default seats |
| Event | 302 cumulative; peak 200/200; 75 turned-away agents |

Hourly class/seated/event/idle-or-walking totals were staggered: 09:00 3,144/2/0/70; 12:00 5,024/3,186/0/1,018; 15:00 5,440/3,086/122/1,724; 18:00 3,256/2,874/0/1,106; 22:00 6/1,850/0/990. Biggest building peak was JSOM 2,026 (1,448 class, 312 seated, 266 idle), then ATC 946 and GR 922. Seated peaks respected caps: JSOM 328/344, JO 216/222, ATC 206/215, ECSW 180/185, GR 106/106. Class total is not a coded capacity violation because classrooms are unbounded. Walking peaked at 4,056 represented students at 12:50.

## 6. Remaining gaps

**Critical:** add verified AB/ACB and residence hall nodes; stop routing dormers through lots; model classroom/room capacity and enrollment; constrain schedules by major/level/term; reconcile the supplied seating rows (they sum to 1,812, not 2,029).

**Important:** synchronize/export dynamic hunger and energy and add recovery; model lateness/missed class; use verified permit zones/lot capacities/road commute/food venues/social groups; spatially separate JSOM1/JSOM2 and add verified SU seating if needed.

**Optional:** export per-agent traces and late/missed-class metrics; calibrate behavioral curves; add event priority/interruption behavior.

## 7. Readiness assessment

The simulator is operationally ready for exploratory scenario data: reproducible 15,000-agent runs finish in under 22 seconds, active-map routes have zero fallbacks, represented-student seating/event capacity is enforced, and class/seated/event/idle occupancy is exported separately. It is **not ready for trusted calibrated campus-occupancy training data** until classroom capacity, schedule realism, residence routing, and missing destinations are fixed. Current output should be labeled scenario data, not ground-truth-like training data.
