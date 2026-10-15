"""Offline regression tests for simulation distances and place metadata."""
import importlib.util
import math
import csv
import pickle
import tempfile
import unittest
from pathlib import Path

import networkx as nx
from shapely.geometry import LineString


class SimulationMetadataTest(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('simulation_metadata'),
                             'Simulation metadata enrichment is not implemented')
        import simulation_metadata
        return simulation_metadata

    def graph(self):
        graph = nx.MultiDiGraph()
        graph.add_node(1, type='path', x=0, y=0)
        graph.add_node(2, type='path', x=.001, y=0)
        return graph

    def test_preserves_walkway_length_instead_of_using_endpoint_chord(self):
        graph = self.graph()
        graph.add_edge(1, 2, length=200)
        self.module().enrich_edges(graph)
        edge = graph[1][2][0]
        self.assertEqual(edge['length'], 200)
        self.assertEqual(edge['distance_m'], 200)
        self.assertAlmostEqual(edge['walk_time_min'], 200 / 84)

    def test_missing_length_uses_full_geometry(self):
        graph = self.graph()
        graph.add_edge(1, 2, geometry=LineString([(0, 0), (.0005, .001), (.001, 0)]))
        self.module().enrich_edges(graph)
        self.assertAlmostEqual(graph[1][2][0]['distance_m'], 248.64, delta=.1)

    def test_invalid_distance_is_rejected(self):
        for value in (-1, float('nan'), float('inf'), 'unknown', True):
            with self.subTest(value=value):
                graph = self.graph()
                graph.add_edge(1, 2, length=value)
                with self.assertRaises(ValueError):
                    self.module().enrich_edges(graph)

    def test_floors_and_capacity_keep_distinct_units(self):
        graph = self.graph()
        graph.add_node('PS', type='parking', category='parking', floors=3, capacity=400)
        graph.add_node('SU', type='building', category='non_academic')
        self.module().enrich_places(graph, [], {})
        self.assertEqual(graph.nodes['PS']['parking_capacity'], 400)
        self.assertEqual(graph.nodes['PS']['capacity_unit'], 'vehicles')
        self.assertIsNone(graph.nodes['SU']['capacity'])
        self.assertEqual(graph.nodes['SU']['capacity_status'], 'unknown')
        self.assertIsNone(graph.nodes['SU']['floors'])

    def test_osm_metadata_and_documented_overrides(self):
        graph = self.graph()
        graph.add_node('DHW', type='building', full_name='Dining Hall West', x=0, y=0)
        features = [dict(osm_type='way', osm_id=123, tags={
            'name': 'Dining Hall West', 'building:levels': '2.5', 'capacity': '800'})]
        overrides = {'DHW': dict(floors=1, floors_source='survey',
                                 capacity=800, capacity_unit='seats',
                                 capacity_source='official publication',
                                 capacity_status='published_historical')}
        self.module().enrich_places(graph, features, overrides)
        self.assertEqual(graph.nodes['DHW']['floors'], 1)
        self.assertEqual(graph.nodes['DHW']['capacity'], 800)
        self.assertEqual(graph.nodes['DHW']['capacity_unit'], 'seats')
        self.assertEqual(graph.nodes['DHW']['capacity_source'], 'official publication')

    def test_ambiguous_osm_numbers_are_unknown(self):
        for value in ('2;3', '2.5', '-1', 'nan', True):
            with self.subTest(value=value):
                self.assertIsNone(self.module().whole_number(value))

    def test_build_does_not_truncate_ambiguous_floor_tags(self):
        from build_graph import extend_graph
        from shapely.geometry import Point
        graph = self.graph()
        catalog = dict(buildings=[dict(code='X', full_name='Test', aliases=['Test'],
                                      category='academic', status='active', source_url='test')],
                       verified_on='2026-10-15', official_map='test', unresolved=[])
        features = [dict(osm_type='way', osm_id=123,
                         tags={'name': 'Test', 'building:levels': '2;3'}, geometry=Point(0, 0))]
        extend_graph(graph, catalog, features)
        self.module().enrich_places(graph, features, {})
        self.assertIsNone(graph.nodes['X']['floors'])

    def test_routes_use_the_same_parallel_edge_for_distance_and_time(self):
        graph = self.graph()
        for node in graph:
            graph.nodes[node].update(type='building', category='academic', routable=True)
        graph.add_edge(1, 2, length=84, walk_time_min=10)
        graph.add_edge(1, 2, length=168, walk_time_min=1)
        graph.add_edge(2, 1, length=84, walk_time_min=10)
        rows = self.module().simulation_routes(graph)
        row = next(r for r in rows if r['start'] == 1)
        self.assertEqual(row['distance_m'], 84)
        self.assertEqual(row['walk_time_min'], 10)

    def test_real_build_exports_all_places_and_is_repeatable(self):
        self.module()
        from build_simulation_graph import build
        source = Path(__file__).parent
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            graph = build(source, output)
            self.assertEqual(graph.nodes['PS4']['parking_capacity'], 1150)
            self.assertEqual(graph.nodes['PS4']['permit_green_pct'], 0)
            self.assertEqual(graph.nodes['PS4']['floors'], 5)
            with (output / 'parking_permit_estimates.csv').open(encoding='utf-8-sig') as file:
                permits = {r['code']: r for r in csv.DictReader(file)}
            self.assertEqual(len(permits), 32)
            self.assertEqual(permits['PS4']['permit_green_pct'], '0')
            self.assertEqual(permits['Lot R']['permit_green_pct'], '')
            self.assertEqual(permits['Lot R']['permit_split_status'], 'unknown')
            self.assertEqual(graph.nodes['Lot M North']['parking_capacity'], 32)
            self.assertEqual(graph.nodes['DHW']['capacity'], 800)
            self.assertIsNone(graph.nodes['SU']['capacity'])
            self.assertTrue(nx.has_path(graph, 'Lot U', 'SU'))
            for _, data in graph.nodes(data=True):
                if data.get('type') != 'path':
                    self.assertIn('floors', data)
                    self.assertIn('capacity', data)
            for _, _, edge in graph.edges(data=True):
                self.assertTrue(math.isfinite(edge['distance_m']))
                self.assertEqual(edge['distance_m'], edge['length'])
            with (output / 'simulation_routes.csv').open(encoding='utf-8-sig') as file:
                self.assertEqual(len(list(csv.DictReader(file))), 6006)
            # A generated simulation graph can also be used as the next source.
            (output / 'utd_graph.pkl').write_bytes((output / 'utd_simulation_graph.pkl').read_bytes())
            import shutil
            shutil.copytree(source / 'cache', output / 'cache')
            rebuilt = build(output, output)
            self.assertEqual(graph.number_of_nodes(), rebuilt.number_of_nodes())
            self.assertEqual(graph.number_of_edges(), rebuilt.number_of_edges())
            self.assertEqual(graph.nodes['PS4'], rebuilt.nodes['PS4'])


if __name__ == '__main__':
    unittest.main()
