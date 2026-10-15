"""Parking outlines must match real geometry and route ends must stop at it."""
import importlib.util
import unittest

from shapely.geometry import Polygon


class ParkingAreasTest(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('parking_areas'), 'Parking area rendering is missing')
        import parking_areas
        return parking_areas

    def feature(self, ref='A'):
        return dict(osm_id=1, tags={'amenity': 'parking', 'ref': ref},
                    geometry=Polygon([(0, 0), (2, 0), (2, 2), (0, 2)]))

    def test_matches_subdivision_to_containing_lot(self):
        areas, review = self.module().match_areas(
            [('Lot A1', {'x': 1, 'y': 1, 'category': 'parking'})], [self.feature()])
        self.assertEqual(set(areas), {'Lot A1'})
        self.assertEqual(review, [])

    def test_conflicting_or_missing_boundaries_are_not_guessed(self):
        areas, review = self.module().match_areas([
            ('Lot W', {'x': 1, 'y': 1, 'category': 'parking'}),
            ('Lot A2', {'x': 3, 'y': 1, 'category': 'parking'})], [self.feature('T')])
        self.assertEqual(areas, {})
        self.assertEqual({r['code'] for r in review}, {'Lot W', 'Lot A2'})

    def test_route_stops_on_polygon_boundary(self):
        pieces = self.module().outside_segments([(-2, 1), (1, 1)], [self.feature()['geometry']])
        self.assertEqual(pieces, [[(-2.0, 1.0), (0.0, 1.0)]])

    def test_route_between_areas_preserves_the_outside_bend(self):
        left = Polygon([(-3, 0), (-1, 0), (-1, 2), (-3, 2)])
        right = self.feature()['geometry']
        pieces = self.module().outside_segments([(-2, 1), (-.5, 3), (1, 1)], [left, right])
        self.assertEqual(len(pieces), 1)
        self.assertIn((-.5, 3.0), pieces[0])
        self.assertAlmostEqual(pieces[0][0][1], 2)
        self.assertAlmostEqual(pieces[0][-1][1], 2)


if __name__ == '__main__':
    unittest.main()
