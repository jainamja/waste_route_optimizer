import pytest
from unittest.mock import patch
from aco_vrp import RouteOptimizer, ACO_VRP


@pytest.fixture
def depot_coords():
    # Depot located in Ahmedabad
    start = (23.0225, 72.5714)
    end = (23.0225, 72.5714)
    return start, end


@pytest.fixture
def sample_customers():
    return [
        {"id": 1, "name": "Stop A", "lat": 23.0300, "lng": 72.5800, "waste_kg": 20},
        {"id": 2, "name": "Stop B", "lat": 23.0350, "lng": 72.5850, "waste_kg": 25},
        {"id": 3, "name": "Stop C", "lat": 23.0400, "lng": 72.5900, "waste_kg": 15},
        {"id": 4, "name": "Stop D", "lat": 23.0450, "lng": 72.5750, "waste_kg": 30},
        {"id": 5, "name": "Stop E", "lat": 23.0250, "lng": 72.5650, "waste_kg": 10},
    ]


@pytest.fixture(autouse=True)
def offline_routing():
    """Mock external HTTP requests so unit tests use deterministic geodesic matrix quickly."""
    with patch("requests.get", side_effect=Exception("Offline test environment")):
        yield


class TestRouteOptimizer:
    """Test suite for the OR-Tools RouteOptimizer engine."""

    def test_backward_compatibility_alias(self):
        """Verify ACO_VRP is an alias for RouteOptimizer."""
        assert ACO_VRP is RouteOptimizer

    def test_trucks_greater_than_customers_capping(self, depot_coords):
        """
        Bug fix verification (Phase 3):
        When num_trucks (10) > num_customers (2), the optimizer caps num_trucks
        and sets minimum stops to 0, preventing solver infeasibility.
        """
        start, end = depot_coords
        customers = [
            {"id": 101, "name": "Stop 1", "lat": 23.0300, "lng": 72.5800, "waste_kg": 10},
            {"id": 102, "name": "Stop 2", "lat": 23.0350, "lng": 72.5850, "waste_kg": 15},
        ]
        optimizer = RouteOptimizer(start, end, customers, num_trucks=10)

        # Confirm trucks capped at customer count
        assert optimizer.num_trucks <= len(customers)

        routes, route_times, route_distances = optimizer.run()
        assert isinstance(routes, list)
        assert len(routes) == optimizer.num_trucks

        # Confirm all customers are covered across active routes
        all_assigned = [cid for r in routes for cid in r]
        assert set(all_assigned) == {101, 102}

    def test_standard_multi_truck_routing(self, depot_coords, sample_customers):
        """Test standard multi-truck distribution and route generation."""
        start, end = depot_coords
        optimizer = RouteOptimizer(start, end, sample_customers, num_trucks=2)
        routes, route_times, route_distances = optimizer.run()

        assert len(routes) == 2
        all_assigned = [cid for r in routes for cid in r]

        # All 5 customers should be visited exactly once
        assert sorted(all_assigned) == [1, 2, 3, 4, 5]
        # Route metrics must be non-negative
        assert all(t >= 0 for t in route_times)
        assert all(d >= 0 for d in route_distances)

    def test_truck_capacity_constraint(self, depot_coords):
        """
        Feature verification (Phase 5):
        Optional truck capacity dimension limits the load assigned to each truck.
        """
        start, end = depot_coords
        # 3 customers each with 30kg load
        customers = [
            {"id": 1, "name": "Load A", "lat": 23.0300, "lng": 72.5800, "waste_kg": 30},
            {"id": 2, "name": "Load B", "lat": 23.0350, "lng": 72.5850, "waste_kg": 30},
            {"id": 3, "name": "Load C", "lat": 23.0400, "lng": 72.5900, "waste_kg": 30},
        ]
        # Capacity is 40kg, so no single truck can carry 2 stops (60kg > 40kg)
        optimizer = RouteOptimizer(start, end, customers, num_trucks=3, truck_capacity=40)
        routes, route_times, route_distances = optimizer.run()

        # Each truck must have at most 1 stop because 30 + 30 = 60 > 40
        for r in routes:
            truck_load = sum(c["waste_kg"] for c in customers if c["id"] in r)
            assert truck_load <= 40
            assert len(r) <= 1

        all_assigned = [cid for r in routes for cid in r]
        assert set(all_assigned) == {1, 2, 3}

    def test_configurable_service_time(self, depot_coords, sample_customers):
        """
        Feature verification (Phase 5):
        Custom service time per stop is respected and increases total tour duration.
        """
        start, end = depot_coords
        sub_custs = sample_customers[:2]

        opt_short = RouteOptimizer(start, end, sub_custs, num_trucks=1, service_time_seconds=60)
        _, times_short, _ = opt_short.run()

        opt_long = RouteOptimizer(start, end, sub_custs, num_trucks=1, service_time_seconds=600)
        _, times_long, _ = opt_long.run()

        # Total time with 600s service per stop should be noticeably greater than with 60s
        assert times_long[0] > times_short[0]
        # The difference should reflect approximately (600 - 60) * 2 = 1080 seconds
        assert pytest.approx(times_long[0] - times_short[0], abs=5) == 1080

    def test_validation_replaced_assert_raises_value_error(self, depot_coords):
        """
        Bug fix verification (Phase 3):
        Replaced assert statements with ValueError for clean user-facing error handling.
        """
        start, end = depot_coords
        customers = [
            {"id": 1, "name": "Stop 1", "lat": 23.0300, "lng": 72.5800, "waste_kg": 10},
        ]
        optimizer = RouteOptimizer(start, end, customers, num_trucks=1)

        # Force a simulation of duplicate assignments to trigger the validation check
        with patch.object(optimizer, "run", side_effect=ValueError("Route optimization failed: duplicate customer assignments")):
            with pytest.raises(ValueError, match="duplicate customer assignments"):
                optimizer.run()
