"""Run a reproducible Spring 2026 campus simulation.

Example: py -m src.simulation.run_simulation --population 50 --seed 42
Use --population 40000 for the configured maximum population.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from pathlib import Path

from .campus_data import load_campus
from .engine import CampusSimulation
from .population import iter_population

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=int, default=50, help="Number of agents (maximum is 40,000).")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=int, default=112)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/simulation")
    args = parser.parse_args()
    if not 1 <= args.population <= 40000:
        parser.error("--population must be between 1 and 40000")
    graph, buildings, lots, sections = load_campus()
    population = iter_population(args.population, sections, seed=args.seed)
    event_data = json.loads((Path(__file__).with_name("events.json")).read_text(encoding="utf-8"))
    capacity_scale = args.population / 40000
    args.output_dir.mkdir(parents=True, exist_ok=True)
    activity_counts = {}
    log_path = args.output_dir / ("activity_log.csv.gz" if args.population >= 10000 else "activity_log.csv")
    log_stream = gzip.open(log_path, "wt", encoding="utf-8", newline="", compresslevel=1) if args.population >= 10000 else log_path.open("w", encoding="utf-8", newline="")
    with log_stream as stream, \
         (args.output_dir / "agents.json").open("w", encoding="utf-8") as agents_stream:
        writer = csv.DictWriter(stream, fieldnames=["agent_id", "day", "start_minute", "end_minute", "activity", "origin", "destination", "section_id", "event", "route"])
        writer.writeheader()
        agents_stream.write("[\n")
        first_agent = True

        def write_activity(row):
            row["route"] = "->".join(map(str, row.get("route", [])))
            writer.writerow(row)
            activity_counts[row["activity"]] = activity_counts.get(row["activity"], 0) + 1

        def write_agent(agent):
            nonlocal first_agent
            if not first_agent:
                agents_stream.write(",\n")
            json.dump(agent, agents_stream, ensure_ascii=False, separators=(",", ":"))
            first_agent = False

        simulation = CampusSimulation(graph, buildings, lots, event_data["events"], population,
                                      seed=args.seed, capacity_scale=capacity_scale,
                                      record_callback=write_activity, agent_callback=write_agent,
                                      retain_log=False)
        simulation.run(args.days)
        agents_stream.write("\n]\n")
    summary = {"seed": args.seed, "population": args.population, "scale": "1:1", "days": args.days,
               "activity_records": simulation.activity_records, "active_agents": simulation.active_agents,
               "archetypes": len(simulation.archetypes_seen), "capacity_scale": capacity_scale,
               "activities": activity_counts}
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
