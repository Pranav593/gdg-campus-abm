"""Behavior tests for scheduled, distance-based student movement."""
import importlib
import importlib.util
import unittest
import networkx as nx
import csv
import io
import json
import os
from pathlib import Path
import pickle
import tempfile
from contextlib import redirect_stdout, redirect_stderr


def tiny_graph(edges=(('A', 'B', 84), ('B', 'A', 84))):
    graph = nx.MultiDiGraph()
    for node in 'ABC':
        graph.add_node(node, type='building', routable=True)
    for a, b, distance in edges:
        graph.add_edge(a, b, length=distance)
    return graph


class RoutingTests(unittest.TestCase):
    def model_class(self):
        self.assertIsNotNone(importlib.util.find_spec('src.models.campus'),
                             'CampusModel routing is not implemented')
        return importlib.import_module('src.models.campus').CampusModel

    def test_parallel_edges_and_canonical_weight_precedence(self):
        graph = tiny_graph((('A', 'B', 100), ('A', 'B', 20)))
        graph['A']['B'][0]['distance_m'] = 5
        model = self.model_class()(graph)
        self.assertEqual(model.route_between('A', 'B'), (('A', 'B'), (5.0,)))
        self.assertNotIn('distance_m', graph['A']['B'][1])
        self.assertEqual(model.route_between('A', 'A'), (('A',), ()))
        self.assertIs(model.route_between('A', 'B'), model.route_between('A', 'B'))

    def test_missing_distances_used_by_route_and_movement(self):
        graph = tiny_graph((('A', 'B', None), ('A', 'C', 6), ('C', 'B', 6)))
        model = self.model_class()(graph)
        self.assertEqual(model.fallback_edge_count, 1)
        self.assertEqual(model.route_between('A', 'B'), (('A', 'B'), (10.0,)))
        self.assertEqual(model.graph['A']['B'][0]['distance_source'], 'simulation_fallback')
        self.assertIsNone(graph['A']['B'][0]['length'])

    def test_invalid_weights_are_not_missing(self):
        model_class = self.model_class()
        for value in (-1, True, float('nan'), float('inf'), 'unknown', '84'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'distance'):
                model_class(tiny_graph((('A', 'B', value),)))
        self.assertEqual(model_class(tiny_graph((('A', 'B', 0),))).route_between('A', 'B')[1], (0,))

    def test_directed_unreachable_and_invalid_destinations(self):
        graph = tiny_graph((('A', 'B', 84),))
        graph.nodes['C']['routable'] = False
        graph.add_node(1, type='path', routable=True)
        model = self.model_class()(graph)
        for node in ('missing', 'C', 1):
            with self.assertRaises(ValueError):
                model.validate_destination(node)
        with self.assertRaisesRegex(ValueError, 'B.*A'):
            model.route_between('B', 'A')

    def test_graph_types_and_configuration_validation(self):
        model_class = self.model_class()
        graph = nx.Graph()
        graph.add_nodes_from([('A', {'type': 'building', 'routable': True}),
                              ('B', {'type': 'building', 'routable': True})])
        graph.add_edge('A', 'B', length=84)
        self.assertEqual(model_class(graph).route_between('B', 'A')[1], (84,))
        for field in ('step_minutes', 'walking_speed_m_s', 'fallback_distance_m'):
            for value in (0, -1, True, float('nan')):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    model_class(graph, **{field: value})
        for field, value in [('arrival_buffer_minutes', -1), ('start_minute', 1441)]:
            with self.assertRaises(ValueError):
                model_class(graph, **{field: value})


class ScheduleTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('src.simulation.schedule'),
                             'Schedule validation is not implemented')
        return importlib.import_module('src.simulation.schedule')

    def test_time_parsing_and_day_boundaries(self):
        parse = self.module().parse_time
        self.assertEqual(parse('08:30'), 510)
        self.assertEqual(parse('24:00'), 1440)
        self.assertEqual(parse(480.25), 480.25)
        for value in ('08:60', '24:01', '8am', '8:0', True, None,
                      float('nan'), float('inf'), -1, 1441):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse(value)

    def test_sessions_reject_invalid_numbers_and_destinations(self):
        session = self.module().ClassSession
        for start, end in [(481, 480), (480, 480), (-1, 10),
                           (1430, 1441), (True, 490), (480, float('nan'))]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                session('ECSW', start, end)
        for destination in ('', None, 42):
            with self.assertRaises(ValueError):
                session(destination, 480, 490)

    def test_schedule_sorted_frozen_and_back_to_back(self):
        mod = self.module()
        a = mod.ClassSession('A', 480, 490, 'first')
        b = mod.ClassSession('B', 490, 500, 'second')
        self.assertEqual(mod.validate_schedule([b, a]), (a, b))
        self.assertEqual(mod.validate_schedule([]), ())
        with self.assertRaises(AttributeError):
            a.start_minute = 0

    def test_overlapping_or_malformed_schedule_rejected(self):
        mod = self.module()
        with self.assertRaisesRegex(ValueError, 'overlap'):
            mod.validate_schedule([mod.ClassSession('A', 480, 500),
                                   mod.ClassSession('B', 490, 510)])
        for entries in ([{}], None, 'not a schedule'):
            with self.assertRaises(ValueError):
                mod.validate_schedule(entries)


