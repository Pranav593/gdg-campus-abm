"""Extend the supplied UTD walk graph using verified academic building locations.

Run: python build_graph.py --source-dir . --output-dir .
Requires networkx, shapely, matplotlib. Reuses the graph/cache; no downloads.
"""
import argparse
import csv
import json
import math
import pickle
from pathlib import Path

from shapely.geometry import Polygon
from shapely.ops import unary_union

SPEED = 1.4


def norm(value):
    return ' '.join(str(value).casefold().replace('’', "'").replace('&', 'and').split())


def meters(lat1, lon1, lat2, lon2):
    a, b = map(math.radians, [lat1, lat2])
    dlat, dlon = map(math.radians, [lat2 - lat1, lon2 - lon1])
    h = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 6371009 * 2 * math.asin(min(1, math.sqrt(h)))


def cached_buildings(cache):
    elements = {}
    for path in sorted(cache.glob('*.json')):
        for item in json.loads(path.read_text(encoding='utf-8'))['elements']:
            key = (item['type'], item['id'])
            if key not in elements or 'tags' in item:
                elements[key] = item
    nodes = {i: (e['lon'], e['lat']) for (kind, i), e in elements.items() if kind == 'node'}
    ways = {i: e for (kind, i), e in elements.items() if kind == 'way'}

    def polygon(way):
        ids = way.get('nodes', [])
        if len(ids) < 4 or ids[0] != ids[-1] or any(n not in nodes for n in ids):
            return None
        shape = Polygon([nodes[n] for n in ids])
        return shape if shape.is_valid else shape.buffer(0)

    result = []
    for (kind, ident), element in elements.items():
        tags = element.get('tags', {})
        if not tags.get('building'):
            continue
        geometry = None
        if kind == 'way':
            geometry = polygon(element)
        elif kind == 'relation':
            outer, inner = [], []
            for member in element.get('members', []):
                if member['type'] == 'way' and member['ref'] in ways:
                    shape = polygon(ways[member['ref']])
                    if shape is not None:
                        (inner if member.get('role') == 'inner' else outer).append(shape)
            if outer:
                geometry = unary_union(outer)
                if inner:
                    geometry = geometry.difference(unary_union(inner))
        if geometry is not None and not geometry.is_empty:
            result.append(dict(osm_type=kind, osm_id=ident, tags=tags, geometry=geometry))
    return result


def resolve(record, features):
    aliases = {norm(name) for name in record['aliases']}
    candidates = [f for f in features if norm(f['tags'].get('name', '')) in aliases]
    if not candidates:
        return None
    if 'lat' in record:
        candidates.sort(key=lambda f: meters(record['lat'], record['lon'], f['geometry'].centroid.y, f['geometry'].centroid.x))
        center = candidates[0]['geometry'].centroid
        if meters(record['lat'], record['lon'], center.y, center.x) > 150:
            return None
    return candidates[0]


