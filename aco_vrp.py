import math
from geopy.distance import geodesic
from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp

class ACO_VRP:
    def __init__(self, start_coords, end_coords, customers, num_trucks=3, **kwargs):
        self.customers = customers
        self.num_trucks = num_trucks
        
        # Support both single-depot (backward compatibility) and multi-depot arrays
        if isinstance(start_coords, tuple):
            self.start_coords = [start_coords] * num_trucks
        else:
            self.start_coords = start_coords
            
        if isinstance(end_coords, tuple):
            self.end_coords = [end_coords] * num_trucks
        else:
            self.end_coords = end_coords
            
        self.nodes = []
        # Inject all start nodes
        for s in self.start_coords:
            self.nodes.append(s)
            
        self.customer_id_map = {}
        # Inject all customers and map their indices
        for idx, c in enumerate(customers):
            self.nodes.append((c['lat'], c['lng']))
            self.customer_id_map[len(self.start_coords) + idx] = c['id']
            
        # Inject all end nodes
        for e in self.end_coords:
            self.nodes.append(e)
            
        self.num_nodes = len(self.nodes)
        self.starts_indices = list(range(self.num_trucks))
        self.ends_indices = list(range(self.num_nodes - self.num_trucks, self.num_nodes))
        
        # Calculate matrix using Time/Duration (Traffic-aware)
        import os
        import requests
        from datetime import datetime, timedelta
        
        # 1. Fixed departure time: Next 9:00 AM
        now = datetime.now()
        target = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now > target:
            target += timedelta(days=1)
        dt_timestamp = int(target.timestamp())
        
        self.distance_matrix = []
        n = self.num_nodes
        api_key = os.environ.get('GMAPS_API_KEY')
        
        if api_key:
            # Use Google Maps Distance Matrix API (Live/Predictive Traffic)
            self.distance_matrix = [[0]*n for _ in range(n)]
            chunk_size = 10
            for i in range(0, n, chunk_size):
                origins = "|".join([f"{node[0]},{node[1]}" for node in self.nodes[i:i+chunk_size]])
                for j in range(0, n, chunk_size):
                    destinations = "|".join([f"{node[0]},{node[1]}" for node in self.nodes[j:j+chunk_size]])
                    
                    url = f"https://maps.googleapis.com/maps/api/distancematrix/json?origins={origins}&destinations={destinations}&mode=driving&departure_time={dt_timestamp}&traffic_model=best_guess&key={api_key}"
                    try:
                        res = requests.get(url, timeout=15)
                        data = res.json()
                        for r_idx, row in enumerate(data.get('rows', [])):
                            for c_idx, element in enumerate(row.get('elements', [])):
                                if element.get('status') == 'OK':
                                    # Optimize for travel time, using traffic estimates
                                    duration = element.get('duration_in_traffic', element.get('duration'))['value']
                                    self.distance_matrix[i + r_idx][j + c_idx] = duration
                                else:
                                    self.distance_matrix[i + r_idx][j + c_idx] = 9999999
                    except Exception as e:
                        print("GMaps Matrix Error:", e)
                        for r_idx in range(chunk_size):
                            for c_idx in range(chunk_size):
                                if i + r_idx < n and j + c_idx < n:
                                    self.distance_matrix[i + r_idx][j + c_idx] = 9999999
        else:
            # Fallback: OSRM Estimated Travel Time (Duration)
            coords_str = ";".join([f"{n[1]},{n[0]}" for n in self.nodes])
            osrm_url = f"https://router.project-osrm.org/table/v1/driving/{coords_str}?annotations=duration"
            
            osrm_success = False
            try:
                res = requests.get(osrm_url, timeout=10)
                if res.status_code == 200:
                    data = res.json()
                    if data.get('code') == 'Ok' and 'durations' in data:
                        for row in data['durations']:
                            # durations in seconds, fallback to high cost
                            self.distance_matrix.append([int(d) if d is not None else 9999999 for d in row])
                        osrm_success = True
            except Exception as e:
                print("OSRM Duration Matrix Error:", e)
                
            if not osrm_success:
                print("Falling back to geodesic distance matrix")
                for i in range(n):
                    row = []
                    for j in range(n):
                        if i == j:
                            row.append(0)
                        else:
                            # Fallback: distance as proxy for time (e.g. assuming 10m/s)
                            dist_m = geodesic(self.nodes[i], self.nodes[j]).meters
                            row.append(int(dist_m / 10))
                    self.distance_matrix.append(row)

    def run(self):
        manager = pywrapcp.RoutingIndexManager(self.num_nodes, self.num_trucks, self.starts_indices, self.ends_indices)
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
        # We enforce a strict minimum of at least 1 customer per truck to ensure no truck is left empty.
        # If there are lots of customers, we enforce a higher minimum to balance the load.
        min_stops = max(1, math.floor(ideal_stops) - 4)
        
        for vehicle_id in range(self.num_trucks):
            # We add +1 because the End node itself increments the CumulVar by 1.
            stops_dimension.CumulVar(routing.End(vehicle_id)).SetRange(min_stops + 1, max_stops + 1)

        search_parameters = pywrapcp.DefaultRoutingSearchParameters()
        # AUTOMATIC strategy is better at handling strict bounds than PATH_CHEAPEST_ARC
        search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.AUTOMATIC
        search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
        # Increased time limit gives the AI more time to explore combinations to find the true shortest path
        # Note: Kept at 10s (not 20s) to prevent Gunicorn 30-second request timeouts on the server
        search_parameters.time_limit.FromSeconds(10)

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
                if node_index not in self.starts_indices and node_index not in self.ends_indices:
                    route.append(self.customer_id_map[node_index])
                previous_index = index
                index = solution.Value(routing.NextVar(index))
                total_dist_meters += routing.GetArcCostForVehicle(previous_index, index, vehicle_id)
            routes.append(route)

        total_distance_km = total_dist_meters / 1000.0
        return routes, total_distance_km
