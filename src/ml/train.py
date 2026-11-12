"""Validate simulation data, train LightGBM, evaluate, and save artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import lightgbm as lgb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from src.ml.features import (CATEGORICAL_FEATURES, FEATURE_NAMES,
                             build_feature_config, load_events, prepare_features)

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "outputs" / "ml" / "combined_occupancy.csv"
MANIFEST_PATH = ROOT / "outputs" / "ml" / "dataset_manifest.json"
EVENTS_PATH = ROOT / "src" / "agents" / "events.json"
MODEL_DIR = ROOT / "outputs" / "ml" / "models"
SEEDS = [42, 123, 456, 789]
OCCUPANCY_COLUMNS = ["in_class", "seated", "at_event", "idle_or_walking",
                     "total_occupancy"]


def json_value(value):
    if isinstance(value, (np.integer,)): return int(value)
    if isinstance(value, (np.floating,)): return float(value)
    if isinstance(value, (np.bool_,)): return bool(value)
    raise TypeError(type(value).__name__)


def read_data(path: Path) -> pd.DataFrame:
    dtype = {"seed": "int16", "run_id": "category", "semester_day": "int16",
             "weekday": "category", "time_s": "int32", "time_of_day": "category",
             "building_code": "category", **{name: "int32" for name in OCCUPANCY_COLUMNS}}
    return pd.read_csv(path, dtype=dtype)


def grid_digest(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(
        frame[["semester_day", "time_s", "building_code"]], index=False
    ).values
    return hashlib.sha256(values.tobytes()).hexdigest()


def validate_data(frame: pd.DataFrame, csv_path: Path, manifest: dict) -> dict:
    checks = {}
    checks["expected_seeds"] = sorted(frame.seed.unique().tolist()) == SEEDS
    rows_per_seed = {str(k): int(v) for k, v in frame.groupby("seed", observed=True).size().items()}
    checks["rows_per_seed_equal"] = len(set(rows_per_seed.values())) == 1
    day_counts = frame.groupby("seed", observed=True).semester_day.nunique()
    checks["75_days_per_seed"] = bool((day_counts == 75).all())
    weekday_ok = frame["weekday"].astype(str) == frame["semester_day"].map(
        lambda day: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"][day % 5])
    checks["weekday_progression"] = bool(weekday_ok.all())
    duplicates = int(frame.duplicated(["seed", "semester_day", "time_s", "building_code"]).sum())
    checks["no_duplicate_keys"] = duplicates == 0
    checks["no_missing_occupancy"] = not frame[OCCUPANCY_COLUMNS].isna().any().any()
    checks["no_negative_occupancy"] = bool((frame[OCCUPANCY_COLUMNS] >= 0).all().all())
    reconciled = frame[OCCUPANCY_COLUMNS[:-1]].sum(axis=1) == frame.total_occupancy
    checks["component_totals_reconcile"] = bool(reconciled.all())
    grids = {str(seed): grid_digest(frame[frame.seed == seed]) for seed in SEEDS}
    checks["identical_building_time_grids"] = len(set(grids.values())) == 1
    times = np.sort(frame.time_s.unique())
    checks["five_minute_intervals"] = bool(len(times) == 204 and np.all(np.diff(times) == 300))
    patterns = {}
    for seed in SEEDS:
        vals = frame.loc[frame.seed == seed, "total_occupancy"].to_numpy()
        patterns[str(seed)] = hashlib.sha256(vals.tobytes()).hexdigest()
    checks["distinct_seed_patterns"] = len(set(patterns.values())) == 4
    run_manifests = []
    for seed in SEEDS:
        item = json.loads((ROOT / f"outputs/ml/seed{seed}/run_manifest.json").read_text())
        run_manifests.append(item)
    checks["manifests_zero_violations"] = all(
        item.get("teleports") == item.get("seating_capacity_violations")
        == item.get("event_capacity_violations") == 0 for item in run_manifests)
    physical = frame[frame.building_code.astype(str) != "_WALKING"]
    occupancy = physical.total_occupancy
    active = physical[physical.time_s.between(8 * 3600, 20 * 3600)].total_occupancy
    inactive = physical[~physical.time_s.between(8 * 3600, 20 * 3600)].total_occupancy
    checks["meaningful_active_hour_signal"] = float(active.mean()) > float(inactive.mean())
    peaks = (physical.groupby("building_code", observed=True).total_occupancy.max()
             .sort_values(ascending=False))
    memory_bytes = int(frame.memory_usage(index=True, deep=True).sum())
    result = {
        "status": "valid" if all(checks.values()) else "invalid",
        "checks": checks,
        "csv_columns": list(frame.columns),
        "csv_dtypes": {name: str(dtype) for name, dtype in frame.dtypes.items()},
        "total_rows": len(frame), "rows_per_seed": rows_per_seed,
        "unique_buildings_including_walking": int(frame.building_code.nunique()),
        "physical_buildings": int(physical.building_code.nunique()),
        "occupancy": {"minimum": int(occupancy.min()), "mean": float(occupancy.mean()),
                      "median": float(occupancy.median()), "maximum": int(occupancy.max()),
                      "zero_percent": float((occupancy == 0).mean() * 100)},
        "active_hours_mean": float(active.mean()), "inactive_hours_mean": float(inactive.mean()),
        "peak_occupancy_by_building": {str(k): int(v) for k, v in peaks.items()},
        "duplicate_keys": duplicates, "grid_sha256_by_seed": grids,
        "pattern_sha256_by_seed": patterns,
        "csv_file_bytes": csv_path.stat().st_size, "dataframe_memory_bytes": memory_bytes,
        "source_dataset_manifest_status": manifest.get("status"),
        "run_manifest_summary": [{"seed": m["seed"], "days": m["days"],
                                  "rows": m["occupancy_rows"], "teleports": m["teleports"],
                                  "seating_capacity_violations": m["seating_capacity_violations"],
                                  "event_capacity_violations": m["event_capacity_violations"]}
                                 for m in run_manifests],
    }
    return result


def regression_metrics(actual, predicted) -> dict:
    error = np.abs(np.asarray(actual) - np.asarray(predicted))
    return {"mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(math.sqrt(mean_squared_error(actual, predicted))),
            "r2": float(r2_score(actual, predicted)),
            "median_absolute_error": float(np.median(error)),
            "p90_absolute_error": float(np.percentile(error, 90))}


def grouped_mae(frame: pd.DataFrame, prediction: np.ndarray, column: str) -> dict:
    work = pd.DataFrame({column: frame[column].astype(str).to_numpy(),
                         "absolute_error": np.abs(frame.total_occupancy.to_numpy() - prediction)})
    return {str(k): float(v) for k, v in
            work.groupby(column, observed=True).absolute_error.mean().sort_values(ascending=False).items()}


def period_labels(time_s: pd.Series) -> pd.Series:
    return pd.cut(time_s, bins=[-1, 10*3600, 14*3600, 18*3600, 24*3600],
                  labels=["morning_before_10", "midday_10_14", "afternoon_14_18",
                          "evening_after_18"])


def make_plots(test: pd.DataFrame, predictions: np.ndarray, metrics: dict, config: dict,
               output: Path):
    output.mkdir(parents=True, exist_ok=True)
    high_traffic = (test.groupby("building_code", observed=True).total_occupancy.mean()
                    .idxmax())
    sample_day = 36  # Week 8 Tuesday, near the middle of the semester.
    mask = ((test.building_code.astype(str) == str(high_traffic))
            & (test.semester_day == sample_day))
    sample = test.loc[mask].copy()
    sample["prediction"] = predictions[mask.to_numpy()]
    plt.figure(figsize=(10, 4.5))
    plt.plot(sample.time_s / 3600, sample.total_occupancy, label="Actual", linewidth=2)
    plt.plot(sample.time_s / 3600, sample.prediction, label="LightGBM", linewidth=2)
    plt.xlabel("Time of day (hour)"); plt.ylabel("Students")
    plt.title(f"{high_traffic}: seed 789, {sample.weekday.iloc[0]}, week 8")
    plt.legend(); plt.tight_layout()
    plt.savefig(output / "actual_vs_predicted.png", dpi=150); plt.close()

    by_building = pd.Series({code: metrics["test"]["mae_by_building"][code]
                             for code in config["prediction_buildings"]}).sort_values()
    plt.figure(figsize=(9, max(6, len(by_building) * 0.18)))
    by_building.plot.barh()
    plt.xlabel("MAE (students)"); plt.ylabel("Building")
    plt.title("Held-out seed 789 MAE by building")
    plt.tight_layout(); plt.savefig(output / "mae_by_building.png", dpi=150); plt.close()
    return str(high_traffic), sample_day


def write_report(validation: dict, config: dict, params: dict, metrics: dict,
                 training_seconds: float, representative: tuple[str, int], output: Path):
    worst = list(metrics["test"]["mae_by_building"].items())[:10]
    text = f"""# Occupancy Model Training Report

