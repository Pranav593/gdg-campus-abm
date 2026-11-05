"""Simulation coverage and conservative parking capacity regression checks."""
import tempfile
import unittest
from pathlib import Path

import networkx as nx
from shapely.geometry import Polygon


class CampusCompletionTest(unittest.TestCase):
    def test_complete_build_groups_housing_and_preserves_walkways(self):
        import pickle
        from build_simulation_graph import build
        folder = Path(__file__).parent
        original = pickle.loads((folder / 'utd_graph.pkl').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            graph = build(folder, Path(directory))
        required = {'Housing', 'LAN', 'RCW', 'SUFC', 'ACB', 'DGA', 'PD',
                    'SPORTS', 'TC', 'DART', 'PLINTH', 'Lot Y', 'SU_SSC',
                    'FM', 'SB', 'SG', 'EP', 'SUP'}
        self.assertFalse(required - set(graph), f'Missing destinations: {required - set(graph)}')
        residences = {n for n, d in graph.nodes(data=True)
                      if d.get('category') in ('housing', 'residential')}
        self.assertEqual(residences, {'Housing'})
        self.assertFalse({'RHW', 'RHS', 'RHN', 'RHNW', 'RHSW'} & set(graph))
        self.assertIsNone(graph.nodes['Housing']['floors'])
        self.assertEqual(graph.nodes['LAN']['floors'], 2)
        self.assertEqual(graph.nodes['APC']['floors'], 2)
        self.assertFalse(graph.nodes['SU_SSC']['routable'])
        self.assertEqual(graph.degree('SU_SSC'), 0)
        for place in required - {'SU_SSC'}:
            self.assertTrue(nx.has_path(graph, place, 'JSOM'), place)
            self.assertTrue(nx.has_path(graph, 'JSOM', place), place)
        for a, b, key, edge in original.edges(keys=True, data=True):
            if original.nodes[a].get('type') == original.nodes[b].get('type') == 'path':
                self.assertEqual(graph[a][b][key]['length'], edge['length'])
        self.assertIsNone(graph.nodes['Lot Y']['permit_types'])
        self.assertEqual(graph.nodes['Lot U']['capacity_status'], 'estimated_footprint')
        self.assertGreater(graph.nodes['Lot U']['parking_capacity'], 0)

    def test_parking_estimator_does_not_duplicate_shared_or_ambiguous_areas(self):
        import simulation_metadata as metadata
        self.assertTrue(hasattr(metadata, 'estimate_parking_capacities'), 'Missing parking estimator')
        graph = nx.MultiDiGraph()
        for code, x in [('Lot T 1', .0002), ('Lot T 2', .0008), ('Lot U', .0025)]:
            graph.add_node(code, category='parking', type='parking', x=x, y=.0005,
                           capacity=None, floors=None)
        shapes = [dict(osm_id='way/1', tags={'ref': 'T'},
                       geometry=Polygon([(0, 0), (.001, 0), (.001, .001), (0, .001)])),
                  dict(osm_id='way/2', tags={'ref': 'U'},
                       geometry=Polygon([(.002, 0), (.003, 0), (.003, .001), (.002, .001)]))]
        metadata.estimate_parking_capacities(graph, shapes)
        self.assertIsNone(graph.nodes['Lot T 1']['capacity'])
        self.assertIsNone(graph.nodes['Lot T 2']['capacity'])
        node = graph.nodes['Lot U']
        self.assertEqual(node['capacity'], node['parking_capacity'])
        self.assertEqual(node['capacity_status'], 'estimated_footprint')
        self.assertIn('30', node['capacity_method'])
        self.assertEqual(node['floors_status'], 'not_applicable')
        # Rebuilding must retain documented capacities over estimates.
        graph.nodes['Lot U'].update(capacity=123, capacity_status='documented')
        metadata.estimate_parking_capacities(graph, shapes)
        self.assertEqual(graph.nodes['Lot U']['capacity'], 123)


if __name__ == '__main__':
    unittest.main()
