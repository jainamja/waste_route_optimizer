import pytest
from aco_vrp import ACO_VRP

def test_aco_basic():
    start_coord = (23.0, 72.5)
    end_coord = (23.1, 72.6)
    
    customers = [
        {'id': 101, 'lat': 23.05, 'lng': 72.55},
        {'id': 102, 'lat': 23.02, 'lng': 72.51},
        {'id': 103, 'lat': 23.08, 'lng': 72.59},
        {'id': 104, 'lat': 23.01, 'lng': 72.52},
        {'id': 105, 'lat': 23.09, 'lng': 72.58}
    ]
    
    num_trucks = 2
    
    aco = ACO_VRP(start_coord, end_coord, customers, num_trucks=num_trucks, num_ants=5, num_iterations=10)
    routes, best_dist = aco.run()
    
    assert len(routes) == num_trucks
    
    # Check that all customers are visited exactly once
    all_visited = []
    for r in routes:
        all_visited.extend(r)
        
    assert sorted(all_visited) == [101, 102, 103, 104, 105]
    assert best_dist > 0
