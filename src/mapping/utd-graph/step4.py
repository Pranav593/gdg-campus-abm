import pickle
import networkx as nx
import osmnx as ox
import matplotlib.pyplot as plt

with open("utd_graph.pkl", "rb") as f:
    G = pickle.load(f)          # loads instantly, no re-download

def route(a, b):
    path = nx.shortest_path(G, a, b, weight="length")
    meters = nx.path_weight(G, path, "length")
    mins = nx.path_weight(G, path, "walk_time_min")
    print(f"{a:5s} -> {b:5s}: {meters:4.0f} m, {mins:4.1f} min walk")
    return path

# ---- the three routes from the assignment
print("Required routes:")
routes = [route("ECSS", "ECSW"), route("ECSW", "SU"), route("SU", "JSOM")]

# ---- bonus: which parking structure is closest to ECSW?
print("\nParking -> ECSW:")
for p in ["PS1", "PS3", "PS4"]:
    route(p, "ECSW")

# ---- draw the map with routes + labels
fig, ax = ox.plot_graph_routes(G, routes, route_colors=["red", "yellow", "cyan"],
                               node_size=0, show=False, close=False)
for n, d in G.nodes(data=True):
    if d["type"] in ("building", "parking"):
        color = "deepskyblue" if d["type"] == "building" else "orange"
        ax.scatter(d["x"], d["y"], c=color, s=40, zorder=5)
        ax.annotate(n, (d["x"], d["y"]), color="white", fontsize=8,
                    xytext=(4, 4), textcoords="offset points")
fig.savefig("utd_routes.png", dpi=200, bbox_inches="tight")
print("\nsaved utd_routes.png")
plt.show()
