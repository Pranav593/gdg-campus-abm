"""Stream-validate and combine full-semester occupancy outputs."""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "outputs" / "ml"
SEEDS = (42, 123, 456, 789)
BASE_COLUMNS = (
    "semester_day", "weekday", "time_s", "time_of_day", "building_code",
    "in_class", "seated", "at_event", "idle_or_walking", "total_occupancy",
)
COMPONENTS = ("in_class", "seated", "at_event", "idle_or_walking")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT))


def validate_and_combine() -> dict:
    combined_path = OUTPUT_ROOT / "combined_occupancy.csv"
    combined_tmp = combined_path.with_suffix(".csv.tmp")
    grid_reference = None
    run_results = []
    pattern_hashes = set()
    total_rows = 0

    with combined_tmp.open("w", newline="") as combined_file:
        writer = csv.writer(combined_file)
        writer.writerow(("seed", "run_id", *BASE_COLUMNS))

        for seed in SEEDS:
            run_id = f"seed{seed}"
            run_dir = OUTPUT_ROOT / run_id
            csv_path = run_dir / "occupancy_snapshots.csv"
            manifest_path = run_dir / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            grid_hash = hashlib.sha256()
            pattern_hash = hashlib.sha256()
            previous_key = None
            rows = 0
            errors = []
            days = set()

            with csv_path.open(newline="") as source:
                reader = csv.DictReader(source)
                if tuple(reader.fieldnames or ()) != BASE_COLUMNS:
                    errors.append(f"unexpected columns: {reader.fieldnames}")
                for row in reader:
                    day = int(row["semester_day"])
                    time_s = int(row["time_s"])
                    code = row["building_code"]
                    key = (day, time_s, code)
                    if key == previous_key:
                        errors.append(f"duplicate consecutive key: {key}")
                    previous_key = key
                    days.add(day)
                    if row["weekday"] != WEEKDAYS[day % 5]:
                        errors.append(f"weekday mismatch at {key}")
                    values = [int(row[name]) for name in (*COMPONENTS, "total_occupancy")]
                    if any(value < 0 for value in values):
                        errors.append(f"negative occupancy at {key}")
                    if sum(values[:4]) != values[4]:
                        errors.append(f"component mismatch at {key}")
                    grid_hash.update(f"{day},{time_s},{code}\n".encode())
                    pattern_hash.update((",".join(map(str, values)) + "\n").encode())
                    writer.writerow((seed, run_id, *(row[name] for name in BASE_COLUMNS)))
                    rows += 1
                    if len(errors) >= 20:
                        raise ValueError(f"{run_id}: too many validation errors: {errors}")

            grid_digest = grid_hash.hexdigest()
            if grid_reference is None:
                grid_reference = grid_digest
            elif grid_digest != grid_reference:
                errors.append("time/building grid differs from seed42")
            pattern_digest = pattern_hash.hexdigest()
            if pattern_digest in pattern_hashes:
                errors.append("occupancy pattern duplicates another seed")
            pattern_hashes.add(pattern_digest)
            if days != set(range(75)):
                errors.append(f"day coverage is {min(days, default=None)}..{max(days, default=None)}")
            if rows != 994_500:
                errors.append(f"expected 994500 rows, got {rows}")
            if manifest.get("teleports") != 0:
                errors.append(f"teleports={manifest.get('teleports')}")
            if manifest.get("event_capacity_violations") != 0:
                errors.append(f"event capacity violations={manifest.get('event_capacity_violations')}")
            seating_violations = manifest.get("seating_capacity_violations")
            if seating_violations != 0:
                errors.append(f"seating capacity violations={seating_violations}")
            run_results.append({
                "run_id": run_id, "seed": seed, "status": "valid" if not errors else "invalid",
                "rows": rows, "occupancy_path": relative(csv_path),
                "manifest_path": relative(manifest_path), "runtime_seconds": manifest.get("total_runtime_seconds"),
                "initialization_seconds": manifest.get("initialization_seconds"),
                "peak_memory_bytes": manifest.get("peak_memory_bytes"),
                "teleports": manifest.get("teleports"),
                "seating_capacity_violations": seating_violations,
                "event_capacity_violations": manifest.get("event_capacity_violations"),
                "agents_on_campus_at_close": manifest.get("agents_on_campus_at_close"),
                "grid_sha256": grid_digest, "occupancy_pattern_sha256": pattern_digest,
                "errors": errors,
            })
            total_rows += rows

    combined_tmp.replace(combined_path)
    first_manifest = json.loads((OUTPUT_ROOT / "seed42" / "run_manifest.json").read_text())
    manifest = {
        "schema_version": "1.0",
        "status": "valid" if all(run["status"] == "valid" for run in run_results) else "invalid",
        "configuration": {
            "seeds": list(SEEDS), "agents_per_run": 15_000, "scale_ratio": 2,
            "represented_students_per_run": 30_000, "semester_start_day": 0,
            "instructional_days": 75, "weekdays": list(WEEKDAYS), "snapshot_seconds": 300,
            "graph": first_manifest.get("graph"), "events": first_manifest.get("events"),
            "events_sha256": first_manifest.get("events_sha256"),
            "configuration_version": first_manifest.get("configuration_version"),
            "occupancy_schema_version": first_manifest.get("schema_version"),
        },
        "runs": run_results,
        "combined": {"path": relative(combined_path), "rows": total_rows,
                     "bytes": combined_path.stat().st_size,
                     "columns": ["seed", "run_id", *BASE_COLUMNS]},
        "validation": {
            "four_complete_runs": len(run_results) == 4 and all(r["rows"] == 994_500 for r in run_results),
            "days_0_through_74": all(not any("day coverage" in e for e in r["errors"]) for r in run_results),
            "weekday_progression_valid": all(not any("weekday mismatch" in e for e in r["errors"]) for r in run_results),
            "identical_grids": len({r["grid_sha256"] for r in run_results}) == 1,
            "no_duplicate_keys": all(not any("duplicate" in e for e in r["errors"]) for r in run_results),
            "no_negative_occupancy": all(not any("negative" in e for e in r["errors"]) for r in run_results),
            "component_totals_reconcile": all(not any("component mismatch" in e for e in r["errors"]) for r in run_results),
            "zero_teleports": all(r["teleports"] == 0 for r in run_results),
            "zero_seating_capacity_violations": all(r["seating_capacity_violations"] == 0 for r in run_results),
            "zero_event_capacity_violations": all(r["event_capacity_violations"] == 0 for r in run_results),
            "distinct_seed_patterns": len(pattern_hashes) == 4,
        },
    }
    (OUTPUT_ROOT / "dataset_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    result = validate_and_combine()
    print(json.dumps({"status": result["status"], **result["combined"]}, indent=2))
    sys.exit(result["status"] != "valid")
