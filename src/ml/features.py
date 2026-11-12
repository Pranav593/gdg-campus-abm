"""Shared, leakage-free feature preparation for training and inference."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
FEATURE_NAMES = [
    "building_id", "weekday_id", "time_s", "semester_day", "semester_week",
    "is_exam_period", "is_campus_event",
]
CATEGORICAL_FEATURES = ["building_id", "weekday_id"]


def load_events(path: str | Path) -> list[dict]:
    with Path(path).open() as handle:
        return json.load(handle).get("events", [])


def event_flags(days: pd.Series, times: pd.Series, buildings: pd.Series,
                events: list[dict]) -> tuple[pd.Series, pd.Series]:
    exam = pd.Series(False, index=days.index)
    campus = pd.Series(False, index=days.index)
    for event in events:
        if event.get("type") == "exam_period":
            exam |= days.between(int(event["start_day"]), int(event["end_day"]))
        elif event.get("type") == "campus_event":
            start_h, start_m = map(int, event["start_time"].split(":"))
            end_h, end_m = map(int, event["end_time"].split(":"))
            start_s = start_h * 3600 + start_m * 60
            end_s = end_h * 3600 + end_m * 60
            campus |= ((days == int(event["day"])) & times.between(start_s, end_s - 1)
                       & (buildings == event["building"]))
    return exam.astype("int8"), campus.astype("int8")


def build_feature_config(buildings: list[str], events: list[dict]) -> dict:
    prediction_buildings = [code for code in sorted(buildings)
                            if not (code.startswith("Lot ") or code.startswith("Res Lot")
                                    or code.endswith(" Lot"))]
    return {
        "model_version": "occupancy-lightgbm-v1",
        "feature_names": FEATURE_NAMES,
        "categorical_features": CATEGORICAL_FEATURES,
        "building_mapping": {code: i for i, code in enumerate(sorted(buildings))},
        "prediction_buildings": prediction_buildings,
        "weekday_mapping": {name: i for i, name in enumerate(WEEKDAYS)},
        "semester_week_formula": "semester_day // 5 + 1",
        "request_day_formula": "(semester_week - 1) * 5 + weekday_index",
        "semester_weeks": 15,
        "events": events,
        "target": "total_occupancy",
        "excluded_destination": "_WALKING",
    }


def prepare_features(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    result = pd.DataFrame(index=frame.index)
    result["building_id"] = frame["building_code"].map(config["building_mapping"])
    result["weekday_id"] = frame["weekday"].map(config["weekday_mapping"])
    if result[["building_id", "weekday_id"]].isna().any().any():
        raise ValueError("Unknown building or weekday in feature input")
    result["building_id"] = result["building_id"].astype("int16")
    result["weekday_id"] = result["weekday_id"].astype("int8")
    result["time_s"] = frame["time_s"].astype("int32")
    result["semester_day"] = frame["semester_day"].astype("int16")
    result["semester_week"] = (result["semester_day"] // 5 + 1).astype("int8")
    exam, campus = event_flags(result["semester_day"], result["time_s"],
                               frame["building_code"], config["events"])
    result["is_exam_period"] = exam
    result["is_campus_event"] = campus
    return result[FEATURE_NAMES]


def parse_time(value: str) -> int:
    try:
        hour_text, minute_text = value.split(":")
        hour, minute = int(hour_text), int(minute_text)
    except (ValueError, AttributeError) as exc:
        raise ValueError("time must use HH:MM format") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time must be a valid 24-hour HH:MM value")
    return hour * 3600 + minute * 60


def semester_day(weekday: str, semester_week: int, config: dict) -> int:
    if weekday not in config["weekday_mapping"]:
        raise ValueError(f"weekday must be one of {list(config['weekday_mapping'])}")
    if not 1 <= semester_week <= int(config["semester_weeks"]):
        raise ValueError("semester_week must be between 1 and 15")
    return (semester_week - 1) * 5 + int(config["weekday_mapping"][weekday])