class StudentFlowTests(unittest.TestCase):
    def setup_model(self, edges=None, **kwargs):
        from src.models.campus import CampusModel
        self.assertTrue(hasattr(CampusModel, 'add_student'), 'Student execution is not implemented')
        return CampusModel(tiny_graph() if edges is None else tiny_graph(edges), **kwargs)

    def add(self, model, sessions=None, **kwargs):
        from src.simulation.schedule import ClassSession
        return model.add_student(student_id=kwargs.pop('student_id', 's1'),
                                 initial_location=kwargs.pop('initial_location', 'A'),
                                 schedule=[ClassSession(*s) for s in (sessions or [])], **kwargs)

    def events(self, model, event):
        return [e for e in model.events if e['event'] == event]

    def test_mesa_registration_and_empty_schedule(self):
        model = self.setup_model()
        student = self.add(model)
        self.assertIn(student, model.agents)
        self.assertNotEqual(student.unique_id, student.student_id)
        model.run_until(481)
        self.assertEqual(student.state, 'finished')
        self.assertEqual(student.current_location, 'A')
        self.assertEqual(len(self.events(model, 'finished')), 1)
        model.run_until(485)
        self.assertEqual(len(self.events(model, 'finished')), 1)

    def test_departure_arrival_and_attendance(self):
        model = self.setup_model()
        student = self.add(model, [('B', 481, 483, 'MATH')])
        model.run_until(484)
        self.assertEqual([(e['event'], e['time_minute']) for e in model.events],
                         [('departure', 480), ('arrival', 481), ('class_start', 481),
                          ('class_end', 483), ('finished', 483)])
        self.assertEqual(student.current_location, 'B')
        self.assertEqual(student.walked_distance_m, 84)
        self.assertEqual(model.completed_classes, 1)
        self.assertEqual(model.current_minute, 484)

    def test_partial_edge_and_truncated_final_interval(self):
        model = self.setup_model([('A', 'B', 168)], step_minutes=5)
        student = self.add(model, [('B', 482, 490)])
        model.run_until(480.5)
        self.assertEqual(student.state, 'walking')
        self.assertEqual(student.current_location, 'A')
        self.assertAlmostEqual(student.remaining_edge_distance_m, 126)
        self.assertEqual(student.current_edge, ('A', 'B'))
        self.assertAlmostEqual(model.total_walked_distance_m, 42)
        self.assertFalse(self.events(model, 'arrival'))
        self.assertEqual(model.current_minute, 480.5)
        model.run_until(482)
        self.assertEqual(self.events(model, 'arrival')[0]['time_minute'], 482)
        self.assertEqual(student.current_location, 'B')

    def test_early_buffer_and_wait_until_start(self):
        model = self.setup_model(start_minute=478, arrival_buffer_minutes=2)
        student = self.add(model, [('B', 481, 483)])
        model.run_until(480)
        self.assertEqual(student.state, 'waiting_for_class')
        self.assertEqual(self.events(model, 'departure')[0]['time_minute'], 478)
        self.assertEqual(self.events(model, 'arrival')[0]['time_minute'], 479)
        self.assertFalse(self.events(model, 'class_start'))
        model.run_until(482)
        self.assertEqual(self.events(model, 'class_start')[0]['time_minute'], 481)

    def test_late_and_exact_end_arrivals(self):
        model = self.setup_model([('A', 'B', 168)])
        self.add(model, [('B', 481, 483)])
        model.run_until(484)
        self.assertEqual(model.late_arrivals, 1)
        self.assertEqual(model.completed_classes, 1)
        self.assertEqual(self.events(model, 'class_start')[0]['lateness_minutes'], 1)
        missed = self.setup_model([('A', 'B', 168)])
        self.add(missed, [('B', 481, 482)])
        missed.run_until(484)
        self.assertEqual(missed.missed_classes, 1)
        self.assertFalse(self.events(missed, 'class_start'))
        self.assertEqual(self.events(missed, 'missed_class')[0]['time_minute'], 482)

    def test_expired_class_finishes_current_edge_then_replans(self):
        edges = [('A', 'X', 252), ('X', 'B', 252), ('B', 'C', 84), ('X', 'C', 84)]
        model = self.setup_model(edges, step_minutes=5)
        student = self.add(model, [('B', 480, 482), ('C', 484, 486)])
        model.run_until(487)
        self.assertEqual(model.missed_classes, 1)
        self.assertEqual(model.completed_classes, 1)
        self.assertEqual(student.current_location, 'C')
        self.assertEqual(student.walked_distance_m, 336)
        self.assertEqual(self.events(model, 'missed_class')[0]['time_minute'], 482)
        self.assertEqual([e['time_minute'] for e in self.events(model, 'departure')], [480, 483])
        self.assertEqual(self.events(model, 'arrival')[0]['time_minute'], 484)

    def test_multiple_edges_zero_lengths_and_same_location_classes(self):
        model = self.setup_model([('A', 'X', 0), ('X', 'B', 42), ('B', 'C', 42)], step_minutes=5)
        self.add(model, [('C', 481, 482), ('C', 482, 483)])
        model.run_until(484)
        self.assertEqual(model.completed_classes, 2)
        self.assertEqual(len(self.events(model, 'departure')), 1)
        self.assertEqual(self.events(model, 'arrival')[0]['time_minute'], 481)
        self.assertEqual([e['time_minute'] for e in self.events(model, 'class_start')], [481, 482])
        self.assertEqual(model.total_walked_distance_m, 84)

    def test_starting_during_class_and_already_expired_classes(self):
        model = self.setup_model(start_minute=482)
        self.add(model, [('A', 479, 481), ('A', 481, 484)])
        model.run_until(485)
        self.assertEqual(model.missed_classes, 1)
        self.assertEqual(model.completed_classes, 1)
        self.assertEqual(model.late_arrivals, 1)
        self.assertEqual(self.events(model, 'class_start')[0]['time_minute'], 482)
        self.assertFalse(self.events(model, 'departure'))

    def test_outcomes_invariant_to_timestep_and_seeded_repetition(self):
        timelines = []
        for tick in (.25, 1, 5):
            model = self.setup_model([('A', 'B', 100), ('B', 'C', 42)], step_minutes=tick, seed=42)
            self.add(model, [('B', 482, 483), ('C', 484, 486)])
            model.run_until(487)
            timelines.append(([(e['event'], round(e['time_minute'], 7)) for e in model.events],
                              round(model.total_walked_distance_m, 7)))
        self.assertEqual(timelines[0], timelines[1])
        self.assertEqual(timelines[1], timelines[2])

    def test_invalid_agents_rejected_before_registration(self):
        from src.simulation.schedule import ClassSession
        model = self.setup_model([('A', 'B', 84)])
        self.add(model)
        for kwargs in [dict(student_id='s1', initial_location='A', schedule=[]),
                       dict(student_id='s2', initial_location='missing', schedule=[]),
                       dict(student_id='s2', initial_location='A', schedule=[], walking_speed_m_s=True),
                       dict(student_id='s2', initial_location='B', schedule=[ClassSession('A', 480, 490)])]:
            with self.assertRaises(ValueError):
                model.add_student(**kwargs)
            self.assertEqual(len(model.agents), 1)

    def test_clock_bounds_and_per_student_speeds(self):
        model = self.setup_model([('A', 'B', 168)])
        self.add(model, [('B', 481, 483)], walking_speed_m_s=2.8)
        model.run_until(484)
        self.assertEqual(self.events(model, 'arrival')[0]['time_minute'], 481)
        for value in (483, 1441, True):
            with self.assertRaises(ValueError):
                model.run_until(value)

    def test_unrepresentably_small_clock_tick_raises_instead_of_stalling(self):
        model = self.setup_model(step_minutes=1e-14)
        with self.assertRaisesRegex(ValueError, 'advance'):
            model.step()

    def test_subprecision_edge_duration_completes_without_stalling(self):
        for speed in (1e16, 1e308):
            with self.subTest(speed=speed):
                model = self.setup_model(walking_speed_m_s=speed)
                student = self.add(model, [('B', 480, 482)])
                # Settle departure at the initial boundary without consuming time.
                student.step()
                self.assertEqual(student.state, 'walking')
                reached_time = student._walk(480, 481)
                self.assertEqual(reached_time, 480)
                self.assertEqual(student.current_location, 'B')
                self.assertEqual(student.walked_distance_m, 84)
                self.assertEqual(student.remaining_edge_distance_m, 0)

    def test_missed_deadlines_during_abandoned_edge_are_timely(self):
        model = self.setup_model([('A', 'B', 840), ('B', 'C', 84)])
        student = self.add(model, [('B', 480, 482), ('C', 483, 485)])
        model.run_until(486)
        self.assertEqual(model.missed_classes, 2)
        self.assertEqual([e['time_minute'] for e in self.events(model, 'missed_class')], [482, 485])
        self.assertEqual(student.current_location, 'A')
        self.assertEqual(student.current_edge, ('A', 'B'))
        self.assertEqual(student.walked_distance_m, 504)
        model.run_until(491)
        self.assertEqual(model.missed_classes, 2)
        self.assertEqual(student.current_location, 'B')


class DemoTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('src.simulation.run'),
                             'Simulation CLI is not implemented')
        return importlib.import_module('src.simulation.run')

    def fixture(self, folder, data=None):
        schedule = folder / 'schedule.json'
        schedule.write_text(json.dumps(data if data is not None else {'students': [
            {'student_id': 's1', 'initial_location': 'A', 'classes': [
                {'destination': 'B', 'start': '08:01', 'end': '08:03', 'course': 'MATH'}]}]}), encoding='utf-8')
        graph = folder / 'graph.pkl'
        graph.write_bytes(pickle.dumps(tiny_graph()))
        return schedule, graph

    def test_json_loading_and_rejecting_bad_records(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            schedule, _ = self.fixture(folder)
            record = mod.load_students(schedule)[0]
            self.assertEqual(record['schedule'][0].start_minute, 481)
            self.assertEqual(record['student_id'], 's1')
            bad_records = [{}, {'students': {}}, {'students': [{}]},
                           {'students': [{'student_id': 's', 'initial_location': 'A', 'classes': [{}]}]},
                           {'students': [{'student_id': 's', 'initial_location': 'A', 'classes': []}]*2},
                           {'students': [{'student_id': 's', 'initial_location': 'A', 'classes': [], 'walking_speed_m_s': True}]}]
            for data in bad_records:
                self.fixture(folder, data)
                with self.subTest(data=data), self.assertRaises(ValueError):
                    mod.load_students(schedule)

    def test_csv_is_sorted_stably_with_subminute_clock(self):
        mod = self.module()
        events = [dict(time_minute=t, event=e, student_id='s') for t, e in
                  [(481, 'arrival'), (480.5, 'departure'), (481, 'class_start')]]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'events.csv'
            mod.write_events(path, events)
            with path.open(encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r['event'] for r in rows], ['departure', 'arrival', 'class_start'])
            self.assertEqual(rows[0]['clock_time'], '08:00:30.000')
            self.assertEqual(float(rows[0]['time_minute']), 480.5)

    def test_cli_runs_and_reports_partial_or_full_walk(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            schedule, graph = self.fixture(folder)
            output = folder / 'events.csv'
            argv = ['--schedule', str(schedule), '--graph', str(graph), '--start', '08:00',
                    '--end', '08:04', '--output', str(output), '--step-minutes', '5']
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(mod.main(argv), 0)
            self.assertIn('Completed classes: 1', stdout.getvalue())
            self.assertIn('Walked distance: 84.000 m', stdout.getvalue())
            self.assertIn('Fallback edges: 0', stdout.getvalue())
            # Fractional minute horizon through the Python API (JSON/model use numbers).
            from src.models.campus import CampusModel
            from src.simulation.schedule import ClassSession
            model = CampusModel(tiny_graph(), step_minutes=5)
            model.add_student(student_id='s', initial_location='A', schedule=[ClassSession('B', 481, 483)])
            model.run_until(480.5)
            mod.write_events(output, model.events)
            self.assertNotIn('arrival', output.read_text())
            self.assertEqual(model.total_walked_distance_m, 42)

    def test_cli_errors_without_writing_output(self):
        mod = self.module()
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            schedule, graph = self.fixture(folder, {'students': [
                {'student_id': 's1', 'initial_location': 'B', 'classes': [
                    {'destination': 'C', 'start': '08:01', 'end': '08:03'}]}]})
            output = folder / 'events.csv'
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertNotEqual(mod.main(['--schedule', str(schedule), '--graph', str(graph),
                                             '--output', str(output)]), 0)
            self.assertIn('s1', stderr.getvalue())
            self.assertIn('No walking route', stderr.getvalue())
            self.assertFalse(output.exists())

    def test_real_graph_default_from_other_directory_and_all_origins(self):
        mod = self.module()
        from src.models.campus import CampusModel
        from src.simulation.schedule import ClassSession
        model = CampusModel(pickle.loads(mod.DEFAULT_GRAPH.read_bytes()), start_minute=480)
        self.assertEqual(model.fallback_edge_count, 0)
        for origin in ('Housing', 'PS1', 'PS3', 'PS4'):
            nodes, distances = model.route_between(origin, 'ECSW')
            expected = nx.shortest_path_length(model.graph, origin, 'ECSW', weight='distance_m')
            self.assertAlmostEqual(sum(distances), expected)
            self.assertEqual((nodes[0], nodes[-1]), (origin, 'ECSW'))
        model.add_student(student_id='real', initial_location='PS4',
                          schedule=[ClassSession('ECSW', 500, 510)])
        model.run_until(511)
        self.assertEqual(model.completed_classes, 1)
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                with redirect_stdout(io.StringIO()):
                    result = mod.main(['--output', str(Path(directory) / 'events.csv')])
                self.assertEqual(result, 0)
            finally:
                os.chdir(previous)


if __name__ == '__main__':
    unittest.main()
