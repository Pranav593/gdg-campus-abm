"""Offline distance and capacity enrichment. Distances are meters, never degrees."""
import csv
import math
from pathlib import Path

import networkx as nx

from build_graph import meters, norm


def whole_number(value):
    """Reject ambiguous/malformed counts rather than truncating or guessing."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return int(number) if math.isfinite(number) and number >= 0 and number.is_integer() else None
    except (TypeError, ValueError, OverflowError):
        return None


def enrich_edges(graph):
    for start, end, key, data in graph.edges(keys=True, data=True):
        value = data.get('length')
        if value is None:
            shape = data.get('geometry')
            points = list(shape.coords) if shape is not None else [
                (graph.nodes[start]['x'], graph.nodes[start]['y']),
                (graph.nodes[end]['x'], graph.nodes[end]['y'])]
            value = sum(meters(a[1], a[0], b[1], b[0]) for a, b in zip(points, points[1:]))
            data['distance_source'] = 'geometry_geodesic' if shape is not None else 'endpoint_geodesic'
        else:
            data.setdefault('distance_source', 'existing_length')
        try:
            distance = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'Invalid length for edge {(start, end, key)}: {value!r}') from exc
        if isinstance(value, bool) or not math.isfinite(distance) or distance < 0:
            raise ValueError(f'Invalid length for edge {(start, end, key)}: {value!r}')
        data.update(length=distance, distance_m=distance, walk_time_min=distance / 1.4 / 60)
    graph.graph.update(distance_unit='meters', walk_speed_m_s=1.4)


def enrich_places(graph, features, overrides):
    by_id = {(f['osm_type'], f['osm_id']): f for f in features}
    by_name = {}
    for feature in features:
        by_name.setdefault(norm(feature['tags'].get('name', '')), []).append(feature)
    for code, data in graph.nodes(data=True):
        if data.get('type') not in ('building', 'parking'):
            continue
        parking = data.get('category') == 'parking' or data.get('type') == 'parking'
        if parking:
            data['type'] = 'parking'
            data['category'] = 'parking'
        feature = by_id.get((data.get('osm_type'), data.get('osm_id')))
        if feature is None:
            candidates = by_name.get(norm(data.get('full_name', '')), [])
            if len(candidates) == 1:
                feature = candidates[0]
        tags = feature['tags'] if feature else {}
        source = f"https://www.openstreetmap.org/{feature['osm_type']}/{feature['osm_id']}" if feature else None
        override = overrides.get(code, {})
        for field, tag in [('floors', 'building:levels'), ('capacity', 'capacity')]:
            existing = whole_number(data.get(field))
            cached = whole_number(tags.get(tag))
            value = existing if existing is not None else cached
            provenance = data.get(field + '_source') or (source if cached == existing and existing is not None else 'existing_graph' if existing is not None else source)
            status = data.get(field + '_status') or ('osm_snapshot' if cached == existing and existing is not None else 'existing' if existing is not None else 'osm_snapshot')
            if field in override:
                value = whole_number(override[field])
                if override[field] is not None and value is None:
                    raise ValueError(f'Invalid {field} override for {code}')
                provenance = override.get(field + '_source')
                if value is not None and not provenance:
                    raise ValueError(f'Missing {field} source for {code}')
                status = override.get(field + '_status', 'documented')
            if field == 'floors' and value == 0:
                value = None
            data[field] = value
            data[field + '_source'] = provenance if value is not None else None
            data[field + '_status'] = status if value is not None else 'unknown'
        data['capacity_unit'] = 'vehicles' if parking else override.get('capacity_unit', data.get('capacity_unit', 'people'))
        data['parking_capacity'] = data['capacity'] if parking else None
        for field in ('capacity_notes', 'capacity_source_date', 'floors_notes',
                      'capacity_scope', 'capacity_method', 'capacity_confidence'):
            if field in override:
                data[field] = override[field]

    from parking_permits import enrich_permits
    enrich_permits(graph)


def estimate_parking_capacities(graph, features):
    """Estimate only unique surface-lot footprints; shared polygons stay unknown.

    30 m2 per vehicle includes stalls and circulation. This is an explicit
    low-confidence simulation assumption, not a university stall count.
    """
    from collections import Counter
    from shapely.ops import transform
    from parking_areas import match_areas
    areas, _ = match_areas(graph.nodes(data=True), features)
    uses = Counter(feature['osm_id'] for feature in areas.values())
    for code, node in graph.nodes(data=True):
        if node.get('category') != 'parking':
            continue
        if str(code).startswith('PS'):
            continue
        node.update(floors=None, floors_source=None, floors_status='not_applicable')
        if node.get('capacity') is not None and node.get('capacity_status') != 'estimated_footprint':
            continue
        feature = areas.get(code)
        # Clear stale estimates if the boundary becomes shared or unresolved.
        if node.get('capacity_status') == 'estimated_footprint':
            node.update(capacity=None, parking_capacity=None, capacity_status='unknown',
                        capacity_source=None, capacity_method=None, capacity_confidence=None)
        if feature is None or uses[feature['osm_id']] != 1:
            node['capacity_notes'] = 'No unique individual lot footprint; capacity needs a stall survey.'
            continue
        lat, lon = node['y'], node['x']
        scale = math.pi * 6371009 / 180
        def project(x, y, z=None):
            return ((x - lon) * scale * math.cos(math.radians(lat)), (y - lat) * scale)
        area = transform(project, feature['geometry']).area
        count = max(1, int(area / 30))
        node.update(capacity=count, parking_capacity=count, capacity_unit='vehicles',
                    capacity_status='estimated_footprint', capacity_confidence='low',
                    capacity_scope='whole_lot', capacity_source_date='2026-10-01',
                    capacity_source='https://www.openstreetmap.org/' + feature['osm_id'],
                    capacity_method='floor(projected footprint area in m2 / 30 m2 per vehicle), including circulation',
                    capacity_notes='Model estimate; not an official stall count or current availability. Landscaping and restrictions may reduce usable spaces.')


def simulation_routes(graph):
    """All directed destination pairs, choosing time from the distance-selected edge."""
    destinations = sorted((n for n, d in graph.nodes(data=True)
                           if d.get('type') != 'path' and d.get('routable')), key=str)
    rows = []
    for start in destinations:
        distances, paths = nx.single_source_dijkstra(graph, start, weight='length')
        for end in destinations:
            if start == end:
                continue
            if end not in paths:
                raise ValueError(f'No walking route from {start} to {end}')
            path = paths[end]
            minutes = sum(min(graph[a][b].values(), key=lambda e: e['length'])['walk_time_min']
                          for a, b in zip(path, path[1:]))
            rows.append(dict(start=start, end=end, distance_m=round(distances[end], 2),
                             length_m=round(distances[end], 2), walk_time_min=round(minutes, 3),
                             path_nodes=len(path)))
    return rows


def export_simulation(graph, output):
    """Write portable metadata and edges alongside the NetworkX graph."""
    import pickle
    import json
    from collections import Counter
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'utd_simulation_graph.pkl').open('wb') as file:
        pickle.dump(graph, file)
    from parking_permits import PERMIT_FIELDS, csv_place
    places = [csv_place(dict(code=n, **d)) for n, d in graph.nodes(data=True) if d.get('type') != 'path']
    for place in places:
        for field in ('seating_by_floor', 'seating_components'):
            if field in place:
                place[field] = json.dumps(place[field], separators=(',', ':'))
    summary = dict(
        nodes=graph.number_of_nodes(), edges=graph.number_of_edges(),
        destinations=len(places), active_destinations=sum(bool(p.get('routable')) for p in places),
        categories=dict(Counter(p.get('category') for p in places)),
        parking_capacity_status=dict(Counter(p.get('capacity_status') for p in places if p.get('category') == 'parking')),
        unknown_parking_capacity=[p['code'] for p in places if p.get('category') == 'parking' and p.get('capacity') is None],
        unknown_parking_permits=[p['code'] for p in places if p.get('category') == 'parking' and p.get('permit_types') is None],
        unknown_building_floors=[p['code'] for p in places if p.get('floors') is None and p.get('floors_status') != 'not_applicable'],
        unknown_nonacademic_capacity=[p['code'] for p in places if p.get('category') == 'non_academic' and p.get('capacity') is None],
        inventory_source=graph.graph.get('campus_inventory_source'),
        distance_unit='meters', reference_walk_speed_m_s=1.4)
    (output / 'simulation_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    exports = [
        ('simulation_nodes.csv', places,
         ['code', 'full_name', 'type', 'category', 'status', 'routable', 'y', 'x',
          'floors', 'floors_source', 'floors_status', 'capacity', 'capacity_unit',
          'parking_capacity', 'capacity_source', 'capacity_status', 'capacity_source_date', 'capacity_notes',
          'capacity_scope', 'capacity_method', 'capacity_confidence', 'floors_notes',
          'destination_kind', 'services', 'location_notes', 'members', 'coordinate_source', 'source_url',
          'seating_total', 'seating_by_floor', 'seating_components', 'seating_status',
          'seating_approximate', 'seating_notes', 'seating_source', *PERMIT_FIELDS]),
        ('parking_permit_estimates.csv', [p for p in places if p.get('category') == 'parking'],
         ['code', 'full_name', *PERMIT_FIELDS]),
        ('simulation_edges.csv', [dict(start=a, end=b, key=k, **d) for a, b, k, d in graph.edges(keys=True, data=True)],
         ['start', 'end', 'key', 'distance_m', 'length', 'walk_time_min', 'distance_source']),
        ('simulation_routes.csv', simulation_routes(graph),
         ['start', 'end', 'distance_m', 'length_m', 'walk_time_min', 'path_nodes']),
        ('metadata_review.csv', [p for p in places if
                                (p.get('floors') is None and p.get('floors_status') != 'not_applicable') or
                                (p.get('category') != 'academic' and p.get('capacity') is None) or
                                str(p.get('capacity_status', '')).startswith('estimated')],
         ['code', 'full_name', 'category', 'floors', 'floors_status', 'capacity', 'capacity_status'])]
    for filename, rows, fields in exports:
        with (output / filename).open('w', newline='', encoding='utf-8-sig') as file:
            writer = csv.DictWriter(file, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
