"""Clean and combine the raw Spring 2026 CourseBook exports.

By default this script reads ``data/coursebook/raw/*.json`` and writes a JSON
array to ``data/coursebook/processed/spring_2026_courses.json``.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "coursebook" / "raw"
DEFAULT_OUTPUT_PATH = (
    REPO_ROOT / "data" / "coursebook" / "processed" / "spring_2026_courses.json"
)

SCHEDULE_SEPARATOR = re.compile(r"\n\s*\n")
TIME_RANGE = re.compile(
    r"^(?P<start>\d{1,2}:\d{2}\s*[AP]M)\s*-\s*"
    r"(?P<end>\d{1,2}:\d{2}\s*[AP]M)$",
    re.IGNORECASE,
)
LOCATION = re.compile(
    r"^(?P<building>[^_\s]+)[_\s]+(?P<floor>[^.\s]+)\.(?P<room>.+)$"
)
BUILDING_ALIASES = {
    # CourseBook uses these older/different codes for graph destinations.
    "APC1": "APC",
    "SOM": "JSOM",
}


def clean_string(value: Any, *, uppercase: bool = False) -> str | None:
    """Return a trimmed string while retaining missing values as ``None``."""
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned.upper() if uppercase else cleaned


def integer_when_possible(value: Any) -> Any:
    """Convert integer-like values without discarding unexpected source data."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)

    cleaned = value.strip() if isinstance(value, str) else value
    try:
        return int(cleaned)
    except (TypeError, ValueError):
        return cleaned


def parse_location(location: Any) -> dict[str, str | int | None]:
    """Parse a CourseBook location into building, numeric floor, and room.

    In addition to the usual ``SCI_2.225`` form, CourseBook currently contains
    a small number of space-separated values such as ``VCB 1.201``. Bare
    values such as ``ONLINE`` and ``SIFRA`` do not contain enough structured
    location information, so their three location fields remain null.
    """
    empty = {"building": None, "floor": None, "room": None}
    value = clean_string(location)
    if not value:
        return empty

    match = LOCATION.fullmatch(value)
    if match is None:
        return empty

    floor_text = match.group("floor")
    floor = int(floor_text) if floor_text.isdigit() else None
    building = match.group("building").upper()
    return {
        "building": BUILDING_ALIASES.get(building, building),
        "floor": floor,
        "room": match.group("room").strip() or None,
    }


def parse_time(value: str) -> str | None:
    """Convert a 12-hour CourseBook time to 24-hour ``HH:MM`` format."""
    try:
        return datetime.strptime(value.strip().upper(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        return None


def parse_schedule_blocks(schedule: Any) -> list[dict[str, Any]]:
    """Convert ``schedule_combined`` into one meeting per schedule block."""
    if not isinstance(schedule, str) or not schedule.strip():
        return []

    meetings: list[dict[str, Any]] = []
    for block in SCHEDULE_SEPARATOR.split(schedule.strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue

        day = lines[0] or None
        time_match = TIME_RANGE.fullmatch(lines[1]) if len(lines) >= 2 else None
        location = parse_location(lines[2] if len(lines) >= 3 else None)
        meetings.append(
            {
                "day": day,
                "start_time": parse_time(time_match.group("start")) if time_match else None,
                "end_time": parse_time(time_match.group("end")) if time_match else None,
                **location,
            }
        )

    return meetings


def clean_section(section: dict[str, Any]) -> dict[str, Any]:
    """Normalize one raw CourseBook section to the output schema."""
    return {
        "section_id": clean_string(section.get("section_address")),
        "prefix": clean_string(section.get("course_prefix"), uppercase=True),
        "course_number": clean_string(section.get("course_number")),
        "section": clean_string(section.get("section")),
        "class_number": clean_string(section.get("class_number")),
        "title": clean_string(section.get("title")),
        "enrollment": integer_when_possible(section.get("enrolled_current")),
        "capacity": integer_when_possible(section.get("enrolled_max")),
        "activity_type": clean_string(section.get("activity_type")),
        "school": clean_string(section.get("school")),
        "department": clean_string(section.get("dept")),
        "term": clean_string(section.get("term")),
        "meetings": parse_schedule_blocks(section.get("schedule_combined")),
    }


def load_raw_files(raw_dir: Path) -> tuple[list[dict[str, Any]], int]:
    """Load and clean every JSON export in ``raw_dir`` in filename order."""
    paths = sorted(raw_dir.glob("*.json"))
    if not paths:
        raise FileNotFoundError(f"No JSON files found in {raw_dir}")

    sections: list[dict[str, Any]] = []
    for path in paths:
        try:
            report = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Could not load {path}: {error}") from error

        report_data = report.get("report_data") if isinstance(report, dict) else None
        if not isinstance(report_data, list):
            raise ValueError(f"{path} does not contain a report_data array")

        for index, section in enumerate(report_data):
            if not isinstance(section, dict):
                raise ValueError(
                    f"{path} report_data[{index}] is not a course section object"
                )
            sections.append(clean_section(section))

    return sections, len(paths)


def write_courses(courses: list[dict[str, Any]], output_path: Path) -> None:
    """Write the normalized course list as formatted UTF-8 JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(courses, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    courses, file_count = load_raw_files(args.raw_dir)
    write_courses(courses, args.output)
    print(f"Files processed: {file_count}")
    print(f"Sections processed: {len(courses)}")
    print(f"Output: {args.output.resolve()}")


if __name__ == "__main__":
    main()
