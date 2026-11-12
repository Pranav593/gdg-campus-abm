"""Run requested full-semester seeds concurrently with independent logs/status."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "ml"
LOGS = OUT / "logs"


def complete(seed):
    folder = OUT / f"seed{seed}"
    try:
        manifest = json.loads((folder / "run_manifest.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return (manifest.get("seed") == seed and manifest.get("days") == 75
            and manifest.get("occupancy_rows") == 994500
            and (folder / "occupancy_snapshots.csv").exists())


def main():
    seeds = [int(x) for x in sys.argv[1:]]
    LOGS.mkdir(parents=True, exist_ok=True)
    processes = {}
    started = time.time()
    for seed in seeds:
        if complete(seed):
            print(f"seed {seed}: already complete", flush=True)
            continue
        log_path = LOGS / f"seed{seed}.log"
        log = log_path.open("w")
        command = [sys.executable, "src/agents/campus_sim.py", "--scale", "2",
                   "--days", "75", "--start-day", "0", "--seed", str(seed),
                   "--events", "src/agents/events.json",
                   "--out", f"outputs/ml/seed{seed}"]
        process = subprocess.Popen(command, cwd=ROOT, stdout=log,
                                   stderr=subprocess.STDOUT)
        processes[seed] = (process, log, time.time(), log_path)
        print(f"seed {seed}: started pid {process.pid}", flush=True)
    results = {}
    while processes:
        for seed, (process, log, seed_start, log_path) in list(processes.items()):
            code = process.poll()
            if code is None:
                continue
            log.close()
            results[str(seed)] = {"exit_code": code,
                                  "wall_seconds": time.time() - seed_start,
                                  "log": str(log_path.relative_to(ROOT))}
            del processes[seed]
            print(f"seed {seed}: exit {code}", flush=True)
        if processes:
            time.sleep(5)
    status = {"wall_seconds": time.time() - started, "runs": results}
    (LOGS / "parallel_status.json").write_text(json.dumps(status, indent=2) + "\n")
    if any(result["exit_code"] for result in results.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
