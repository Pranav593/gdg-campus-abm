import pickle
import osmnx as ox

center = (32.9858, -96.7501)
with open("utd_graph.pkl", "rb") as f:
    G = pickle.load(f)

feats = ox.features_from_point(center, dist=1200,
            tags={"building": True, "amenity": "parking"})
feats = feats[feats["name"].notna()]

def osm_number(name, tag):
    """Read a number tag (like building:levels) from OSM, or None if missing."""
    if tag not in feats.columns:
        return None
    vals = feats.loc[feats["name"] == name, tag].dropna()
    if len(vals) == 0:
        return None
    try:
        return int(float(str(vals.iloc[0]).split(";")[0]))
    except ValueError:
        return None

# fill in anything OSM is missing (look up real numbers, e.g. UTD parking site)
MANUAL_FLOORS = {
    # "ECSW": 4,
}
MANUAL_CAPACITY = {
    # "PS3": 1500,
}

for n, d in G.nodes(data=True):
    if d["type"] == "building":
        d["floors"] = MANUAL_FLOORS.get(n, osm_number(d["full_name"], "building:levels"))
        print(f"{n:5s} floors   = {d['floors']}")
    elif d["type"] == "parking":
        d["capacity"] = MANUAL_CAPACITY.get(n, osm_number(d["full_name"], "capacity"))
        print(f"{n:5s} capacity = {d['capacity']}")

with open("utd_graph.pkl", "wb") as f:
    pickle.dump(G, f)
print("saved utd_graph.pkl")