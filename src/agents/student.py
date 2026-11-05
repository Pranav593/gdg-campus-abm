"""A Mesa student who consumes time along routes and attends scheduled classes."""
import mesa

TIME_EPS = 1e-9
DISTANCE_EPS = 1e-7


class StudentAgent(mesa.Agent):
    def __init__(self, model, schedule, *, student_id: str, initial_location: str,
                 walking_speed_m_s: float | None = None):
        ordered, speed = model.prepare_student(student_id, initial_location, schedule, walking_speed_m_s)
        super().__init__(model)
        model._student_ids.add(student_id)
        self.student_id = student_id
        self.schedule = ordered
        self.walking_speed_m_s = speed
        self.current_location = initial_location
        self.state = 'idle'
        self.target_class = None
        self.route = ()
        self.current_edge = None
        self.remaining_edge_distance_m = 0.0
        self.walked_distance_m = 0.0
        self._index = 0
        self._distances = ()
        self._edge_index = 0
        self._abandon_route = False

    def _emit(self, event, when, session=None, lateness=0):
        session = session or self.target_class
        self.model.emit_event(self.student_id, when, event, self.current_location,
                              session.destination if session else None,
                              session.course if session else '', lateness)

    def _miss(self, when):
        self._emit('missed_class', when, self.schedule[self._index])
        self.model.missed_classes += 1
        self._index += 1
        self.target_class = None

    def _set_edge(self):
        self.current_edge = (self.route[self._edge_index], self.route[self._edge_index + 1])
        self.remaining_edge_distance_m = self._distances[self._edge_index]

    def _walk(self, now, end):
        """Advance to the next edge/class/interval boundary, never teleporting."""
        # Divide before scaling to avoid overflowing speed * 60. A duration
        # smaller than the clock's precision still completes the entire edge.
        edge_end = now + self.remaining_edge_distance_m / self.walking_speed_m_s / 60
        stop = min(end, edge_end)
        deadline = (self.schedule[self._index].end_minute
                    if self._index < len(self.schedule) else float('inf'))
        stop = min(stop, max(now, deadline))
        moved = (self.remaining_edge_distance_m if stop >= edge_end else
                 min(self.remaining_edge_distance_m,
                     max(0.0, stop - now) * self.walking_speed_m_s * 60))
        self.remaining_edge_distance_m -= moved
        self.walked_distance_m += moved
        now = stop
        # Deadlines still matter while completing an abandoned edge, even
        # though the next target is not selected until reaching a graph node.
        if self._index < len(self.schedule) and now >= deadline - TIME_EPS:
            self._miss(now)
            self._abandon_route = True
        if self.remaining_edge_distance_m <= DISTANCE_EPS:
            self.current_location = self.current_edge[1]
            self.current_edge = None
            self.remaining_edge_distance_m = 0.0
            self._edge_index += 1
            if self._abandon_route:
                self._abandon_route = False
                self.state = 'idle'
            elif self._edge_index == len(self._distances):
                self._emit('arrival', now)
                self.state = 'waiting_for_class'
            else:
                self._set_edge()
        return now

    def step(self) -> None:
        now, end = self.model.current_minute, self.model.interval_end_minute
        # Instantaneous state changes at interval boundaries are settled too;
        # positive travel/wait time is consumed only inside the interval.
        while True:
            if self.state == 'finished':
                return
            if self.state == 'walking':
                if now >= end and self.remaining_edge_distance_m > DISTANCE_EPS:
                    return
                now = self._walk(now, end)
                continue
            if self.state == 'idle':
                while self._index < len(self.schedule) and self.schedule[self._index].end_minute <= now + TIME_EPS:
                    self._miss(now)
                if self._index == len(self.schedule):
                    self.state = 'finished'
                    self._emit('finished', now)
                    return
                self.target_class = self.schedule[self._index]
                if self.current_location == self.target_class.destination:
                    self.state = 'waiting_for_class'
                    continue
                route, distances = self.model.route_between(self.current_location, self.target_class.destination)
                travel_minutes = sum(distances) / self.walking_speed_m_s / 60
                departure = self.target_class.start_minute - travel_minutes - self.model.arrival_buffer_minutes
                if departure > end + TIME_EPS:
                    return
                now = min(end, max(now, departure))
                self.route, self._distances, self._edge_index = route, distances, 0
                self.state = 'walking'
                self._set_edge()
                self._emit('departure', now)
                continue
            if self.state == 'waiting_for_class':
                if self.target_class.end_minute <= now + TIME_EPS:
                    self._miss(now)
                    self.state = 'idle'
                    continue
                if self.target_class.start_minute > end + TIME_EPS:
                    return
                now = min(end, max(now, self.target_class.start_minute))
                late = max(0.0, now - self.target_class.start_minute)
                self.state = 'in_class'
                self._emit('class_start', now, lateness=late)
                if late > TIME_EPS:
                    self.model.late_arrivals += 1
                continue
            if self.state == 'in_class':
                if self.target_class.end_minute > end + TIME_EPS:
                    return
                now = min(end, max(now, self.target_class.end_minute))
                self._emit('class_end', now)
                self.model.completed_classes += 1
                self._index += 1
                self.target_class = None
                self.state = 'idle'
