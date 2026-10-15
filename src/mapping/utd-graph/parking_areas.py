"""Match cached parking footprints conservatively and clip displayed routes."""
import json
import re

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union


def cached_parking(cache):
    elements = {}
    for path in sorted(cache.glob('*.json')):
        for item in json.loads(path.read_text(encoding='utf-8'))['elements']:
            key = (item['type'], item['id'])
            if key not in elements or 'tags' in item:
                elements[key] = item
    nodes = {i: (e['lon'], e['lat']) for (kind, i), e in elements.items() if kind == 'node'}
    shapes = {}
    for (kind, ident), item in elements.items():
        ids = item.get('nodes', [])
        if kind != 'way' or len(ids) < 4 or ids[0] != ids[-1] or any(n not in nodes for n in ids):
            continue
        shape = Polygon([nodes[n] for n in ids])
        shapes[ident] = shape if shape.is_valid else shape.buffer(0)
    result = []
    for (kind, ident), item in elements.items():
        tags = item.get('tags', {})
        if tags.get('amenity') != 'parking':
            continue
        shape = shapes.get(ident) if kind == 'way' else None
        if kind == 'relation':
            outer, inner = [], []
            for member in item.get('members', []):
                if member['type'] == 'way' and member['ref'] in shapes:
                    (inner if member.get('role') == 'inner' else outer).append(shapes[member['ref']])
            if outer:
                shape = unary_union(outer).difference(unary_union(inner))
        if shape is not None and not shape.is_empty and shape.geom_type in ('Polygon', 'MultiPolygon'):
            result.append(dict(osm_id=f'{kind}/{ident}', tags=tags, geometry=shape))
    return result


def match_areas(nodes, features):
    areas, review = {}, []
    for code, data in nodes:
        if data.get('category') != 'parking':
            continue
        point = Point(data['x'], data['y'])
        candidates = [f for f in features if f['geometry'].covers(point)]
        # Numbered map sections may share one OSM lot footprint.
        expected = re.sub(r'\s*\d+$', '', str(code).removeprefix('Lot ')).casefold().strip()
        candidates = [f for f in candidates if not f['tags'].get('ref') or
                      f['tags']['ref'].casefold().strip() == expected]
        if len(candidates) == 1:
            areas[code] = candidates[0]
        else:
            review.append(dict(code=code, reason='No unambiguous containing parking footprint with a compatible lot reference'))
    return areas, review


def outside_segments(coordinates, polygons):
    if len(coordinates) < 2:
        return []
    line = LineString(coordinates)
    if polygons:
        line = line.difference(unary_union(polygons))
    if line.is_empty:
        return []
    if line.geom_type == 'LineString':
        return [list(line.coords)]
    return [list(part.coords) for part in line.geoms if part.geom_type == 'LineString' and not part.is_empty]


def edge_coordinates(graph, start, end, edge):
    a, b = graph.nodes[start], graph.nodes[end]
    shape = edge.get('geometry')
    points = list(shape.coords) if shape is not None else [(a['x'], a['y']), (b['x'], b['y'])]
    if Point(points[-1]).distance(Point(a['x'], a['y'])) < Point(points[0]).distance(Point(a['x'], a['y'])):
        points.reverse()
    return points


def draw_areas(ax, graph, areas):
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch
    from shapely.geometry.polygon import orient
    painted = set()
    for code, feature in areas.items():
        shape = feature['geometry']
        if feature['osm_id'] not in painted:
            painted.add(feature['osm_id'])
            for polygon in (shape.geoms if shape.geom_type == 'MultiPolygon' else [shape]):
                polygon = orient(polygon)
                vertices, codes = [], []
                for ring in [polygon.exterior, *polygon.interiors]:
                    points = list(ring.coords)
                    vertices.extend(points)
                    codes.extend([Path.MOVETO] + [Path.LINETO] * (len(points)-2) + [Path.CLOSEPOLY])
                patch = PathPatch(Path(vertices, codes), facecolor='#f0a044', edgecolor='#ffc16e',
                                  linewidth=.6, alpha=.32, zorder=2)
                patch.set_gid('parking-area-' + str(feature['osm_id']).replace('/', '-'))
                ax.add_patch(patch)
        node = graph.nodes[code]
        # The matched map marker is already inside the footprint; retain its
        # position so labels on shared footprints don't collapse onto one point.
        label = ax.annotate(str(code), (node['x'], node['y']), color='#ffe1b1',
                            fontsize=6.5, ha='center', va='center', zorder=6,
                            bbox=dict(facecolor='#111111', edgecolor='none', alpha=.55, pad=.6))
        label.set_gid('parking-label-' + str(code).replace(' ', '-'))
