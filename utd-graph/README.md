# UTD academic building graph

The map retains the original black background, gray walking network, blue
building nodes, white code labels, and red/yellow/cyan routes. The graph includes
36 confirmed academic destinations and two non-routable academic sites. Dorm,
parking and Student Union destination nodes and labels are excluded.

## Run

Install `networkx`, `shapely`, and `matplotlib` in your Python environment, then run:

```powershell
python build_graph.py
python test_academic_graph.py
```

For the same black map with zoom and pan controls, run:

```powershell
python draw_map.py --show
```

This opens `utd_map.html` in your browser. Scroll to zoom, drag to pan, and use
Reset to return to the full campus. The map uses vector paths, so zooming keeps
the lines sharp. You can also double-click `utd_map.html` without running Python.

`build_graph.py` reads the existing `utd_graph.pkl`, the supplied `cache/`, and
`academic_buildings.json`. It preserves the existing walking nodes and edges,
adds missing destinations with two-way nearest-walkway connectors, and writes
`utd_graph.pkl`, `utd_routes.png`, `academic_nodes.csv`, `academic_routes.csv`,
and `building_review.csv`.
It does not need a new OpenStreetMap download. Re-running does not duplicate nodes
or connections. `draw_map.py` redraws the map alone. `utd_graph_original.pkl`
preserves the graph before this update; `build_graph_original.py` and
`utd_routes_original.png` preserve the original script and map.
`utd_graph_with_parking.pkl` and `utd_routes_with_parking.png` preserve the version
before restricting destinations to academic buildings.

`academic_routes.csv` contains all 1,260 directed walking routes between the 36
active academic destinations, with distance and walk time. The image shows 35
connections joining all active academic buildings, chosen with a minimum
spanning tree of their walking distances to keep the map readable. Gray lines
remain the cached walking network; they are not dorm or parking destinations.

## Verified locations and review items

The building inventory was checked against UT Dallas's official interactive map
on October 8, 2026: https://map.utdallas.edu/index.html
The supplied OpenStreetMap cache is dated October 1, 2026.
Existing node coordinates and floor metadata are preserved; added building
coordinates use cached footprint centroids when available, otherwise official
map markers. Source links are recorded in the inventory and graph attributes.