def extend_graph(graph, catalog, features):
    walk_nodes = [n for n, data in graph.nodes(data=True) if data.get('type') == 'path']
    if not walk_nodes:
        raise ValueError('The input graph has no walking nodes.')
    added = []
    for record in catalog['buildings']:
        code = record['code']
        feature = resolve(record, features)
        if code not in graph:
            if feature:
                point = feature['geometry'].centroid
                lat, lon = point.y, point.x
            elif 'lat' in record:
                lat, lon = record['lat'], record['lon']
            else:
                raise ValueError(f'No verified coordinates or cached footprint for {code}')
            graph.add_node(code, x=lon, y=lat, type='building', full_name=record['full_name'])
            added.append(code)
        data = graph.nodes[code]
        data.update(category=record['category'], status=record['status'],
                    routable=record['status'] == 'active', source_url=record['source_url'],
                    official_name=record['full_name'], verified_on=catalog['verified_on'])
        if not data.get('full_name'):
            data['full_name'] = record['full_name']
        if feature:
            data.update(osm_id=feature['osm_id'], osm_type=feature['osm_type'])
            data.setdefault('coordinate_source', 'OSM building footprint centroid')
            levels = feature['tags'].get('building:levels')
            if 'floors' not in data and levels:
                try:
                    data['floors'] = int(float(str(levels).split(';')[0]))
                except ValueError:
                    pass
        else:
            data.setdefault('coordinate_source', 'UT Dallas official map marker')
        # Reconnect only newly added destinations, preserving every existing edge.
        if not data['routable']:
            graph.remove_edges_from(list(graph.in_edges(code, keys=True)) + list(graph.out_edges(code, keys=True)))
        elif code in added:
            near = min(walk_nodes, key=lambda n: meters(data['y'], data['x'], graph.nodes[n]['y'], graph.nodes[n]['x']))
            distance = meters(data['y'], data['x'], graph.nodes[near]['y'], graph.nodes[near]['x'])
            for start, end in [(code, near), (near, code)]:
                graph.add_edge(start, end, length=distance, walk_time_min=distance / SPEED / 60,
                               connector=True, connector_method='nearest_walkway_node')
        neighbors = [n for n in graph.successors(code) if graph.nodes[n].get('type') == 'path']
        if neighbors:
            data['walkway_node'] = neighbors[0]
            data['connector_distance_m'] = min(e['length'] for e in graph[code][neighbors[0]].values())
    graph.graph.update(academic_verified_on=catalog['verified_on'], academic_source=catalog['official_map'],
                       unresolved_buildings=catalog['unresolved'], walk_speed_m_s=SPEED)
    return added


def map_data(graph, features):
    places = []
    for code, data in graph.nodes(data=True):
        if data.get('type') in ['building', 'parking']:
            row = {k: v for k, v in data.items() if k not in ['geometry']}
            row.update(code=code, full_name=data.get('official_name', data.get('full_name', str(code))))
            places.append(row)
    places.sort(key=lambda p: p['code'])
    minx = min(p['x'] for p in places) - .0011
    maxx = max(p['x'] for p in places) + .0011
    miny = min(p['y'] for p in places) - .0011
    maxy = max(p['y'] for p in places) + .0011
    bounds = (minx, miny, maxx, maxy)
    return places, bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=Path(__file__).parent)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    source, output = args.source_dir, args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(Path(__file__).with_name('academic_buildings.json').read_text(encoding='utf-8'))
    graph_path = source / 'utd_graph.pkl'
    with graph_path.open('rb') as file:
        graph = pickle.load(file)
    backup = output / 'utd_graph_original.pkl'
    if not backup.exists():
        backup.write_bytes(graph_path.read_bytes())
    features = cached_buildings(source / 'cache')
    added = extend_graph(graph, catalog, features)
    from academic_routing import academic_only, academic_routes
    graph = academic_only(graph)
    route_rows, display_routes = academic_routes(graph)
    graph.graph['academic_display_routes'] = display_routes
    with (output / 'utd_graph.pkl').open('wb') as file:
        pickle.dump(graph, file)
    places, bounds = map_data(graph, features)
    fields = ['code', 'full_name', 'category', 'status', 'routable', 'y', 'x', 'floors', 'coordinate_source', 'connector_distance_m', 'source_url']
    with (output / 'academic_nodes.csv').open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(places)
    with (output / 'building_review.csv').open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=['code', 'full_name', 'status', 'reason'])
        writer.writeheader(); writer.writerows(catalog['unresolved'])
    with (output / 'academic_routes.csv').open('w', newline='', encoding='utf-8-sig') as file:
        writer = csv.DictWriter(file, fieldnames=['start', 'end', 'length_m', 'walk_time_min', 'path_nodes'])
        writer.writeheader(); writer.writerows(route_rows)
    from draw_map import draw
    draw(output / 'utd_graph.pkl', output / 'utd_routes.png')
    summary = dict(added=added, active_academic=sum(p.get('category') == 'academic' and p.get('status') == 'active' for p in places),
                   labeled_places=len(places), nodes=graph.number_of_nodes(), edges=graph.number_of_edges(),
                   academic_pair_routes=len(route_rows), displayed_connections=len(display_routes), unresolved=catalog['unresolved'])
    (output / 'graph_summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
