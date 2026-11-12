# PR evaluation and integration decision

## Decision

**Select PR #7 (`Campus sim`, `47152fa`)**. It is the only PR with a runnable multi-agent, multi-day simulation covering CourseBook schedules, walking, seating, events, and occupancy export. This branch is `integration/map-seating`; `main` and original PR heads were not merged or altered.

## Execution evidence

All runs used Python 3.14, Mesa 3.5.1 and NetworkX 3.6.1 in separate worktrees at fetched PR heads.

| PR | Command/result | Runtime | Assessment |
|---|---|---:|---|
| #5 `Agent 1_Meghana` | `python3 src/agents/student_agent_01.py` fails creating `mesa.Agent`: `TypeError: object.__init__() takes exactly one argument` | 0.95 s to failure | One hard-coded schedule and graph routing only; no runnable population, activity, capacity, event, export, commuter, or semester model. |
| #6 `Basic working agent with 3 traits` | five-day single-student runner succeeds, but warns `SU` and `DHW` do not exist in graph | 1.31 s | CourseBook lookup, overlap validation, edge-length walking, meals/stays and dorm returns work for one configured schedule. No population/archetypes, capacities, events, semester curve or occupancy export. |
| #7 `Campus sim` | 200 agents / 2 days succeeds, zero teleports, CSV snapshots | 1.4 s | 20 weighted archetypes, CourseBook pool, conflict rejection, Gaussian variation, parking, floor-aware walking, seating, events, decay/exam effects and export. Needed physical-capacity/map fixes, made here. |

Integration benchmark: `--agents 200 --scale 2 --days 2 --seed 42` completed in 1.9 s simulation / 2.70 s wall clock, zero teleports, 6,992 occupancy rows, all 20 archetypes, and 200 distinct schedule fingerprints. Building peaks differed (JSOM 12, CB 9, GR 8 agents), rather than synchronized movement.

## Behavioral findings

| Criterion | #5 | #6 | #7 / selected branch |
|---|---|---|---|
| CourseBook schedules/conflicts | Hard-coded example | Reads CourseBook; validates overlap | Samples usable CourseBook sections and rejects conflicts |
| Commuter behavior | No | Basic dorm reappearance | Parking, permits, commuter/dormer differences, Gaussian arrival/parking |
| Free time | No | Meals/library fallback | Study/eat/social/leave decisions; capacity-aware alternatives; Gaussian durations |
| Walking | Node hop/tick; broken runner | Edge length/time | Edge length/time, floors and route preferences; zero smoke-test teleports |
| Semester variation | No | No | Attendance decay, exam attendance/study effects |
| Archetypes | No | Three knobs | 20 weighted archetypes plus individual Gaussian traits |
| Events/capacity/export | No | No | Events, physical cap, CSV snapshots |

**PR #5's behavioral logic is not better than PR #7's.** #5 is a small readable class-routing state machine, but it is non-runnable and lacks population behavior, activities, variability, capacities, events, and semester effects. #6's useful idea is explicit schedule validation; #7 is the stronger simulation base.

## Archetypes

PR #7 has 20 archetypes with weights summing to 1.0. They are **manually authored, not LLM-generated**: `src/agents/make_archetypes.py` says “no LLM needed” and contains a literal `TABLE` of values. `population.py` applies Gaussian trait variation and randomly samples non-overlapping CourseBook sections.

## Events

The requested JSON structure parses. The integration now uses a consolidated verified graph with the SU node/connector retained from the existing parking graph, so the exact day-37 SU event routes physically and enforces its 200-person peak. The detailed evidence is in `SIMULATION_AUDIT.md`. The exam period applies the configured study multiplier.

## Seating/map changes and limitations

`SEATING_FULL` preserves every supplied floor count. The provided 19 rows total **1,812**, not the requested 2,029; the source values are arithmetically short by 217. No capacity was invented to hide this discrepancy.

Physical seats are no longer scaled. At `--scale 2`, one agent claims two physical seats; capacity stays unchanged at every scale. JSOM1/JSOM2 remain separate floor inventories and aggregate only at the sole existing `JSOM` map node. `PHYA` resolves to `PHA`; FO/FA/FN/JO/GR/HH/ML1/ML2/AD/APC/ATC/ECS resolve directly. JO floor 1, JSOM1 floors 3/4 and APC floor 2 stay zero. NB, NL, POLICE and APC2 are excluded.

100-seat defaults are applied to accessible academic buildings missing from the supplied table: **BE, BSB, CB, CR, MC, PHY, SCI, SLC, TH, WSTC, CRA, RL, ROC, ROW, SPN, SP2, WAAC, DAV**. AB and ACB remain in the source inventory but have no graph nodes; they are reported instead of receiving invented coordinates/links. The consolidated map has SU and named parking lots, but no verified residence-hall destinations.

## Validation and commands

`python3 -m unittest discover -s tests -v` passes five tests for supplied floors, aliases, restrictions, defaults, scale invariance, claim/release accounting, alternatives and routes. The runner also checks seat underflow/accounting after each day.

```sh
cd ../gdg-campus-abm-integration
python3 -m unittest discover -s tests -v
python3 src/agents/campus_sim.py --agents 200 --scale 2 --days 2 --seed 42 --out out
python3 src/agents/campus_sim.py --agents 800 --scale 1 --days 1 --start-day 37 --events tests/events_executable.json --seed 42 --out out/event-test
```

`out/occupancy_snapshots.csv` is the time-series export for future ML work.
