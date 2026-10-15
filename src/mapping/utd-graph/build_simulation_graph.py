"""Build a campus simulation graph with floors, capacities and meter distances.

Run: python build_simulation_graph.py [--source-dir DIR] [--output-dir DIR]
Uses the bundled graph, inventory and OSM cache without downloading map data.
"""
import argparse
import json
import pickle
from pathlib import Path

from build_graph import cached_buildings, extend_graph
from simulation_metadata import enrich_edges, enrich_places, export_simulation


def build(source, output):
    folder = Path(__file__).parent
    catalog = json.loads((folder / 'academic_buildings.json').read_text(encoding='utf-8'))
    extras = json.loads((folder / 'simulation_places.json').read_text(encoding='utf-8'))
    known = {record['code'] for record in catalog['buildings']}
    catalog['buildings'].extend(record for record in extras['buildings'] if record['code'] not in known)
    with (source / 'utd_graph.pkl').open('rb') as file:
        graph = pickle.load(file)
    features = cached_buildings(source / 'cache')
    extend_graph(graph, catalog, features)
    enrich_edges(graph)
    enrich_places(graph, features, extras['metadata'])
    graph.graph['destination_scope'] = 'campus_simulation'
    graph.graph['osm_snapshot_date'] = '2026-10-01'
    # Display routes describe the original map, not this graph's full scope.
    graph.graph.pop('academic_display_routes', None)
    export_simulation(graph, output)
    print(f'Simulation: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges -> {output}')
    return graph


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=Path(__file__).parent)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    build(args.source_dir, args.output_dir)
