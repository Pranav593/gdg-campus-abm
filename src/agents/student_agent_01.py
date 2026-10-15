import pickle
import networkx as nx
import mesa

class StudentAgent(mesa.Agent):
    def __init__(self, unique_id, model, schedule):
        super().__init__(unique_id, model)
        self.schedule = schedule  # Student has a schedule
        self.current_location = "ECSW"  # Starting point
        self.current_destination = None
        self.route = []
        self.status = "idle"  # States: idle, traveling, in_class

    def step(self):
        # Simulation time advances (minutes since midnight)
        current_time = self.model.schedule_time

        if self.status == "idle":
            next_class = self.get_next_class(current_time)
            if next_class:
                self.current_destination = next_class["building"]
                self.route = self.calculate_route(self.current_location, self.current_destination)
                self.status = "traveling"
                print(f"[Time {current_time}] Student {self.unique_id} heading to {next_class['name']} at {self.current_destination}. Route: {self.route}")

        elif self.status == "traveling":
            if self.route:
                self.current_location = self.route.pop(0)
                print(f"[Time {current_time}] Student {self.unique_id} moved to: {self.current_location}")
            
            # Check if arrived at destination
            if self.current_location == self.current_destination:
                self.status = "in_class"
                print(f"[Time {current_time}] Student {self.unique_id} arrived at {self.current_destination}. Attending class.")

        elif self.status == "in_class":
            if current_time >= self.get_class_end_time():
                print(f"[Time {current_time}] Student {self.unique_id} class ended. Ready for next activity.")
                self.status = "idle"

    def get_next_class(self, current_time):
        for c in self.schedule:
            if c["start_min"] >= current_time:
                return c
        return None

    def calculate_route(self, start, target):
        try:
            path = nx.shortest_path(self.model.graph, source=start, target=target, weight="length")
            return path[1:] if len(path) > 1 else []
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            return []

    def get_class_end_time(self):
        for c in self.schedule:
            if c["building"] == self.current_destination:
                return c["end_min"]
        return 0


class CampusModel(mesa.Model):
    def __init__(self, graph):
        super().__init__()
        self.graph = graph
        self.schedule_time = 480  # Start simulation at 08:00 AM (in minutes)

    def step(self):
        # Simulation time advances by 5 minutes each tick
        self.schedule_time += 5
        self.agents.do("step")


def time_to_min(time_str):
    h, m = map(int, time_str.split(":"))
    return h * 60 + m


if __name__ == "__main__":
    # 1. Load the graph from pickle file
    GRAPH_FILE = "utd-graph/utd_graph.pkl"  
    print("Loading UTD campus graph...")
    with open(GRAPH_FILE, "rb") as f:
        campus_graph = pickle.load(f)

    # 2. Initialize the model
    simulation_model = CampusModel(campus_graph)

    # 3. Final Course Schedule Dataset
    student_schedule = [
        {
            "course_code": "ACCT 2301.001",
            "name": "Introductory Financial Accounting",
            "building": "JSOM",
            "day": "Tuesday",
            "start_time": "08:30",
            "end_time": "09:45"
        },
        {
            "course_code": "ACCT 2301.001",
            "name": "Introductory Financial Accounting",
            "building": "JSOM",
            "day": "Thursday",
            "start_time": "08:30",
            "end_time": "09:45"
        },
        {
            "course_code": "BIOL 2311.001",
            "name": "Introduction to Modern Biology I",
            "building": "SCI",
            "day": "Monday",
            "start_time": "10:00",
            "end_time": "10:50"
        },
        {
            "course_code": "BIOL 2311.001",
            "name": "Introduction to Modern Biology I",
            "building": "SCI",
            "day": "Wednesday",
            "start_time": "10:00",
            "end_time": "10:50"
        },
        {
            "course_code": "BIOL 2311.001",
            "name": "Introduction to Modern Biology I",
            "building": "SCI",
            "day": "Friday",
            "start_time": "10:00",
            "end_time": "10:50"
        },
        {
            "course_code": "ACCT 2302.007",
            "name": "Introductory Management Accounting",
            "building": "JSOM",
            "day": "Monday",
            "start_time": "14:30",
            "end_time": "15:45"
        },
        {
            "course_code": "ACCT 2302.007",
            "name": "Introductory Management Accounting",
            "building": "JSOM",
            "day": "Wednesday",
            "start_time": "14:30",
            "end_time": "15:45"
        },
        {
            "course_code": "ACCT 3331.002",
            "name": "Intermediate Financial Accounting I",
            "building": "JSOM",
            "day": "Tuesday",
            "start_time": "11:30",
            "end_time": "12:45"
        },
        {
            "course_code": "ACCT 3331.002",
            "name": "Intermediate Financial Accounting I",
            "building": "JSOM",
            "day": "Thursday",
            "start_time": "11:30",
            "end_time": "12:45"
        },
        {
            "course_code": "ACCT 3341.001",
            "name": "Cost Management Systems",
            "building": "JSOM",
            "day": "Tuesday",
            "start_time": "17:30",
            "end_time": "18:45"
        },
        {
            "course_code": "ACCT 3341.001",
            "name": "Cost Management Systems",
            "building": "JSOM",
            "day": "Thursday",
            "start_time": "17:30",
            "end_time": "18:45"
        }
    ]

    # Pre-process schedule items to add minute equivalents for the agent model
    for course in student_schedule:
        course["start_min"] = time_to_min(course["start_time"])
        course["end_min"] = time_to_min(course["end_time"])

    # Sort schedule chronologically by start time
    student_schedule.sort(key=lambda x: x["start_min"])

    # 4. Create and add student agent to the model
    student = StudentAgent(unique_id=1, model=simulation_model, schedule=student_schedule)
    simulation_model.agents.add(student)

    # 5. Run simulation loop (enough steps to cover the day's timeline)
    print("\n--- Starting Synthetic Student Simulation ---")
    for step_num in range(120):  # 120 steps * 5 mins = 600 minutes (covers 8:00 AM to ~6:00 PM)
        simulation_model.step()