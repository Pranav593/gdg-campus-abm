"""Reloadable prediction interface for a trained campus occupancy model."""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .features import parse_time, prepare_features, semester_day

DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[2] / "outputs" / "ml" / "models"


class OccupancyPredictor:
    def __init__(self, model_dir: str | Path = DEFAULT_MODEL_DIR):
        model_dir = Path(model_dir)
        model_path = model_dir / "occupancy_model.txt"
        config_path = model_dir / "feature_config.json"
        if not model_path.exists() or not config_path.exists():
            raise FileNotFoundError(f"Model artifacts are missing from {model_dir}")
        self.config = json.loads(config_path.read_text())
        self.model = lgb.Booster(model_file=str(model_path))

    def _frame(self, buildings: list[str], weekday: str, time: str,
               semester_week: int) -> pd.DataFrame:
        unknown = sorted(set(buildings) - set(self.config["prediction_buildings"]))
        if unknown:
            raise ValueError(f"unknown building code: {unknown[0]}")
        day = semester_day(weekday, semester_week, self.config)
        time_s = parse_time(time)
        raw = pd.DataFrame({"building_code": buildings, "weekday": weekday,
                            "time_s": time_s, "semester_day": day})
        return prepare_features(raw, self.config)

    def predict_occupancy(self, building_code: str = "ECSW", weekday: str = "Tuesday",
                          time: str = "14:30", semester_week: int = 8) -> dict:
        features = self._frame([building_code], weekday, time, semester_week)
        value = float(np.clip(self.model.predict(features)[0], 0, None))
        return {"building_code": building_code, "predicted_occupancy": int(round(value))}

    def predict_campus(self, weekday: str = "Tuesday", time: str = "14:30",
                       semester_week: int = 8) -> dict:
        buildings = list(self.config["prediction_buildings"])
        features = self._frame(buildings, weekday, time, semester_week)
        values = np.clip(self.model.predict(features), 0, None)
        return {"weekday": weekday, "time": time, "semester_week": semester_week,
                "predictions": [{"building_code": code,
                                 "predicted_occupancy": int(round(value))}
                                for code, value in zip(buildings, values)]}


_default_predictor: OccupancyPredictor | None = None


def _predictor() -> OccupancyPredictor:
    global _default_predictor
    if _default_predictor is None:
        _default_predictor = OccupancyPredictor()
    return _default_predictor


def predict_occupancy(building_code="ECSW", weekday="Tuesday", time="14:30",
                      semester_week=8):
    return _predictor().predict_occupancy(building_code, weekday, time, semester_week)


def predict_campus(weekday="Tuesday", time="14:30", semester_week=8):
    return _predictor().predict_campus(weekday, time, semester_week)
