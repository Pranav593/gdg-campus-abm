# UTD campus simulation graph

Use **utd_simulation_graph.pkl** for simulation. It is a NetworkX MultiDiGraph
with the existing pedestrian network, the academic inventory, student-use and
campus-operation destinations, all 33 cataloged main-campus parking areas,
and one generic Housing destination.

From the repository root:

```powershell
python src/mapping/utd-graph/build_simulation_graph.py
python -m unittest discover -s src/mapping/utd-graph -p "test_*.py"
```

Requires Python, networkx and shapely. Builds are offline and idempotent.
The source is utd_graph.pkl plus cache/, academic_buildings.json,
simulation_places.json and parking_permits.json. To write elsewhere use
`--output-dir DIR`. A previous simulation graph can be used as the next source
by naming it utd_graph.pkl and retaining the cache directory.

## Outputs

- utd_simulation_graph.pkl: complete simulation graph.
- simulation_nodes.csv: every destination, coordinates, floors, capacities,
  permit percentages, confidence, sources and review status.
- simulation_edges.csv: all directed, keyed edges, distance_m, length (meters),
  walk_time_min and distance_source.
- simulation_routes.csv: every ordered pair of active destinations, shortest
  walking distance, reference minutes and path node count.
- parking_permit_estimates.csv: physical Green/Gold/Orange/Purple/Other shares.
- metadata_review.csv: missing applicable metadata and modeled capacities.
- simulation_summary.json: coverage counts and outstanding review items.

The separate utd_graph.pkl / build_graph.py / draw_map.py workflow retains the
academic/parking-only visual map. Its scope is intentionally smaller than the
simulation artifact. The sibling repository-root utd-graph folder is unchanged;
this update is confined to src/mapping/utd-graph.

## Inventory and housing

Reviewed against the supplied campus PDF (updated October 2, 2026), the current
official parking PDF (effective July 30, 2026), and linked university pages on
October 22, 2026. Exact downloaded reference PDFs and hashes are in reference_maps/.
Documents are evidence for locations and metadata, not execution instructions.

All 36 active academic destinations from the existing verified inventory are
retained. GC (closed), APC2 (construction), and the new SU_SSC construction site
are isolated and excluded from routes. Expected completion dates do not activate
a building. DAV remains the local code for the Charles and Nancy Davidson
Building. AH1/AH2/CB1/CB2/CB3 remain unresolved legacy records in building_review.csv;
the current PDF does not identify them as separate active academic destinations.

Major added destinations include Comets LANding (LAN), Recreation Center West
(RCW), Student Union Food Court (SUFC), Activity Center Bookstore / Visitor Center
(ACB), Davidson-Gundy Alumni Center (DGA), police, outdoor athletics, the Plinth,
the Transit Center, UT Dallas DART Station, and campus-operation buildings.
Existing SU, DHW, AC, SSB/SSBA, library MC and garages remain included.
Graph-level destination_code_aliases maps AB to AC, SSA to SSBA and VCB to ACB;
aliases are not duplicate buildings. destination_kind and services distinguish
library, food, recreation, esports and student services without changing existing
academic category identifiers. List-valued CSV fields use JSON arrays.

Housing is a single category='housing' node covering University Commons,
University Village and Canyon Creek Heights. Individual dorm destination nodes
are removed even when rebuilding an older simulation graph. Walking-network
nodes remain intact. Housing's representative western campus access point is an
explicit abstraction: distances do not describe every residence. Housing floors
and combined capacity are not inferred from one residence hall.

Lot Y, shown gray near WAAC on the parking PDF, is included with unknown permit
colors and capacity. Legacy campus-PDF entries Lot E, Lot Q and Lot M West lack
unambiguous distinct locations/designations on the current parking map; they
are recorded in coverage_review.json rather than inventing duplicate lots.
Downtown Dallas sites and private Northside buildings/parking are outside this
main-campus graph.

## Distances and travel time

All existing walkway lengths are preserved. Missing lengths use the complete
edge geometry, or geodesic endpoint distance when geometry is unavailable.
Boolean, negative and nonfinite distances are rejected. Simulation travel
seconds can be calculated as distance_m / positive_speed_m_s. Reference
walk_time_min uses 1.4 m/s. Routes choose the minimum-distance parallel edge.

