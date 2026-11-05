"""Draw grouped campus housing from cached OSM building footprints."""
from shapely.ops import unary_union


def housing_groups(features):
    groups = {'University Commons': [], 'University Village': [], 'Canyon Creek Heights': []}
    halls = {'Sirius Hall', 'Capella Hall', 'Vega Hall', 'Helix Hall', 'Andromeda Hall'}
    for feature in features:
        tags = feature['tags']
        name = tags.get('name', '')
        shape = feature.get('geometry')
        if shape is None or shape.is_empty:
            continue
        if name in halls and tags.get('building') == 'dormitory':
            group = 'University Commons'
        elif name.startswith('Canyon Creek Heights') and tags.get('building') == 'dormitory':
            group = 'Canyon Creek Heights'
        elif (tags.get('building') == 'apartments' and
              (name.isdigit() or name in ('University Village Leasing Office', 'Phase 2 Clubhouse', 'Phase 8 Clubhouse', 'Clubhouse')) and
              -96.757 < shape.centroid.x < -96.751 and 32.9818 < shape.centroid.y < 32.9898):
            group = 'University Village'
        else:
            continue
        groups[group].append(shape)
    return {name: shapes for name, shapes in groups.items() if shapes}


def draw_housing(ax, features, housing_node):
    from matplotlib.patches import Polygon
    groups = housing_groups(features)
    for name, shapes in groups.items():
        # This envelope is a visual grouping, not an official land boundary.
        outline = unary_union(shapes).convex_hull.buffer(.00006)
        patch = Polygon(list(outline.exterior.coords), closed=True, facecolor='#9467df',
                        edgecolor='#d2b8ff', alpha=.18, linewidth=1, linestyle='--', zorder=1.5)
        patch.set_gid('housing-area-' + name.replace(' ', '-'))
        ax.add_patch(patch)
        for shape in shapes:
            for part in (shape.geoms if shape.geom_type == 'MultiPolygon' else [shape]):
                footprint = Polygon(list(part.exterior.coords), closed=True, facecolor='#9467df',
                                    edgecolor='#d2b8ff', alpha=.5, linewidth=.5, zorder=2)
                ax.add_patch(footprint)
        center = outline.centroid
        ax.annotate('Housing\n' + name, (center.x, center.y), color='#eadcff',
                    ha='center', va='center', fontsize=7, zorder=8,
                    bbox=dict(facecolor='#21172f', edgecolor='#d2b8ff', alpha=.85, pad=2))
    if housing_node:
        ax.scatter(housing_node['x'], housing_node['y'], marker='D', s=40,
                   color='#d2b8ff', edgecolor='white', zorder=8)
        ax.annotate('Housing access', (housing_node['x'], housing_node['y']),
                    xytext=(-6, -12), textcoords='offset points', ha='right',
                    fontsize=7, color='#eadcff', zorder=9)
    ax.text(.01, .945, 'Purple: Housing | dashed outlines are approximate footprint groupings',
            transform=ax.transAxes, fontsize=6, color='#eadcff', va='top',
            bbox=dict(facecolor='#111111', edgecolor='none', alpha=.85))
    return groups
