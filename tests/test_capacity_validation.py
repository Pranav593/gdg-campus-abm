"""Regression checks for the physical seating contract and supplied campus map."""
import json
import pickle
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "agents"))
import campus_config as cfg
from campus_sim import CampusModel


class CapacityValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(cfg.GRAPH_PATH, "rb") as f:
            cls.graph = pickle.load(f)

    def model(self, scale=1):
        return CampusModel(self.graph, [], scale_ratio=scale, seed=7)

    def test_measured_floor_capacities_preserve_source_values(self):
        # The supplied individual entries total 1,812.  The brief's 2,029 total is
        # arithmetically inconsistent, so this protects the actual floor data.
        self.assertEqual(sum(sum(f.values()) for f in cfg.SEATING_FULL.values()), 1812)
        self.assertEqual(cfg.SEATING_FULL["JO"], {1: 0, 2: 16, 3: 49, 4: 95, 5: 62})
        self.assertEqual(cfg.SEATING_FULL["GR"], {2: 28, 3: 38, 4: 40})
        self.assertEqual(cfg.SEATING_FULL["JSOM1"], {1: 57, 2: 100, 3: 0, 4: 0})
        self.assertEqual(cfg.SEATING_FULL["JSOM2"], {1: 84, 2: 78, 3: 15, 4: 10})
        self.assertEqual(cfg.SEATING_FULL["HH"], {1: 47})
        self.assertEqual(cfg.SEATING_FULL["ML1"], {1: 11})
        self.assertEqual(cfg.SEATING_FULL["ML2"], {1: 18})
        self.assertEqual(cfg.SEATING_FULL["PHYA"], {1: 60})
        self.assertEqual(cfg.SEATING_FULL["AB"], {1: 40})
        self.assertEqual(cfg.SEATING_FULL["ACB"], {1: 60})
        self.assertEqual(cfg.SEATING_FULL["AD"], {1: 20, 2: 50, 3: 30})
        self.assertEqual(cfg.SEATING_FULL["APC"], {1: 100, 2: 0})
        self.assertEqual(cfg.SEATING_FULL["ATC"], {1: 120, 2: 45, 3: 50})
        for key, seats in {"ECSN": 70, "ECSS": 89, "ECSW": 185, "FO": 85, "FA": 20, "FN": 40}.items():
            self.assertEqual(cfg.SEATING_FULL[key], {1: seats})

    def test_aliases_and_restrictions(self):
        self.assertEqual(cfg.NODE_ALIAS["JSOM1"], "JSOM")
        self.assertEqual(cfg.NODE_ALIAS["JSOM2"], "JSOM")
        self.assertEqual(cfg.NODE_ALIAS["PHYA"], "PHA")
        model = self.model()
        for node in cfg.INACCESSIBLE_BUILDINGS:
            self.assertNotIn(node, model.seat_nodes)
        self.assertNotIn("JO", [n for n in model.seat_nodes if model.seats[n].get(1, 1) > 0 and n == "JO"])

    def test_default_academic_capacities_and_physical_invariance(self):
        one, ten = self.model(1), self.model(10)
        self.assertEqual(one.seat_cap, ten.seat_cap)
        self.assertIn("SCI", one.default_seat_nodes)
        self.assertEqual(one.seat_cap["SCI"], 100)
        self.assertNotIn("NB", one.default_seat_nodes)
        self.assertNotIn("NL", one.default_seat_nodes)
        self.assertNotIn("APC2", one.default_seat_nodes)

    def test_claim_does_not_overbook_and_releases(self):
        model = self.model()
        initial = model.seat_cap["HH"]
        rng = random.Random(1)
        claimed = []
        while True:
            floor = model.claim("HH", rng)
            if floor is None:
                break
            claimed.append(floor)
        self.assertEqual(len(claimed), initial)
        self.assertIsNone(model.claim("HH", rng))
        for floor in claimed:
            model.release("HH", floor)
        self.assertEqual(model.free_total["HH"], initial)

    def test_routes_and_seating_alternative_are_usable(self):
        model = self.model()
        self.assertIsNotNone(model.dist("JO", "ECSW"))
        model.free_total["HH"] = 0
        model.seats["HH"] = {1: 0}
        self.assertTrue(any(model.free_total[n] > 0 for n in model.seat_nodes if n != "HH"))

    def test_consolidated_map_routes_su_and_verified_lots(self):
        self.assertIn("SU", self.graph)
        self.assertIn("Lot A1", self.graph)
        self.assertIsNotNone(self.model().dist("SU", "ECSW"))
        self.assertIsNotNone(self.model().dist("Lot M North", "JSOM"))

    def test_exact_unnamed_event_schema_loads(self):
        with open(ROOT / "tests" / "events_exact.json") as f:
            events = json.load(f)["events"]
        model = CampusModel(self.graph, events, scale_ratio=2, seed=7)
        self.assertEqual(len(model.exam_periods), 1)
        self.assertEqual(len(model.campus_events), 1)
        self.assertEqual(model.campus_events[0]["building"], "SU")
        self.assertEqual(model.campus_events[0]["cap"], 200)


if __name__ == "__main__":
    unittest.main()
