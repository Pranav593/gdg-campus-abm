# Simulation training-data readiness

Validation date: 2026-11-12. Branch: `integration/map-seating`.

## Map and routing

The default `GRAPH_PATH` is `src/mapping/utd-graph/utd_graph_simulation.pkl`; no `--graph` override is needed. It contains the richer academic/named-parking map, restored SU, retained edge lengths, and bidirectional pedestrian routing. All active destinations are in the usable component. GC and APC2 remain unavailable, and NB/NL remain excluded student destinations. Academic aliases and physical discretionary seating are unchanged. The 1,000-agent smoke test, 15,000-agent one-day run, and 15,000-agent five-day run all recorded zero teleports. Individual walking speed still determines edge traversal time.

## CourseBook audit

The 111 raw files contain 4,061 unique sections and 1,803 unique courses. All 4,061 have parseable current and maximum enrollment. Source totals are 128,479 current enrollments and 188,790 maximum slots. Section IDs and class numbers are unique, so the exports show no duplicate/cross-listed records that would automatically double-count enrollment. Multi-day meeting records belong to one section and receive one section-level enrollment target.

Preprocessing had already preserved `enrolled_current` and `enrolled_max` as `enrollment` and `capacity`; no enrollment values were lost. Credits were absent from both raw and previous processed data. Preprocessing now stores `credits` and `credit_source`: the second course-number character supplies credits for 3,926 sections, while 135 variable/special numbers use an explicitly labelled three-credit estimate.

The consolidated graph and weekday/time rules yield 3,348 usable sections across 1,573 courses. Exclusions are 498 with no weekday meeting, 214 with unmapped buildings, and one missing time. Usable current enrollment is 107,982. Forty usable sections report current enrollment above maximum by 115 students. Because maximum is a hard bound, the assignable target is 107,867. Across all source sections, 50 report current above maximum.

## Enrollment and schedules

Scheduling allocates section enrollment globally instead of independently sampling students. Each section starts with `min(enrolled_current, enrolled_max)` represented slots. Normal agents consume two slots at scale 2. An odd target uses one final agent with a one-student weight for that section only, so odd enrollment is not rounded upward. Class occupancy uses that section-specific weight.

Allocation balances each student's credit load, prevents overlapping meetings, prevents multiple sections of the same course, preserves all meetings, and never exceeds 19 credits. A second reconciliation pass may fill residual slots up to 14 credits; it does not use 19 as a normal target.

Full-scale validation results:

| Metric | Result |
|---|---:|
| Source enrollment in usable sections | 107,982 |
| Hard-bounded target enrollment | 107,867 |
| Assigned represented enrollment | 107,867 |
| Sections matched exactly | 3,348 / 3,348 (100%) |
| Unfilled target enrollment | 0 |
| Sections over maximum | 0 |
| Agents with time conflicts | 0 |
| Agents in duplicate sections of one course | 0 |
| Agents above 19 credits | 0 |
| Empty schedules | 0 |
| Schedules below 9 credits | 311 |
| Agents at 13–14 credits | 1,456 / 15,000 (9.71%) |

The usable source provides 311,179 represented credit hours, or 10.37 credits per member of a 30,000-student population. Therefore the requested 13–14-credit typical load is mathematically unavailable after excluding invalid/unmapped sections. The observed distribution is 58 agents at 7 credits, 253 at 8, 4,069 at 9, 3,903 at 10, 2,401 at 11, 2,860 at 12, 1,390 at 13, and 66 at 14. The simulator preserves source enrollment instead of inventing sections to force a higher load.

Machine-readable details are written to `enrollment_validation.json` and `enrollment_by_section.csv` in every run directory.

## Hunger and energy

`state.hunger` and `state.energy` now mirror the internal values at every metabolism/state update and are exported in `agent_states.json` when `--save-population` is enabled.

- Hunger rises gradually at 0.09/hour, resets to 0.05 after eating, and can trigger food seeking above 0.72 even outside the scheduled meal window. Classes are never interrupted.
- Energy declines with on-campus time, with additional walking/studying fatigue. Idle rest, meals, and off-campus breaks provide modest recovery.
- Low energy reduces study duration and study-choice weight, increases the existing leave tendency, and adds a rest option.
- Values are clamped to [0,1]. Full-run exported states passed bounds checks.

