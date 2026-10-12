import pickle
import osmnx as ox
import networkx as nx

center = (32.9858, -96.7501)

# ---- 1. walking network + walk time (same as step 2)
G = ox.graph_from_point(center, dist=1200, network_type="walk")
for u, v, data in G.edges(data=True):
    data["walk_time_min"] = data["length"] / 1.4 / 60
for n in G.nodes:
    G.nodes[n]["type"] = "path"          # generic navigation node

walk_only = G.copy()   # used to find the nearest WALKWAY node (not another building)

# ---- 2. buildings + parking from OSM
feats = ox.features_from_point(center, dist=1200,
            tags={"building": True, "amenity": "parking"})
feats = feats[feats["name"].notna()].copy()
# center point of each building (projected to meters so it's accurate)
utm = feats.estimate_utm_crs()
feats["center"] = feats.geometry.to_crs(utm).centroid.to_crs(4326)

# ---- 3. function: add one labeled node and connect it to the nearest walkway
def add_place(label, osm_name, kind):
    row = feats[feats["name"] == osm_name].iloc[0]
    lon, lat = row["center"].x, row["center"].y
    near = ox.distance.nearest_nodes(walk_only, X=lon, Y=lat)

    G.add_node(label, x=lon, y=lat, type=kind, full_name=osm_name)
    d = ox.distance.great_circle(lat, lon, G.nodes[near]["y"], G.nodes[near]["x"])
    for a, b in [(label, near), (near, label)]:   # both directions
        G.add_edge(a, b, length=d, walk_time_min=d / 1.4 / 60)
    print(f"  added {label:12s} ({kind}) -> {d:.0f} m from walkway")

# ---- 4. buildings (exact names from find.py)
BUILDINGS = {
    "ECSW": "Engineering and Computer Science West",
    "ECSN": "Engineering and Computer Science North",
    "ECSS": "Engineering and Computer Science South",
    "JSOM": "Naveen Jindal School of Management",
    "SCI":  "Sciences Building",
    "SU":   "Student Union",
    "MC":   "Eugene McDermott Library",
    "BSB":  "Bioengineering Science Building",
    "SLC":  "Science Learning Center",
}
print("Buildings:")
for label, name in BUILDINGS.items():
    add_place(label, name, "building")

# ---- 5. parking structures (short labels like the assignment uses)
PARKING = {
    "PS1": "Parking Structure 1",
    "PS3": "Parking Structure 3",
    "PS4": "Parking Structure 4",
}
print("\nParking:")
for label, name in PARKING.items():
    add_place(label, name, "parking")

# ---- 6. quick test + save
print("\nTest: SU -> JSOM path has",
      len(nx.shortest_path(G, "SU", "JSOM", weight="length")), "nodes")

with open("utd_graph.pkl", "wb") as f:
    pickle.dump(G, f)
print("saved utd_graph.pkl")