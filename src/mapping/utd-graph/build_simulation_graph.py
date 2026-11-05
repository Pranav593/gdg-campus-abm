"""Build a campus simulation graph with floors, capacities and meter distances.

Run: python build_simulation_graph.py [--source-dir DIR] [--output-dir DIR]
Uses the bundled graph, inventory and OSM cache without downloading map data.
"""
import argparse
import json
import pickle
from pathlib import Path

from build_graph import cached_buildings, extend_graph
from simulation_metadata import enrich_edges, enrich_places, export_simulation, estimate_parking_capacities


def build(source, output):
    folder = Path(__file__).parent
    catalog = json.loads((folder / 'academic_buildings.json').read_text(encoding='utf-8'))
    extras = json.loads((folder / 'simulation_places.json').read_text(encoding='utf-8'))
    known = {record['code'] for record in catalog['buildings']}
    catalog['buildings'].extend(record for record in extras['buildings'] if record['code'] not in known)
    with (source / 'utd_graph.pkl').open('rb') as file:
        graph = pickle.load(file)
    features = cached_buildings(source / 'cache')
    # Remove individual residential destinations even when rebuilding an older
    # simulation graph. Never remove the underlying walking network.
    graph.remove_nodes_from([n for n, d in graph.nodes(data=True)
                             if d.get('category') == 'residential' or
                             n in ('RHW', 'RHS', 'RHN', 'RHNW', 'RHSW')])
    extend_graph(graph, catalog, features)
    for record in catalog['buildings']:
        graph.nodes[record['code']]['full_name'] = record['full_name']
    enrich_edges(graph)
    enrich_places(graph, features, extras['metadata'])
    from parking_areas import cached_parking
    estimate_parking_capacities(graph, cached_parking(source / 'cache'))
    for record in extras['buildings']:
        data = graph.nodes[record['code']]
        for field in ('destination_kind', 'services', 'location_notes', 'members'):
            if field in record:
                data[field] = record[field]
        if record.get('location_notes') and 'lat' in record:
            data['coordinate_source'] = 'approximate official-map position / representative access point'
        if record['category'] in ('housing', 'outdoor', 'transit'):
            data.update(floors=None, floors_status='not_applicable', floors_source=None)
    graph.graph['campus_inventory_source'] = extras['source']
    graph.nodes['MC'].update(destination_kind='library', services=['library', 'study', 'food'])
    graph.graph['destination_code_aliases'] = {'AB': 'AC', 'SSA': 'SSBA', 'VCB': 'ACB'}
    graph.graph['destination_scope'] = 'campus_simulation'
    graph.graph['osm_snapshot_date'] = '2026-10-01'
    # Display routes describe the original map, not this graph's full scope.
    graph.graph.pop('academic_display_routes', None)
    # Observed seating is distinct from occupancy and parking capacity.
    seating = json.loads((folder / 'seating_counts.json').read_text(encoding='utf-8'))
    for code, observation in seating['records'].items():
        if code not in graph:
            raise ValueError(f'Unknown seating destination: {code}')
        graph.nodes[code].update(observation, seating_source=seating['source'])
    graph.graph['seating_scope'] = seating['scope']
    graph.graph['seating_review'] = seating['unresolved_observations']
    export_simulation(graph, output)
    print(f'Simulation: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges -> {output}')
    return graph


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, default=Path(__file__).parent)
    parser.add_argument('--output-dir', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    build(args.source_dir, args.output_dir)
