import osmnx as ox

center = (32.9858, -96.7501)
G = ox.graph_from_point(center, dist=1200, network_type="walk")

# --- look at one edge: OSMnx already gave us 'length' in meters
u, v, data = list(G.edges(data=True))[0]
print("example edge:", data)

# --- add walking time (1.4 m/s = average walking speed)
for u, v, data in G.edges(data=True):
    data["walk_time_min"] = data["length"] / 1.4 / 60

u, v, data = list(G.edges(data=True))[0]
print("after adding walk time:", data["length"], "m,", round(data["walk_time_min"], 2), "min")

# --- download buildings + parking from OSM
feats = ox.features_from_point(center, dist=1200,
            tags={"building": True, "amenity": "parking"})
named = feats[feats["name"].notna()]
print("named buildings/lots found:", len(named))

# save the list so we can find the real names
named[["name", "building", "amenity"]].sort_values("name").to_csv("names.csv")
print("saved names.csv")