"""
Project filename:
Authors: Meghana,
Project file description:
Agent / Mesa Group (Agent-based modeling framework) for simulating student behavior in a campus environment. This module defines the StudentAgent class, which represents individual students navigating through the campus graph and interacting with courses from the CourseBook dataset.
Use the existing working campus graph and CourseBook dataset (spring_2026_courses.json) to begin the first version of a student agent.

"""

import pickle
import networkx as nx
import mesa

class StudentAgent(mesa.Agent):
    def __init__(self, model, schedule):
        super().__init__(model)
        self.schedule = schedule
        self.current_location = None

    def step(self):
        pass

class CampusModel(mesa.Model):
    def __init__(self, graph):
        super().__init__()
        self.graph = graph

    def step(self):
        self.agents.do("step")


with open("utd-graph/utd_graph.pkl", "rb") as f:
    G = pickle.load(f)

route = nx.shortest_path(
    G,
    source="ECSW",
    target="JSOM",
    weight="length"
)