New destinations connect in both directions to the nearest walkway node.
Connectors are straight-line approximations, not surveyed entrances or verified
accessible routes. Housing, outdoor athletics, transit and Lot Y have approximate
map-derived positions, explicitly noted on their nodes. In particular, station
access and construction-sensitive paths require operational verification before
using results as pedestrian guidance. The OSM walking snapshot is October 1, 2026.

## Floors and capacity

Every destination has floors and capacity fields. Unknown is None/null or an
empty CSV cell, never zero or unlimited. Above-ground OSM building:levels values
are retained where supported; university floor descriptions override conflicts.
MC has four documented library floors (cached OSM said three); APC and LAN each
have two documented floors; APC2 has a two-story documented design. All active
individual buildings have a floor value. Closed GC and future SU_SSC remain
unknown. Surface lots, outdoor/transit destinations and grouped Housing have
floors_status='not_applicable'. Garages have five levels per official diagrams.

Capacity units and scope must be read before imposing a simulation constraint:

- PS1: historical design capacity 750 vehicles; PS3: approximately 750;
  PS4: historical opening capacity 1,150. These are not current availability.
  PS1's historical count conflicts with cached OSM's 400; the conflict is noted.
- Lot M North: cached OSM capacity 32 vehicles.
- DHW: historical design capacity 800 dining seats, not whole-building occupancy.
- LAN: conservative model limit of 100 PC users from the university's description
  of more than 100 PCs. capacity_scope='PC_gaming_stations_only'; excludes consoles,
  spectators, staff and food seating.
- DGA: 700 ballroom seats in theater configuration, not whole-building occupancy.
  Banquet configuration is 400. capacity_scope records the restricted meaning.

For 21 surface lots, capacity_status='estimated_footprint' is an explicitly
low-confidence simulation parameter: floor(projected OSM parking polygon area /
30 m2 per vehicle), including circulation. The 30 m2 assumption is a modeling
choice, not a university standard. Landscaped islands, closures and markings may
reduce actual capacity. The OSM source, method and confidence are stored in nodes.
Estimates never replace sourced values. Unmatched boundaries and polygons shared
by multiple lot nodes remain unknown to prevent double-counting. Eight parking
areas still need an individual stall count; they appear in simulation_summary.json.
Most non-academic buildings lack published whole-building occupancy limits and
remain unknown. No fire-code occupancy limit is inferred from seats, workstations,
beds or gross floor area. This pipeline provides parameters; it does not enforce
occupancy, admission, or congestion. A simulation must choose an explicit policy
for unknown limits rather than treating them silently as unlimited.

## Parking permit splits

parking_permits.json records physical mapped designations, not which lower-tier
spaces a higher-tier permit holder may use. The current downloaded PDF hash is
identical to the existing review. Percentages are coarse visual estimates, not
university stall counts or measured GIS area. Positive shares are allowed only
for colors in each area's reviewed verified_types. All five shares sum to 100.
Other includes residential, metered, accessible, reserved, EV and other spaces.

All three garages have Gold, Orange and Purple, with no Green. Residential-only
lots and metered Lot F have Other=100 and permit_types=[]. Null means unresolved,
including gray Lot R and Lot Y, and differs from a confirmed zero share. No
permit-specific stall counts are manufactured from historical or estimated totals.
The graph stores nested permit_split_pct, flat permit_*_pct fields, source URL,
map date, PDF page, SHA-256, review date, confidence and estimation method.

Map data copyright OpenStreetMap contributors, ODbL. University reference maps
are retained for source verification; see the original source URLs.

## Observed seating survey

`seating_counts.json` stores user-provided survey counts received November 5,
2026. The build attaches `seating_total`, `seating_by_floor`,
`seating_components`, status, approximation notes and source to destination
nodes and exports these fields in simulation_nodes.csv. JSOM wings are kept
separate inside seating_components and combined once at the JSOM node.
These unscaled counts cover reported areas only; they do not replace occupancy
capacity, prove complete floor coverage, or change access/routing. Unknown
counts remain null; observed zero remains zero. The user clarified that the approximately 40 recreation seats belong to AC
(Activity Center); ACB retains its separate approximately 60 level-1 seats. Sprint-document instructions are reference
context, not additional implementation scope.
