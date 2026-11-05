"""Mesa campus model with canonical meter weights and cached directed routes."""
import mesa
import networkx as nx

from src.simulation.schedule import finite_number, parse_time, validate_schedule


class CampusModel(mesa.Model):
    def __init__(self, graph: nx.Graph, *, start_minute: float = 480,
                 step_minutes: float = 1, walking_speed_m_s: float = 1.4,
                 arrival_buffer_minutes: float = 0, fallback_distance_m: float = 10,
                 seed: int | None = None):
        super().__init__(seed=seed)
        if not isinstance(graph, nx.Graph):
            raise ValueError('Campus graph must be a NetworkX graph')
        self.current_minute = parse_time(start_minute)
        self.start_minute = self.current_minute
        self.interval_end_minute = self.current_minute
        self.step_minutes = finite_number(step_minutes, 'step_minutes', strictly_positive=True)
        self.walking_speed_m_s = finite_number(walking_speed_m_s, 'walking_speed_m_s', strictly_positive=True)
        self.arrival_buffer_minutes = finite_number(arrival_buffer_minutes, 'arrival_buffer_minutes')
        self.fallback_distance_m = finite_number(fallback_distance_m, 'fallback_distance_m', strictly_positive=True)
        self.graph = graph.copy()
        self.fallback_edge_count = 0
        self.events = []
        self.completed_classes = 0
        self.missed_classes = 0
        self.late_arrivals = 0
        self._routes = {}
        self._student_ids = set()
        self._run_end = 1440.0
        edges = (self.graph.edges(keys=True, data=True) if self.graph.is_multigraph()
                 else ((a, b, None, d) for a, b, d in self.graph.edges(data=True)))
        for a, b, key, data in edges:
            value = data.get('distance_m')
            if value is None:
                value = data.get('length')
            if value is None:
                value = self.fallback_distance_m
                data['distance_source'] = 'simulation_fallback'
                self.fallback_edge_count += 1
            try:
                distance = finite_number(value, 'edge distance')
            except ValueError as exc:
                raise ValueError(f'Invalid distance on edge {(a, b, key)}: {value!r}') from exc
            data['distance_m'] = distance

    @property
    def total_walked_distance_m(self) -> float:
        return sum(agent.walked_distance_m for agent in self.agents)

    def validate_destination(self, node: str) -> None:
        if node not in self.graph:
            raise ValueError(f'Unknown destination {node!r}')
        data = self.graph.nodes[node]
        if data.get('type') == 'path' or data.get('routable') is not True:
            raise ValueError(f'Destination {node!r} is not an active routable destination')

    def route_between(self, source: str, target: str) -> tuple[tuple[object, ...], tuple[float, ...]]:
        """Nodes and selected parallel-edge distances, both using distance_m."""
        pair = (source, target)
        if pair not in self._routes:
            try:
                nodes = tuple(nx.shortest_path(self.graph, source, target, weight='distance_m'))
            except (nx.NodeNotFound, nx.NetworkXNoPath) as exc:
                raise ValueError(f'No walking route from {source!r} to {target!r}') from exc
            distances = []
            for a, b in zip(nodes, nodes[1:]):
                data = self.graph[a][b]
                distances.append(min(e['distance_m'] for e in data.values())
                                 if self.graph.is_multigraph() else data['distance_m'])
            self._routes[pair] = (nodes, tuple(distances))
        return self._routes[pair]

    def emit_event(self, student_id: str, time_minute: float, event: str,
                   location: object, destination: str | None = None,
                   course: str = '', lateness_minutes: float = 0) -> None:
        self.events.append(dict(time_minute=time_minute, student_id=student_id,
                                event=event, location=location, destination=destination,
                                course=course, lateness_minutes=lateness_minutes))

    def prepare_student(self, student_id, initial_location, schedule, walking_speed_m_s=None):
        """Validate everything that could fail before Mesa registers an agent."""
        if not isinstance(student_id, str) or not student_id.strip():
            raise ValueError('student_id must be a nonempty string')
        if student_id in self._student_ids:
            raise ValueError(f'Duplicate student_id {student_id!r}')
        try:
            ordered = validate_schedule(schedule)
            speed = (self.walking_speed_m_s if walking_speed_m_s is None else
                     finite_number(walking_speed_m_s, 'student walking_speed_m_s', strictly_positive=True))
            self.validate_destination(initial_location)
            previous = initial_location
            for session in ordered:
                self.validate_destination(session.destination)
                self.route_between(previous, session.destination)
                previous = session.destination
        except (ValueError, TypeError) as exc:
            raise ValueError(f'Student {student_id!r}: {exc}') from exc
        return ordered, speed

    def add_student(self, *, student_id, initial_location, schedule, walking_speed_m_s=None):
        from src.agents.student import StudentAgent
        return StudentAgent(self, schedule, student_id=student_id,
                            initial_location=initial_location, walking_speed_m_s=walking_speed_m_s)

    def step(self) -> None:
        """Process one interval; Mesa wraps this method to maintain its own tick."""
        end = min(self.current_minute + self.step_minutes, self._run_end, 1440.0)
        if end <= self.current_minute:
            if self.current_minute < min(self._run_end, 1440.0):
                raise ValueError('step_minutes is too small to advance the floating-point simulation clock')
            return
        self.interval_end_minute = end
        self.agents.do('step')
        self.current_minute = end

    def run_until(self, end_minute: float) -> None:
        end = parse_time(end_minute)
        if end < self.current_minute:
            raise ValueError('End time must not precede the current simulation clock')
        self._run_end = end
        try:
            while self.current_minute < end:
                self.step()
        finally:
            self._run_end = 1440.0
