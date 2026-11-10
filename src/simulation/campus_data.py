"""Load the supplied Spring 2026 CourseBook sections and UTD walk graph."""
from __future__ import annotations

import csv
import json
import pickle
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COURSES_PATH = ROOT / "data/coursebook/processed/spring_2026_courses.json"
GRAPH_PATH = ROOT / "src/mapping/utd-graph/utd_graph.pkl"
BUILDINGS_PATH = ROOT / "src/mapping/utd-graph/academic_nodes.csv"


def load_campus():
    with COURSES_PATH.open(encoding="utf-8") as stream:
        courses = json.load(stream)
    with GRAPH_PATH.open("rb") as stream:
        graph = pickle.load(stream)
    buildings = {}
    with BUILDINGS_PATH.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            code = row["code"]
            if row["category"] == "academic" and row["status"] == "active" and code in graph:
                buildings[code] = row
    lots = [n for n, data in graph.nodes(data=True) if data.get("category") == "parking" and data.get("routable")]
    if not lots:
        lots = [n for n, data in graph.nodes(data=True) if data.get("type") == "parking"]
    if not lots:
        raise ValueError("The supplied campus graph has no parking destinations.")
    sections = []
    for course in courses:
        for meeting in course.get("meetings", []):
            if meeting.get("day") not in {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}:
                continue
            if meeting.get("building") not in buildings or not meeting.get("start_time") or not meeting.get("end_time"):
                continue
            sections.append({**meeting, "section_id": course["section_id"], "title": course.get("title", "")})
    if not sections:
        raise ValueError("No valid on-campus weekday meetings found in the supplied CourseBook data.")
    return graph, buildings, lots, sections