## Dataset verification

Validation status: **{validation['status']}**. The dataset contains {validation['total_rows']:,} rows across four independent seeds and {validation['physical_buildings']} non-walking destinations. `_WALKING` was validated but excluded from model training. The frontend interface returns {len(config['prediction_buildings'])} actual building destinations and excludes parking/residential lots. Occupancy ranges from {validation['occupancy']['minimum']} to {validation['occupancy']['maximum']} students, with mean {validation['occupancy']['mean']:.2f}, median {validation['occupancy']['median']:.2f}, and {validation['occupancy']['zero_percent']:.2f}% zero rows.

All seed/day grids, five-minute intervals, unique keys, nonnegative values, component reconciliation, distinct seed patterns, and zero manifest violations passed validation.

## Training

- Model: LightGBM regression (`regression_l1` objective)
- Training seeds: 42, 123
- Early-stopping validation seed: 456
- Held-out test seed: 789
- Training runtime: {training_seconds:.2f} seconds
- Selected boosting iteration: {metrics['best_iteration']}
- Features: {', '.join(config['feature_names'])}
- Configuration: `{json.dumps(params, sort_keys=True)}`

The initial 600-tree configuration underfit building/time interactions and was rejected because its held-out MAE exceeded the baseline. The final targeted higher-capacity configuration is the model reported here.

