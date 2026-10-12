import osmnx as ox

center = (32.9858, -96.7501)   # middle of UTD
G = ox.graph_from_point(center, dist=1200, network_type="walk")

print("nodes:", G.number_of_nodes())
print("edges:", G.number_of_edges())
ox.plot_graph(G)