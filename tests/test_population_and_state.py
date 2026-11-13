import json
import pickle
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "agents"))
import campus_config as cfg
from campus_sim import CampusModel, StudentAgent, IDLE, WALKING
from population import make_population


class PopulationAndStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(cfg.GRAPH_PATH, "rb") as f:
            cls.graph = pickle.load(f)
        with open(cfg.ARCHETYPES_PATH) as f:
            cls.archetype = json.load(f)["archetypes"][0]

    def spec(self, agent_id=1):
        return {
            "agent_id": agent_id, "archetype_tag": self.archetype["archetype_tag"],
            "commuter_tag": self.archetype["commuter_tag"], "parks_near_first": True,
            "traits": dict(self.archetype["traits"]), "state": dict(self.archetype["state"]),
            "schedule": [], "credits": 0, "target_credits": 13,
        }

    def agent(self, agent_id=1):
        model = CampusModel(self.graph, [], scale_ratio=2, seed=11)
        return StudentAgent(model, self.spec(agent_id))

    def test_hunger_energy_and_exposed_state_stay_synchronized(self):
        agent = self.agent()
        agent.state = IDLE
        agent.hunger_level, agent.energy_level, agent.state_updated_at = 0.2, 0.6, cfg.DAY_START
        agent._update_metabolism(cfg.DAY_START + 3600)
        self.assertGreater(agent.hunger_level, 0.2)
        self.assertGreater(agent.energy_level, 0.6)
        self.assertEqual(agent.info["hunger"], agent.hunger_level)
        self.assertEqual(agent.info["energy"], agent.energy_level)
        agent._consume_meal(cfg.DAY_START + 3600)
        self.assertEqual(agent.hunger_level, 0.05)
        self.assertTrue(0 <= agent.energy_level <= 1)

    def test_walking_reduces_energy_and_low_energy_shortens_study(self):
        low, high = self.agent(2), self.agent(2)
        low.state = WALKING
        low.energy_level, low.state_updated_at = 0.8, cfg.DAY_START
        low._update_metabolism(cfg.DAY_START + 3600)
        self.assertLess(low.energy_level, 0.8)
        low.energy_level, high.energy_level = 0.2, 0.9
        self.assertLess(low._duration("study"), high._duration("study"))

    def test_enrollment_allocation_respects_caps_conflicts_and_credits(self):
        def section(sid, course, start, enrollment):
            prefix, number = course
            return {"section_id": sid, "course_key": course, "course": f"{prefix} {number}",
                    "credits": 3, "credit_source": "course_number", "source_enrollment": enrollment,
                    "max_enrollment": enrollment, "target_enrollment": enrollment,
                    "meetings": [{"section_id": sid, "day": "Monday", "start_time": start,
                                  "end_time": "11:00" if start == "10:00" else "13:00",
                                  "building": "ECSW", "floor": 1, "room": "1",
                                  "start_s": cfg.to_seconds(start),
                                  "end_s": cfg.to_seconds("11:00" if start == "10:00" else "13:00")}]} 
        sections = [section("cs1000.001", ("CS", "1301"), "10:00", 5),
                    section("math1000.001", ("MATH", "1301"), "12:00", 6)]
        pool = {s["course_key"]: [s] for s in sections}
        archetype = dict(self.archetype, population_weight=1.0)
        agents, report = make_population([archetype], 10, pool, random.Random(4),
                                         scale_ratio=2, return_report=True)
        self.assertEqual(report["over_capacity_sections"], 0)
        self.assertEqual(report["conflicting_agents"], 0)
        self.assertEqual(report["agents_over_19_credits"], 0)
        self.assertEqual(report["assigned_enrollment"], 11)
        self.assertTrue(all(len({m["section_id"] for m in a["schedule"]}) <= 2 for a in agents))


if __name__ == "__main__":
    unittest.main()
