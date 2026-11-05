"""Run fictional daily student schedules: python -m src.simulation.run."""
import argparse
import csv
import json
from pathlib import Path
import pickle
import sys
from time import perf_counter

from src.simulation.terminal_report import print_journey_report

from src.models.campus import CampusModel
from src.simulation.schedule import ClassSession, finite_number, parse_time, validate_schedule

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GRAPH = ROOT / 'src' / 'mapping' / 'utd-graph' / 'utd_simulation_graph.pkl'
DEFAULT_SCHEDULE = ROOT / 'data' / 'demo_student_schedules.json'
EVENT_FIELDS = ('time_minute', 'clock_time', 'student_id', 'event', 'location',
                'destination', 'course', 'lateness_minutes')


def load_students(path: Path) -> list[dict]:
    """Parse and validate the entire JSON input before any agents are registered."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid schedule JSON in {path}: {exc}') from exc
    if not isinstance(data, dict) or not isinstance(data.get('students'), list):
        raise ValueError('Schedule JSON must contain a students array')
    students, ids = [], set()
    for index, record in enumerate(data['students']):
        if not isinstance(record, dict):
            raise ValueError(f'Student record {index} must be an object')
        student_id = record.get('student_id')
        try:
            if not isinstance(student_id, str) or not student_id.strip():
                raise ValueError('student_id must be a nonempty string')
            if student_id in ids:
                raise ValueError(f'Duplicate student_id {student_id!r}')
            initial = record.get('initial_location')
            if not isinstance(initial, str) or not initial.strip():
                raise ValueError('initial_location must be a nonempty node code')
            if not isinstance(record.get('classes'), list):
                raise ValueError('classes must be an array')
            sessions = []
            for entry in record['classes']:
                if not isinstance(entry, dict):
                    raise ValueError('Each class must be an object')
                missing = {'destination', 'start', 'end'} - set(entry)
                if missing:
                    raise ValueError(f'Class missing fields: {", ".join(sorted(missing))}')
                sessions.append(ClassSession(entry['destination'], parse_time(entry['start']),
                                             parse_time(entry['end']), entry.get('course', '')))
            speed = record.get('walking_speed_m_s')
            if 'walking_speed_m_s' in record:
                speed = finite_number(speed, 'walking_speed_m_s', strictly_positive=True)
            students.append(dict(student_id=student_id, initial_location=initial,
                                 schedule=validate_schedule(sessions), walking_speed_m_s=speed))
            ids.add(student_id)
        except ValueError as exc:
            raise ValueError(f'Student {student_id!r} (record {index}): {exc}') from exc
    return students


def clock_time(minute: float) -> str:
    # Numeric time_minute in CSV preserves full precision for analysis.
    milliseconds = round(minute * 60000)
    hours, milliseconds = divmod(milliseconds, 3600000)
    minutes, milliseconds = divmod(milliseconds, 60000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f'{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}'


def write_events(path: Path, events: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=EVENT_FIELDS)
        writer.writeheader()
        for event in sorted(events, key=lambda e: e['time_minute']):
            writer.writerow(dict(event, clock_time=clock_time(event['time_minute'])))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schedule', type=Path, default=DEFAULT_SCHEDULE)
    parser.add_argument('--graph', type=Path, default=DEFAULT_GRAPH,
                        help='Trusted local NetworkX pickle; default is the enriched src graph')
    parser.add_argument('--start', type=parse_time, default=480, metavar='HH:MM')
    parser.add_argument('--end', type=parse_time, default=780, metavar='HH:MM')
    parser.add_argument('--output', type=Path, default=Path('simulation_output/events.csv'))
    parser.add_argument('--step-minutes', type=float, default=1)
    parser.add_argument('--speed-m-s', type=float, default=1.4)
    parser.add_argument('--arrival-buffer-minutes', type=float, default=0)
    parser.add_argument('--fallback-distance-m', type=float, default=10)
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(argv)
    started = perf_counter()
    try:
        if args.end < args.start:
            raise ValueError('End time must not precede start time')
        records = load_students(args.schedule)
        # Graph is the repository's own trusted local artifact, not remote input.
        with args.graph.open('rb') as stream:
            graph = pickle.load(stream)
        model = CampusModel(graph, start_minute=args.start, step_minutes=args.step_minutes,
                            walking_speed_m_s=args.speed_m_s,
                            arrival_buffer_minutes=args.arrival_buffer_minutes,
                            fallback_distance_m=args.fallback_distance_m, seed=args.seed)
        # Check all graph-dependent inputs before populating a partial model.
        for record in records:
            model.prepare_student(**record)
        for record in records:
            model.add_student(**record)
        simulation_started = perf_counter()
        model.run_until(args.end)
        simulation_seconds = perf_counter() - simulation_started
        write_events(args.output, model.events)
    except (ValueError, OSError, pickle.UnpicklingError, EOFError, ImportError) as exc:
        print(f'Simulation error: {exc}', file=sys.stderr)
        return 1
    print(f'Simulated {clock_time(args.start)} to {clock_time(model.current_minute)} '
          f'({model.current_minute - args.start:g} minutes)')
    print(f'Execution time: {perf_counter() - started:.3f} seconds (simulation loop: {simulation_seconds:.3f} seconds)')
    print_journey_report(records, model.events, model.current_minute, clock_time)
    print(f'\nStudents: {len(model.agents)}')
    print(f'Completed classes: {model.completed_classes}')
    print(f'Missed classes: {model.missed_classes}')
    print(f'Late arrivals: {model.late_arrivals}')
    print(f'Walked distance: {model.total_walked_distance_m:.3f} m')
    print(f'Fallback edges: {model.fallback_edge_count}')
    print(f'Events: {len(model.events)} -> {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
