"""Check the real campus graph's destination coverage and walk connections."""
import math
import pickle
import sys
import unittest
from pathlib import Path

import networkx as nx

GRAPH_PATH = Path(sys.argv.pop(1)) if len(sys.argv) > 1 else Path(__file__).with_name('utd_graph.pkl')
EXPECTED = set('AD ATC BE BSB CB CR CRA ECSN ECSS ECSW FA FN FO GR HH JO JSOM MC ML1 ML2 NB NL PHA PHY SCI SLC TH WSTC RL ROC ROW SPN SP2 WAAC APC DAV'.split())


class AcademicGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with GRAPH_PATH.open('rb') as f:
            cls.graph = pickle.load(f)

    def test_all_confirmed_academic_buildings_present(self):
        self.assertEqual(EXPECTED - set(self.graph), set(), 'Missing confirmed academic nodes')

    def test_academic_walk_connections_and_travel_times(self):
        graph = self.graph
        for code in EXPECTED & set(graph):
            with self.subTest(building=code):
                node = graph.nodes[code]
                self.assertEqual(node['type'], 'building')
                self.assertTrue(node.get('full_name'))
                self.assertTrue(math.isfinite(node['x']) and math.isfinite(node['y']))
                neighbors = list(graph.successors(code))
                self.assertTrue(neighbors)
                for near in neighbors:
                    self.assertEqual(graph.nodes[near]['type'], 'path')
                    self.assertTrue(graph.has_edge(near, code))
                    for edge in graph[code][near].values():
                        self.assertAlmostEqual(edge['walk_time_min'], edge['length'] / 1.4 / 60)
                self.assertTrue(nx.has_path(graph, code, 'JSOM'))
                self.assertTrue(nx.has_path(graph, 'JSOM', code))

    def test_academic_routes_work(self):
        for start, end in [('ECSS', 'ECSW'), ('ECSW', 'JSOM'), ('ATC', 'JO'), ('SP2', 'APC'), ('ROW', 'CR')]:
            route = nx.shortest_path(self.graph, start, end, weight='length')
            self.assertGreater(nx.path_weight(self.graph, route, 'length'), 0)

    def test_no_nonacademic_destinations(self):
        destinations = {n for n, d in self.graph.nodes(data=True) if d.get('type') != 'path'}
        self.assertEqual(destinations, EXPECTED | {'GC', 'APC2'})
        for n in destinations:
            self.assertEqual(self.graph.nodes[n].get('category'), 'academic')

    def test_displayed_routes_join_all_academic_destinations(self):
        routes = self.graph.graph['academic_display_routes']
        connections = nx.Graph()
        self.assertEqual(len(routes), len(EXPECTED) - 1)
        for connection in routes:
            start, end, path = connection['start'], connection['end'], connection['path']
            self.assertIn(start, EXPECTED)
            self.assertIn(end, EXPECTED)
            self.assertEqual((path[0], path[-1]), (start, end))
            self.assertTrue(nx.is_path(self.graph, path))
            connections.add_edge(start, end)
        self.assertEqual(set(connections), EXPECTED)
        self.assertTrue(nx.is_connected(connections))

    def test_closed_and_unbuilt_sites_are_not_walk_destinations(self):
        for code in ['GC', 'APC2']:
            with self.subTest(building=code):
                self.assertIn(code, self.graph)
                self.assertFalse(self.graph.nodes[code]['routable'])
                self.assertEqual(self.graph.degree(code), 0)


if __name__ == '__main__':
    unittest.main()
