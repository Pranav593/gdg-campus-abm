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