The 11 added active academic destinations are ATC, CRA, FA, RL, ROC, ROW, SPN,
SP2, WAAC, APC, and DAV. DAV is a local graph label for the Charles and Nancy
Davidson Building (JSOM's former phase III); the official map has no code.

GC is labeled as closed on the official map. APC2 is the Athenaeum performance
hall/music building under construction, with spring 2027 listed for opening.
Both are shown as blue building nodes on the original-style image for coverage,
but have `routable=False` and no edges in the graph.

AH1, AH2, CB1, CB2, and CB3 appear in the older catalog, but are absent from the
current official building category and strict map searches. They remain in
`building_review.csv` without guessed positions or graph nodes. This absence
does not prove demolition; their current status/location needs confirmation.

Connectors reproduce the original straight-line nearest-walkway approach at
1.4 m/s. They are not surveyed entrances. The cached walking network may include
paths affected by construction. All colored route endpoints are active academic
buildings; the closed GC and future APC2 nodes have no walking routes.

Map data © OpenStreetMap contributors, ODbL.


## Simulation distances, floors and capacities

Build the complete campus simulation graph without downloading map data:

```powershell
python build_simulation_graph.py
python -m unittest discover -s . -p "test_*.py"
```

Requires `networkx` and `shapely`. From the repository root, run
`python scripts/test_mapping.py` to run both graph folders' complete test suites.
`build_graph.py` also enriches the existing map graph with the same metadata;
its existing destination scope and rendering are retained.

`build_simulation_graph.py` adds Student Union, Dining Hall West, Activity Center,
Student Services buildings, five residence halls, three garages and the 29
cataloged parking lots to a separate graph. It writes:

- `utd_simulation_graph.pkl`: NetworkX MultiDiGraph for simulation.
- `simulation_nodes.csv`: floors, capacity, units, sources and unknown flags.
- `simulation_edges.csv`: every keyed directed edge with `distance_m`, legacy
  `length` (also meters), and reference `walk_time_min` at 1.4 m/s.
- `simulation_routes.csv`: 6,006 directed routes between 78 active destinations,
  with `distance_m`, legacy `length_m`, reference walk time and node count.
- `metadata_review.csv`: destinations with missing floor/capacity data.

Distances preserve existing walkway lengths. Only missing lengths are computed
from full edge geometry, or endpoints when geometry is unavailable. Negative or
nonfinite distances are rejected. Connector lengths are straight-line distances
to the nearest walkway node, not surveyed entrance routes. Future simulations
can calculate travel seconds as `distance_m / speed_m_s` for positive speeds.

`floors` is a positive whole number of above-ground levels where available.
Floor counts come from the October 1, 2026 OSM cache or existing graph data;
OSM values have not been surveyed. Ambiguous values are left unknown.

`capacity` is a nonnegative count, with an explicit `capacity_unit`:
`vehicles` for parking, `seats` for dining, `beds` for housing, and `people`
for other building counts. `parking_capacity` aliases `capacity` on parking
nodes. These are metadata for future simulation limits; this change does not
implement agent admission, occupancy tracking or congestion.

Known capacities are PS1: 750 vehicles, PS3: approximately 750 vehicles,
PS4: 1,150 vehicles, Lot M North: 32 vehicles, Dining Hall West: 800 seats,
and Andromeda Hall (legacy label RHW): 600 beds. Each value has a source link,
source date (year precision where applicable), status and explanatory notes in
`simulation_places.json` and the node export. PS1's historical university design
figure conflicts with the cached OSM count of 400; the conflict is recorded.
Published historical capacities are starting parameters requiring operational
review, not current availability or certified maximum occupancy. Seats and beds
are not interchangeable with whole-building fire occupancy limits.

Missing values are Python/JSON `None`/`null` and empty CSV cells, with status
`unknown`. They mean unknown, not zero or unlimited. Most surface lots and
Student Union lack a sourced capacity. Combined lot counts are not arbitrarily
split into individual capacities. Closed GC and construction site APC2 remain
isolated and excluded from routes. Edit documented overrides in
`simulation_places.json`, then rebuild; repeated runs do not duplicate places.


## Parking permit estimates

`parking_permits.json` records a manual review of the official UTD parking map
(PDF effective July 30, 2026). It lists physically designated colors per area,
not the eligibility of a higher-tier permit to use lower-tier spaces.

Parking nodes include `permit_split_pct` (Green, Gold, Orange, Purple and Other),
`permit_types`, flat `permit_green_pct` / `permit_gold_pct` / `permit_orange_pct` /
`permit_purple_pct` / `permit_other_pct` fields, source URL, map date, one-based
PDF page, downloaded PDF SHA-256, review date, method, denominator and confidence.
`parking_permit_estimates.csv` and `simulation_nodes.csv` expose these fields;
`permit_types` is a JSON array in CSV. `academic_nodes.csv` includes them for
parking destinations retained by that map variant.

Percentages are coarse, low-confidence visual estimates from mapped color
regions, not official stall counts or measured GIS area. They sum to 100 including
Other (residential, metered, accessible, reserved, EV and non-four-color spaces).
The source does not establish exact counts, and no permit-specific stall counts
are calculated from potentially historical capacity totals. Tiny mapped colors
remain nonzero. A zero means the color was not shown in that reviewed area.
Null means unresolved, including gray/unclassified Lot R and any new unreviewed
node. The current inventory has 32 parking areas: 31 have estimates and Lot R is
unknown. Designations and numerical estimates carry separate confidence values.

All three garages show Gold, Orange and Purple but no Green. Their five-level
diagrams also replace older cached garage floor counts. Residential-only lots
and metered Lot F retain Other=100, rather than being assigned commuter colors.
The map separates T1/T2/T3 and M Southeast 1/2 even where older cached polygons
group them together. Shared shaded footprints do not imply shared permit mixes.

Rebuild with `python build_simulation_graph.py` (and `python build_graph.py` for
the map graph). Editing estimates is validated: no percentage may be assigned
to a color absent from that lot's reviewed `verified_types`.
