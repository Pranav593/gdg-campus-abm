"""Restrict destinations to academic buildings and calculate their walking routes."""
import networkx as nx


def academic_only(graph):
    result = graph.copy()
    result.remove_nodes_from([node for node, data in result.nodes(data=True)
                              if data.get('type') != 'path' and data.get('category') not in ('academic', 'parking')])
    result.graph['destination_scope'] = 'academic_only'
    return result


def academic_routes(graph):
    buildings = sorted(node for node, data in graph.nodes(data=True)
                       if data.get('category') in ('academic', 'parking') and data.get('routable'))
    paths, lengths, rows = {}, {}, []
    for start in buildings:
        distance, routes = nx.single_source_dijkstra(graph, start, weight='length')
        for end in buildings:
            if start == end:
                continue
            if end not in routes:
                raise ValueError(f'No walking route from {start} to {end}')
            path = routes[end]
            paths[start, end] = path
            lengths[start, end] = distance[end]
            rows.append(dict(start=start, end=end, length_m=round(distance[end], 2),
                             walk_time_min=round(nx.path_weight(graph, path, 'walk_time_min'), 3),
                             path_nodes=len(path)))
    # Show a compact set of connections joining every academic building, instead
    # of laying all 1,260 directed pair routes on top of one another.
    pairs = nx.Graph()
    pairs.add_nodes_from(buildings)
    for i, start in enumerate(buildings):
        for end in buildings[i + 1:]:
            pairs.add_edge(start, end, weight=(lengths[start, end] + lengths[end, start]) / 2)
    tree = nx.minimum_spanning_tree(pairs, weight='weight')
    display = [dict(start=a, end=b, path=paths[a, b]) for a, b in tree.edges()]
    return rows, display
