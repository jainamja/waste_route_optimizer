import math
from geopy.distance import geodesic
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

class ACO_VRP:
    def __init__(self, start_coord, end_coord, customers, num_trucks=3, **kwargs):
        self.start_coord = start_coord
        self.end_coord = end_coord
        self.customers = customers
        self.num_trucks = num_trucks
        
        self.nodes = [self.start_coord]
        self.customer_id_map = {}
        for idx, c in enumerate(customers):
            self.nodes.append((c['lat'], c['lng']))
            self.customer_id_map[idx + 1] = c['id']
            
        self.nodes.append(self.end_coord)
        self.num_nodes = len(self.nodes)
        
        self.start_node = 0
        self.end_node = self.num_nodes - 1
        
        # Calculate distance matrix using OSRM True Driving Distances
        import requests
        
        coords_str = ";".join([f"{n[1]},{n[0]}" for n in self.nodes])
        osrm_url = f"https://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=distance"
        
        osrm_success = False
        try:
            res = requests.get(osrm_url, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get('code') == 'Ok' and 'distances' in data:
                    self.distance_matrix = []
                    for row in data['distances']:
                        # distances in meters, fallback to 999999 if null
                        self.distance_matrix.append([int(d) if d is not None else 999999 for d in row])
                    osrm_success = True
        except Exception as e:
            print("OSRM Matrix Error:", e)
            
        if not osrm_success:
            print("Falling back to geodesic distance matrix")
            self.distance_matrix = []
            for i in range(self.num_nodes):
                row = []
                for j in range(self.num_nodes):
                    if i == j:
                        row.append(0)
                    else:
                        dist_km = geodesic(self.nodes[i], self.nodes[j]).kilometers
                        row.append(int(dist_km * 1000))  # Convert to meters
                self.distance_matrix.append(row)

    def run(self):
        manager = pywrapcp.RoutingIndexManager(
            self.num_nodes, 
            self.num_trucks, 
            [self.start_node] * self.num_trucks, 
            [self.end_node] * self.num_trucks
        )
        routing = pywrapcp.RoutingModel(manager)

        def distance_callback(from_index, to_index):
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            return self.distance_matrix[from_node][to_node]

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

        # Distance dimension
        dimension_name = 'Distance'
        routing.AddDimension(
            transit_callback_index,
            0,  # no slack
            300000,  # vehicle maximum travel distance in meters (300 km)
            True,  # start cumul to zero
            dimension_name)
        
        # We do NOT use GlobalSpanCostCoefficient on distance. 
        # Forcing equal distances makes trucks drive useless miles (zigzagging) just to match the longest route!
        
        # Stops dimension (to balance the workload)
        routing.AddConstantDimension(
            1, # increment by 1 for every node visited
            100, # capacity (max stops)
            True, # start at zero
            "Stops"
        )
        stops_dimension = routing.GetDimensionOrDie("Stops")
        
        # Force every truck to take a roughly even number of stops.
        # We use SOFT bounds with a huge penalty to prevent the solver from failing 
        # to find an initial feasible solution, while still strongly forcing it to balance the fleet.
        ideal_stops = len(self.customers) / self.num_trucks
        max_stops = math.ceil(ideal_stops) + 4
        min_stops = max(1, math.floor(ideal_stops) - 4)
        
        for vehicle_id in range(self.num_trucks):
            stops_dimension.SetCumulVarSoftUpperBound(routing.End(vehicle_id), max_stops, 1000000)
            stops_dimension.SetCumulVarSoftLowerBound(routing.End(vehicle_id), min_stops, 1000000)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
        search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        search_parameters.time_limit.FromSeconds(5) # Allow 5 seconds for deep search

        solution = routing.SolveWithParameters(search_parameters)

        if not solution:
            return [], 0

        routes = []
        total_dist_meters = 0
        
        for vehicle_id in range(self.num_trucks):
            route = []
            index = routing.Start(vehicle_id)
            while not routing.IsEnd(index):
                node_index = manager.IndexToNode(index)
                if node_index not in (self.start_node, self.end_node):
                    route.append(self.customer_id_map[node_index])
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                total_dist_meters += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
            routes.append(route)

        total_distance_km = total_dist_meters / 1000.0
        return routes, total_distance_km