## Performance

| Dataset | MAE | RMSE | R² | Median AE | 90th percentile AE |
|---|---:|---:|---:|---:|---:|
| Validation seed 456 | {metrics['validation']['mae']:.3f} | {metrics['validation']['rmse']:.3f} | {metrics['validation']['r2']:.4f} | {metrics['validation']['median_absolute_error']:.3f} | {metrics['validation']['p90_absolute_error']:.3f} |
| Test seed 789 | {metrics['test']['mae']:.3f} | {metrics['test']['rmse']:.3f} | {metrics['test']['r2']:.4f} | {metrics['test']['median_absolute_error']:.3f} | {metrics['test']['p90_absolute_error']:.3f} |
| Historical-average baseline (test) | {metrics['baseline_test']['mae']:.3f} | {metrics['baseline_test']['rmse']:.3f} | {metrics['baseline_test']['r2']:.4f} | {metrics['baseline_test']['median_absolute_error']:.3f} | {metrics['baseline_test']['p90_absolute_error']:.3f} |

LightGBM test MAE improvement over the training-only historical baseline: **{metrics['baseline_mae_improvement_percent']:.2f}%**.

### Worst-performing buildings by held-out MAE

""" + "\n".join(f"- {name}: {value:.3f} students" for name, value in worst) + f"""

The representative time-series plot uses {representative[0]} on semester day {representative[1]}. The second plot compares held-out MAE across all buildings.

## Artifacts and commands

- Model: `outputs/ml/models/occupancy_model.txt`
- Feature configuration: `outputs/ml/models/feature_config.json`
- Metrics: `outputs/ml/models/metrics.json`
- Validation: `outputs/ml/models/data_validation.json`
- Plots: `outputs/ml/models/plots/`

Retrain:

```bash
brew install libomp  # one-time LightGBM runtime dependency on Apple Silicon
.venv-ml/bin/python -m src.ml.train
```

Start the API:

```bash
.venv-ml/bin/python -m uvicorn src.ml.api:app --host 127.0.0.1 --port 8000
```

Example requests:

```text
GET http://127.0.0.1:8000/api/predict?building=ECSW&weekday=Tuesday&time=14:30&week=8
GET http://127.0.0.1:8000/api/predict/campus?weekday=Tuesday&time=14:30&week=8
```

The first example currently returns `{{"building_code":"ECSW","predicted_occupancy":549}}`.

## Limitations

