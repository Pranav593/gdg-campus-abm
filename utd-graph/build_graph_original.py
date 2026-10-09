"""
UTD campus graph -- Group 1
OpenStreetMap -> OSMnx -> NetworkX
Run: python build_graph.py   ->  creates utd_graph.pkl

Building codes come from the "Academic Buildings" legend of UTD's official
campus map (housing.utdallas.edu/files/2023/06/campus-map.pdf).
"""
import difflib
import pickle

import osmnx as ox

CENTER = (32.9858, -96.7501)
DIST = 1200
WALK_SPEED = 1.4   # m/s

# code -> possible names OSM might use (first exact match wins)
ACADEMIC = {
    "AD":   ["Administration Building", "Administration"],
    "AH1":  ["Arts and Humanities 1", "Arts and Humanities Building 1"],
    "AH2":  ["Arts and Humanities 2", "Arts and Humanities Building 2"],
    "ATC":  ["Edith O'Donnell Arts and Technology Building", "Arts and Technology Building"],
    "BE":   ["Lloyd V. Berkner Hall", "Berkner Hall"],
    "BSB":  ["Bioengineering Science Building", "Bioengineering and Sciences Building"],
    "CB":   ["Classroom Building"],
    "CB1":  ["Classroom Building 1", "Classroom Building I"],
    "CB2":  ["Classroom Building 2", "Classroom Building II"],
    "CB3":  ["Classroom Building 3", "Classroom Building III"],
    "CR":   ["Callier Center Richardson", "Callier Center for Communication Disorders", "Callier Center"],
    "CRA":  ["Callier Center Addition", "Callier Richardson Addition"],
    "ECSN": ["Engineering and Computer Science North"],
    "ECSS": ["Engineering and Computer Science South"],
    "ECSW": ["Engineering and Computer Science West"],
    "FA":   ["Founders Annex"],
    "FN":   ["Founders North"],
    "FO":   ["Founders Building", "Founders"],
    "GC":   ["Cecil and Ida Green Center", "Green Center"],
    "GR":   ["Cecil H. Green Hall", "Green Hall"],
    "HH":   ["Karl Hoblitzelle Hall", "Hoblitzelle Hall"],
    "JO":   ["Erik Jonsson Academic Center", "Jonsson Academic Center"],
    "JSOM": ["Naveen Jindal School of Management"],
    "MC":   ["Eugene McDermott Library", "McDermott Library"],
    "ML1":  ["Modular Lab 1", "Modular Laboratory 1"],
    "ML2":  ["Modular Lab 2", "Modular Laboratory 2"],
    "NB":   ["North Office Building"],
    "NL":   ["North Lab", "North Laboratory"],
    "PHA":  ["Physics Annex"],
    "PHY":  ["Physics Building"],
    "SCI":  ["Sciences Building"],
    "SLC":  ["Science Learning Center"],
    "TH":   ["University Theatre", "University Theater", "Theatre"],
    "WSTC": ["Waterview Science and Technology Center"],
}
# Student Union isn't "academic" on the map, but the assignment's routes need it
OTHER = {
    "SU":   ["Student Union"],
}
PARKING = {
    "PS1": ["Parking Structure 1"],
    "PS3": ["Parking Structure 3"],
    "PS4": ["Parking Structure 4"],
}

# If a building prints NOT FOUND, either add the OSM name it suggests to the
# lists above, or put coordinates here (Google Maps: right-click -> copy):
MANUAL_COORDS = {
    # "NL": (32.9876, -96.7493),
}
MANUAL_FLOORS = {
    # "ECSS": 4,      # OSM says 1 -- verify and fix
}
MANUAL_CAPACITY = {
    # "PS3": 0000,    # not in OSM -- look up
}

# ---- 1. walking network + walk time
print("Downloading walking network...")
G = ox.graph_from_point(CENTER, dist=DIST, network_type="walk")
for u, v, d in G.edges(data=True):
    d["walk_time_min"] = d["length"] / WALK_SPEED / 60
for n in G.nodes:
    G.nodes[n]["type"] = "path"
walk_only = G.copy()

# ---- 2. buildings + parking from OSM
print("Downloading buildings...")
feats = ox.features_from_point(CENTER, dist=DIST,
            tags={"building": True, "amenity": "parking"})
feats = feats[feats["name"].notna()].copy()
feats["center"] = feats.geometry.to_crs(feats.estimate_utm_crs()).centroid.to_crs(4326)

def norm(s):
    return str(s).lower().replace("’", "'").strip()

by_name = {}
for _, row in feats.iterrows():
    by_name.setdefault(norm(row["name"]), row)

def osm_number(row, tag):
    try:
        return int(float(str(row[tag]).split(";")[0]))
    except (KeyError, TypeError, ValueError):
        return None

def connect(label, lat, lon, kind, **attrs):
    near = ox.distance.nearest_nodes(walk_only, X=lon, Y=lat)
    G.add_node(label, x=lon, y=lat, type=kind,
               **{k: v for k, v in attrs.items() if v is not None})
    d = ox.distance.great_circle(lat, lon, G.nodes[near]["y"], G.nodes[near]["x"])
    for a, b in [(label, near), (near, label)]:
        G.add_edge(a, b, length=d, walk_time_min=d / WALK_SPEED / 60)
    return d

missing = []

def add_place(label, names, kind):
    row = next((by_name[norm(n)] for n in names if norm(n) in by_name), None)
    if row is None:
        if label in MANUAL_COORDS:
            lat, lon = MANUAL_COORDS[label]
            connect(label, lat, lon, kind,
                    floors=MANUAL_FLOORS.get(label),
                    capacity=MANUAL_CAPACITY.get(label))
            print(f"  {label:5s} <- manual coordinates")
        else:
            close = difflib.get_close_matches(norm(names[0]), list(by_name), n=3, cutoff=0.5)
            print(f"  {label:5s} NOT FOUND   OSM has similar: {close}")
            missing.append(label)
        return
    extra = {"full_name": row["name"]}
    if kind == "parking":
        extra["capacity"] = MANUAL_CAPACITY.get(label, osm_number(row, "capacity"))
    else:
        extra["floors"] = MANUAL_FLOORS.get(label, osm_number(row, "building:levels"))
    d = connect(label, row["center"].y, row["center"].x, kind, **extra)
    print(f"  {label:5s} <- {row['name']}  ({d:.0f} m to walkway)")

print("\nAcademic buildings:")
for label, names in ACADEMIC.items():
    add_place(label, names, "building")
print("\nOther:")
for label, names in OTHER.items():
    add_place(label, names, "building")
print("\nParking:")
for label, names in PARKING.items():
    add_place(label, names, "parking")

# ---- 3. save
with open("utd_graph.pkl", "wb") as f:
    pickle.dump(G, f)

n_labeled = sum(1 for _, d in G.nodes(data=True) if d["type"] != "path")
print(f"\nGraph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
      f"{n_labeled} labeled places")
if missing:
    print("Not found in OSM (fix in ACADEMIC or MANUAL_COORDS):", missing)
print("saved utd_graph.pkl")