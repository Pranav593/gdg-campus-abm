"""Create the simulation graph from only existing verified map data.

Base: src/mapping/utd-graph/utd_graph.pkl (academic catalog + named lots).
Addition: the verified Student Union node and its original walkway connector from
utd-graph/utd_graph_with_parking.pkl.  No coordinates or edges are invented.
"""
from pathlib import Path
import pickle
import networkx as nx


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "src/mapping/utd-graph/utd_graph.pkl"
SU_SOURCE = ROOT / "utd-graph/utd_graph_with_parking.pkl"
OUT = ROOT / "src/mapping/utd-graph/utd_graph_simulation.pkl"


def main():
    with BASE.open("rb") as f:
        graph = pickle.load(f)
    with SU_SOURCE.open("rb") as f:
        source = pickle.load(f)
    if "SU" not in source:
        raise RuntimeError("Verified SU node absent from source graph")
    graph.add_node("SU", **dict(source.nodes["SU"]))
    copied = 0
    for neighbor in source.neighbors("SU"):
        if neighbor not in graph:
            raise RuntimeError(f"SU connector node {neighbor!r} absent from base graph")
        for key, attrs in source["SU"][neighbor].items():
            graph.add_edge("SU", neighbor, key=key, **dict(attrs))
            copied += 1
    # OSM encodes some sidewalks as one-way arcs.  Pedestrian routing in this
    # simulator needs the same verified walkway usable in both directions; this
    # preserves every edge/length and does not introduce new geometry.
    graph = nx.MultiGraph(graph)
    graph.graph["simulation_consolidation"] = {
        "base": str(BASE.relative_to(ROOT)),
        "verified_addition": "SU node/edges from utd_graph_with_parking.pkl",
        "copied_edges": copied,
        "walking_directionality": "bidirectional from existing OSM walkway edges",
    }
    with OUT.open("wb") as f:
        pickle.dump(graph, f)
    print(f"wrote {OUT}: {len(graph)} nodes, {len(graph.edges)} edges, {copied} SU edges")


if __name__ == "__main__":
    main()
