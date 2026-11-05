import pickle
import random
import networkx as nx
import mesa

class StudentAgent(mesa.Agent):
    def __init__(self, unique_id, model, commuter_tag, schedule, traits, state):
        super().__init__(unique_id, model)
        self.commuter_tag = commuter_tag
        self.schedule = schedule
        self.traits = traits
        self.state = state
        
        # Initialize location and schedule times in minutes
        self.state["current_location"] = self.state.get("current_location") or "PARKING_GOLD" # Commuter starting point
        self.current_destination = None
        self.route = []
        self.status = "idle"  # States: idle, traveling, in_class

    def step(self):
        current_time = self.model.schedule_time

        # Update internal states dynamically per tick
        self.update_internal_states()

        if self.status == "idle":
            next_class = self.get_next_class(current_time)
            if next_class:
                # Factor in punctuality: higher punctuality means leaving earlier
                buffer_time = int(15 * self.traits["punctuality"])
                departure_time = next_class["start_min"] - buffer_time

                if current_time >= departure_time:
                    # Check class skip tendency based on traits
                    if random.random() < self.traits["class_skip_tendency"]:
                        print(f"[Time {current_time}] Student {self.unique_id} decided to skip {next_class['section_id']} due to class_skip_tendency.")
                        # Mark this class as attended/skipped so we don't keep checking it
                        next_class["skipped"] = True
                        return

                    self.current_destination = next_class["building"]
                    self.state["destination"] = self.current_destination
                    self.route = self.calculate_route(self.state["current_location"], self.current_destination)
                    self.status = "traveling"
                    self.state["current_activity"] = "traveling"
                    print(f"[Time {current_time}] Student {self.unique_id} heading to {next_class['section_id']} at {self.current_destination}. Route: {self.route}")

        elif self.status == "traveling":
            if self.route:
                self.state["current_location"] = self.route.pop(0)
                print(f"[Time {current_time}] Student {self.unique_id} moved to: {self.state['current_location']}")
            
            # Check if arrived at destination
            if self.state["current_location"] == self.current_destination:
                self.status = "in_class"
                self.state["current_activity"] = "in_class"
                print(f"[Time {current_time}] Student {self.unique_id} arrived at {self.current_destination}. Attending class.")

        elif self.status == "in_class":
            current_class = self.get_current_class(current_time)
            if current_class and current_time >= current_class["end_min"]:
                print(f"[Time {current_time}] Student {self.unique_id} class {current_class['section_id']} ended. Ready for next activity.")
                self.status = "idle"
                self.state["current_activity"] = "idle"

    def get_next_class(self, current_time):
        for c in self.schedule:
            if c["start_min"] > current_time and not c.get("skipped", False):
                return c
        return None

    def get_current_class(self, current_time):
        for c in self.schedule:
            if c["start_min"] <= current_time <= c["end_min"]:
                return c
        return None

    def calculate_route(self, start, target):
        try:
            path = nx.shortest_path(self.model.graph, source=start, target=target, weight="length")
            return path[1:] if len(path) > 1 else []
        except (nx.NodeNotFound, nx.NetworkXNoPath):
            # Fallback if specific node isn't in graph keys directly
            return [target]

    def update_internal_states(self):
        # Hunger increases slightly over time based on meal regularness
        self.state["hunger"] = min(1.0, self.state["hunger"] + 0.005 * (2.0 - self.traits["meal_regularness"]))
        # Energy decreases slightly during the day
        self.state["energy"] = max(0.0, self.state["energy"] - 0.002)


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
    try:
        with open(GRAPH_FILE, "rb") as f:
            campus_graph = pickle.load(f)
    except FileNotFoundError:
        print(f"Warning: Graph file '{GRAPH_FILE}' not found. Creating a dummy graph for demonstration.")
        campus_graph = nx.Graph()
        campus_graph.add_edge("PARKING_GOLD", "ECSW", length=100)
        campus_graph.add_edge("ECSW", "SCI", length=150)

    # 2. Initialize the model
    simulation_model = CampusModel(campus_graph)

    # 3. Student Profile Configuration (incorporating your exact data)
    commuter_tag = {
        "type": "commuter",
        "parking_permit": "gold"
    }

    student_schedule = [
        {
            "section_id": "cs2336.001.26s",
            "day": "Monday",
            "start_time": "10:00",
            "end_time": "11:15",
            "building": "ECSW",
            "floor": 2,
            "room": "225"
        },
        {
            "section_id": "math2418.001.26s",
            "day": "Monday",
            "start_time": "13:00",
            "end_time": "14:15",
            "building": "SCI",
            "floor": 2,
            "room": "225"
        }
    ]

    traits = {
        "attendance": 0.90,
        "punctuality": 0.75,
        "studiousness": 0.80,
        "sociability": 0.40,
        "walking_speed_mps": 1.35,
        "leave_campus_tendency": 0.35,
        "route_consistency": 0.80,
        "meal_regularness": 0.70,
        "class_skip_tendency": 0.10,
        "campus_stay_tendency": 0.55,
        "event_interest": 0.40,
        "study_spike_response": 0.80,
        "commute_friction": 0.60,
        "dorm_return_tendency": 0.05,
        "parking_loyalty": 0.75
    }

    state = {
        "current_location": "PARKING_GOLD",
        "destination": None,
        "current_activity": "off_campus",
        "hunger": 0.20,
        "energy": 0.85,
        "mood": 0.70,
        "time_pressure": 0.10
    }

    # Pre-process schedule items to add minute equivalents
    for course in student_schedule:
        course["start_min"] = time_to_min(course["start_time"])
        course["end_min"] = time_to_min(course["end_time"])

    # Sort schedule chronologically by start time
    student_schedule.sort(key=lambda x: x["start_min"])

    # 4. Create and add student agent to the model
    student = StudentAgent(
        unique_id=1,
        model=simulation_model,
        commuter_tag=commuter_tag,
        schedule=student_schedule,
        traits=traits,
        state=state
    )
    simulation_model.agents.add(student)

    # 5. Run simulation loop (e.g., 120 steps * 5 mins = 600 minutes / 8:00 AM to 6:00 PM)
    print("\n--- Starting Synthetic Student Simulation with Traits & State ---")
    for step_num in range(120):
        simulation_model.step()