Deterministic tests confirm hunger increase, meal reduction, activity fatigue, idle recovery, low-energy study impact, bounds, and exposed/internal state synchronization.

## Occupancy export

`occupancy_snapshots.csv` uses the stable version 2.0 schema:

```text
semester_day,weekday,time_s,time_of_day,building_code,in_class,seated,at_event,idle_or_walking,total_occupancy
```

Counts represent real students consistently. Class rows use section-specific one/two-student weights; all other agent states use the scale ratio. `total_occupancy` equals the four component columns. Every active destination receives a row at every five-minute snapshot, including zero occupancy. `_WALKING` is a separate aggregate pseudo-destination. Keys `(semester_day,time_s,building_code)` are unique, and one-day/five-day reconciliation checks passed.

`run_manifest.json` records schema/configuration versions, seed, scale, source files, event hash, graph, day range, snapshot interval, runtimes, memory, teleports, close counts, and capacity-violation counts. Identical columns make output directories directly concatenable.

## Full-scale benchmarks

### One day: semester day 37

- 15,000 agents representing 30,000 students; seed 42.
- Initialization 1.02 seconds; simulation 21.9 seconds; internal total 24.3 seconds; wall time 25.37 seconds.
- Peak memory 345,047,040 bytes (about 329 MiB).
- 13,260 occupancy rows; 621,049-byte CSV; full run directory about 38.1 MB including population/state exports.
- Zero teleports, schedule conflicts, seating violations, section over-capacity, or event-capacity violations.
- SU event: 282 cumulative represented attendees, peak 200/200, 102 agents turned away.
- Highest building peaks: JSOM 1,589, SCI 830, ECSW 779, ECSS 684, GR 601.
- 162 agents remained on campus at 23:00; late presence is retained rather than silently removed.

### Five weekdays

- Initialization 1.03 seconds; simulation 89.0 seconds; internal total 91.5 seconds; wall time 92.79 seconds.
- Peak memory 357,875,712 bytes (about 341 MiB).
- 66,300 occupancy rows; 2,909,442-byte CSV; full run directory about 40.5 MB.
- Day runtimes: Monday 20.8 s, Tuesday 18.0 s, Wednesday 18.4 s, Thursday 18.7 s, Friday 13.1 s.
- Agents at close: Monday 39, Tuesday 0, Wednesday 175, Thursday 0, Friday 0.
- Zero teleports and capacity violations across all five days. Weekdays produced distinct occupancy curves and run times.

## Output locations

- One-day dataset: `outputs/readiness-full-day1/occupancy_snapshots.csv`
- One-day enrollment JSON/CSV: `outputs/readiness-full-day1/enrollment_validation.json`, `enrollment_by_section.csv`
- Five-day dataset: `outputs/readiness-full-week/occupancy_snapshots.csv`
- Five-day enrollment JSON/CSV: `outputs/readiness-full-week/enrollment_validation.json`, `enrollment_by_section.csv`
- Each directory also contains `run_manifest.json`, `population.json`, and `agent_states.json`.

These output directories are Git-ignored.

## Semester command and estimate

```sh
python3 src/agents/campus_sim.py --scale 2 --days 75 --start-day 0 --seed 42 \
  --events src/agents/events.json --out outputs/semester-seed42 --save-population
```

Omitting `--agents` uses the configured 30,000 students / scale 2 = 15,000 agents. Based on the measured week, a 75-day semester should take about 23 minutes and create about 995,000 occupancy rows. Estimated disk usage is roughly 80 MB with population/state exports, or about 45 MB without `--save-population`.

## Known limitations

- The source cannot support a typical 13–14-credit load for 30,000 students after unusable sections are removed. Restoring verified destinations/times is preferable to inventing enrollment.
- Classroom physical room capacities remain unavailable; section enrollment now bounds scheduled membership, but classroom geometry/capacity is not separately modelled.
- AB/ACB remain unmapped. The supplied discretionary seating rows still total 1,812 rather than the stated 2,029.
- Residence and road routing intentionally remain simplified for this MVP.
- Source enrollment is a static snapshot; attendance behavior reduces actual daily class occupancy.

The simulator now meets the operational requirements for immediate ML dataset generation. The documented source coverage and credit-load limitation should remain attached to trained-model provenance.
