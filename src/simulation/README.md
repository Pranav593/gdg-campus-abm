# Campus simulation

The semester runner uses the actual cleaned Spring 2026 CourseBook meetings and
`src/mapping/utd-graph/utd_graph.pkl` for building-to-building routing. The
population defaults to 50 during development; 40,000 agents is the configured
1:1 maximum.
Each agent receives a fixed, normally varied trait profile and a conflict-free
sample of real section meetings. A seeded run is repeatable.

```powershell
py -m src.simulation.run_simulation --population 50 --seed 42
py -m src.simulation.run_simulation --population 1000 --seed 42
py -m src.simulation.run_simulation --population 30000 --seed 42
py -m src.simulation.run_simulation --population 40000 --seed 42
```

Outputs go to `outputs/simulation/`: `agents.json`, an activity CSV, and
`summary.json`. At populations of 10,000 or more the activity CSV is streamed
as `activity_log.csv.gz` with fast compression to limit disk use; below that it
is `activity_log.csv`. Activities include scheduled classes, walking, study, meals,
social time, events and returning to an assigned parking lot. Exam periods
change study and attendance probabilities. Building seating and event capacity
are scaled from the configured 40,000 student population.
Scaled seat and event capacities have a minimum of one during small development
runs so that those behaviors can be exercised.

## Assumptions and current scope

- The 20 archetype weights sum to 1.0; all archetypes have gold permits per
  the archetype generation requirement. Generated students receive a realistic
  green/gold/orange/purple permit mix and fixed seeded trait variations.
- Course sections are sampled without overlap across the week, and all meetings
  for each selected section stay together. A student receives 3–5 sections; this is a simple schedule builder, not a
  degree audit or enrollment optimizer.
- A 50/50 draw selects a parking preference near the first or last class.
  Parking choice balances graph walking time, parking loyalty and a sampled
  delay. The graph has no permit eligibility by lot, so all lots are candidates
  for now. Dormers also begin and end at parking, as specified.
- Walk time uses graph distance divided by individual walking speed. Building
  floor changes add 30 seconds per floor where known.
- Free-time activities use available gaps, nearby reachable active buildings,
  next-class travel time, traits and temporary scaled seating. Students remain
  in place when a feasible activity cannot be found.
- Event day numbers and exam periods are semester-relative and editable in
  `events.json`. Event capacities represent total attendance across the run.
- The route graph omits the Student Union as a destination. The career fair is
  therefore placed at JSOM, an active routable venue in this graph. Replace
  this venue if a routable Student Union node is added later.
- The runner is an end-to-end baseline intended for gradual scaling. Agent-day
  plans are processed sequentially; it does not yet model synchronized
  minute-by-minute room occupancy. Parking permit eligibility needs lot data.
- A 30,000-agent, 112-day run was completed successfully. The configured
  maximum of 40,000 is accepted by the command and uses the same implementation.
