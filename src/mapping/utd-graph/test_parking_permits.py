"""Permit estimates must never invent a designation or hide an unknown."""
import importlib.util
import json
from pathlib import Path
import unittest

import networkx as nx


class ParkingPermitTest(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('parking_permits'), 'Permit metadata is missing')
        import parking_permits
        return parking_permits

    def catalog(self):
        return json.loads(Path(__file__).with_name('parking_permits.json').read_text(encoding='utf-8'))

    def test_garages_have_no_green_and_keep_other_spaces(self):
        graph = nx.MultiDiGraph()
        for code in ['PS1', 'PS3', 'PS4']:
            graph.add_node(code, type='parking', category='parking')
        self.module().enrich_permits(graph, self.catalog())
        for _, data in graph.nodes(data=True):
            self.assertEqual(data['permit_green_pct'], 0)
            self.assertNotIn('green', data['permit_types'])
            self.assertGreater(data['permit_other_pct'], 0)
            self.assertAlmostEqual(sum(data['permit_split_pct'].values()), 100)

    def test_residential_and_metered_lots_do_not_acquire_commuter_colors(self):
        graph = nx.MultiDiGraph()
        for code in ['Res Lot North', 'Res Lot North West', 'Lot F']:
            graph.add_node(code, category='parking')
        self.module().enrich_permits(graph, self.catalog())
        for _, data in graph.nodes(data=True):
            self.assertEqual(data['permit_types'], [])
            self.assertEqual(data['permit_other_pct'], 100)

    def test_unresolved_and_unlisted_lots_are_null_not_zero(self):
        graph = nx.MultiDiGraph()
        for code in ['Lot R', 'Future lot']:
            graph.add_node(code, category='parking')
        self.module().enrich_permits(graph, self.catalog())
        for _, data in graph.nodes(data=True):
            self.assertIsNone(data['permit_green_pct'])
            self.assertIsNone(data['permit_types'])
            self.assertEqual(data['permit_split_status'], 'unknown')

    def test_unverified_color_and_invalid_totals_are_rejected(self):
        for change in ['unverified_color', 'total', 'boolean']:
            with self.subTest(change=change):
                catalog = self.catalog()
                record = catalog['lots']['Lot U']
                if change == 'unverified_color':
                    record['split_pct']['purple'] = 1
                    record['split_pct']['green'] -= 1
                elif change == 'total':
                    record['split_pct']['green'] = 10
                else:
                    record['split_pct']['green'] = True
                graph = nx.MultiDiGraph()
                graph.add_node('Lot U', category='parking')
                with self.assertRaises(ValueError):
                    self.module().enrich_permits(graph, catalog)

    def test_existing_capacity_and_nonparking_nodes_are_unchanged(self):
        graph = nx.MultiDiGraph()
        graph.add_node('PS4', category='parking', capacity=1150)
        graph.add_node('ECSW', category='academic')
        self.module().enrich_permits(graph, self.catalog())
        self.assertEqual(graph.nodes['PS4']['capacity'], 1150)
        self.assertNotIn('permit_types', graph.nodes['ECSW'])

    def test_csv_distinguishes_no_commuter_colors_from_unknown(self):
        module = self.module()
        graph_row = {'permit_types': ['gold', 'orange']}
        self.assertEqual(json.loads(module.csv_place(graph_row)['permit_types']), ['gold', 'orange'])
        self.assertEqual(graph_row['permit_types'], ['gold', 'orange'])
        self.assertEqual(module.csv_place({'permit_types': []})['permit_types'], '[]')
        self.assertIsNone(module.csv_place({'permit_types': None})['permit_types'])


if __name__ == '__main__':
    unittest.main()