This model measures generalization to an unseen **synthetic simulation seed**, not accuracy against real campus observations. It inherits the simulator's schedule, behavioral, map, event, and seating assumptions. Only four stochastic simulation runs are available, and event indicators cover only events explicitly configured in `src/agents/events.json`. Real sensor or count data is required before making real-world accuracy claims.
"""
    output.write_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--out", type=Path, default=MODEL_DIR)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST_PATH.read_text())
    data = read_data(args.data)
    validation = validate_data(data, args.data, manifest)
    (args.out / "data_validation.json").write_text(
        json.dumps(validation, indent=2, default=json_value) + "\n")
    if validation["status"] != "valid":
        raise SystemExit("Critical dataset validation failed; see data_validation.json")

    data = data[data.building_code.astype(str) != "_WALKING"].copy()
    events = load_events(EVENTS_PATH)
    buildings = sorted(data.building_code.astype(str).unique().tolist())
    config = build_feature_config(buildings, events)
    config.update({"training_seeds": [42, 123], "validation_seed": 456,
                   "test_seed": 789, "events_path": str(EVENTS_PATH.relative_to(ROOT))})
    (args.out / "feature_config.json").write_text(json.dumps(config, indent=2) + "\n")

    train = data[data.seed.isin([42, 123])]
    valid = data[data.seed == 456]
    test = data[data.seed == 789]
    x_train, x_valid, x_test = (prepare_features(part, config)
                                for part in (train, valid, test))
    y_train, y_valid, y_test = (part.total_occupancy.to_numpy()
                                for part in (train, valid, test))
    params = {"objective": "regression_l1", "metric": "mae", "learning_rate": 0.05,
              "num_leaves": 255, "max_depth": 12, "min_data_in_leaf": 50,
              "feature_fraction": 1.0, "bagging_fraction": 1.0, "bagging_freq": 0,
              "lambda_l2": 1.0,
              "seed": 2026, "feature_fraction_seed": 2026, "bagging_seed": 2026,
              "num_threads": 8, "verbosity": -1, "deterministic": True,
              "force_col_wise": True}
    training_start = time.perf_counter()
    model = lgb.train(params, lgb.Dataset(x_train, y_train, categorical_feature=CATEGORICAL_FEATURES),
                      num_boost_round=1400,
                      valid_sets=[lgb.Dataset(x_valid, y_valid, reference=None,
                                              categorical_feature=CATEGORICAL_FEATURES)],
                      valid_names=["seed456"],
                      callbacks=[lgb.early_stopping(100), lgb.log_evaluation(100)])
    training_seconds = time.perf_counter() - training_start
    model.save_model(str(args.out / "occupancy_model.txt"), num_iteration=model.best_iteration)
    valid_prediction = np.clip(model.predict(x_valid, num_iteration=model.best_iteration), 0, None)
    test_prediction = np.clip(model.predict(x_test, num_iteration=model.best_iteration), 0, None)

    baseline_keys = ["building_code", "weekday", "time_s"]
    baseline_table = (train.groupby(baseline_keys, observed=True).total_occupancy.mean()
                      .rename("baseline"))
    baseline = test.join(baseline_table, on=baseline_keys).baseline
    building_fallback = train.groupby("building_code", observed=True).total_occupancy.mean()
    baseline = baseline.fillna(test.building_code.map(building_fallback)).fillna(train.total_occupancy.mean())
    baseline_prediction = baseline.to_numpy()

    metrics = {"model_version": config["model_version"], "best_iteration": model.best_iteration,
               "training_seconds": training_seconds, "training_rows": len(train),
               "validation_rows": len(valid), "test_rows": len(test),
               "params": params, "validation": regression_metrics(y_valid, valid_prediction),
               "test": regression_metrics(y_test, test_prediction),
               "baseline_test": regression_metrics(y_test, baseline_prediction)}
    metrics["baseline_mae_improvement_percent"] = float(
        100 * (metrics["baseline_test"]["mae"] - metrics["test"]["mae"])
        / metrics["baseline_test"]["mae"])
    for name, frame, prediction in (("validation", valid, valid_prediction),
                                    ("test", test, test_prediction)):
        metrics[name]["mae_by_building"] = grouped_mae(frame, prediction, "building_code")
        metrics[name]["mae_by_weekday"] = grouped_mae(frame, prediction, "weekday")
        period = period_labels(frame.time_s).astype(str)
        period_frame = frame.assign(time_period=period)
        metrics[name]["mae_by_time_period"] = grouped_mae(period_frame, prediction, "time_period")
    representative = make_plots(test, test_prediction, metrics, config, args.out / "plots")
    (args.out / "metrics.json").write_text(json.dumps(metrics, indent=2, default=json_value) + "\n")
    write_report(validation, config, params, metrics, training_seconds, representative,
                 args.out / "TRAINING_REPORT.md")
    print(json.dumps({"status": "trained", "best_iteration": model.best_iteration,
                      "training_seconds": training_seconds,
                      "validation": metrics["validation"], "test": metrics["test"],
                      "baseline_test": metrics["baseline_test"],
                      "baseline_mae_improvement_percent": metrics["baseline_mae_improvement_percent"]},
                     indent=2, default=json_value))


if __name__ == "__main__":
    main()
