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
