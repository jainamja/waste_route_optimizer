import unittest
import sys
import os

from aco_vrp import ACO_VRP

class TestOptimizerComprehensive(unittest.TestCase):
    def setUp(self):
        self.depot_start = (23.0225, 72.5714)
        self.depot_end = (23.2770, 72.4335)

    def test_zero_customers_empty_return(self):
        aco = ACO_VRP(self.depot_start, self.depot_end, [], num_trucks=3)
        routes, times, distances = aco.run()
        self.assertEqual(len(routes), 3)
        self.assertEqual(routes, [[], [], []])
        self.assertEqual(times, [0, 0, 0])
        self.assertEqual(distances, [0, 0, 0])

    def test_single_customer_multiple_trucks(self):
        customers = [
            {'id': 1001, 'lat': 23.0300, 'lng': 72.5800}
        ]
        aco = ACO_VRP(self.depot_start, self.depot_end, customers, num_trucks=2)
        routes, times, distances = aco.run()
        self.assertEqual(len(routes), 2)
        assigned_cids = [cid for r in routes for cid in r]
        self.assertEqual(assigned_cids, [1001])
        # Exactly one truck should have 1 customer, the other 0
        truck_lens = sorted([len(r) for r in routes])
        self.assertEqual(truck_lens, [0, 1])

    def test_multiple_customers_partitioning(self):
        customers = [
            {'id': 1, 'lat': 23.03, 'lng': 72.58},
            {'id': 2, 'lat': 23.04, 'lng': 72.59},
            {'id': 3, 'lat': 23.05, 'lng': 72.60},
            {'id': 4, 'lat': 23.06, 'lng': 72.61},
            {'id': 5, 'lat': 23.07, 'lng': 72.62}
        ]
        aco = ACO_VRP(self.depot_start, self.depot_end, customers, num_trucks=2)
        routes, times, distances = aco.run()
        self.assertEqual(len(routes), 2)
        assigned_cids = [cid for r in routes for cid in r]
        self.assertEqual(sorted(assigned_cids), [1, 2, 3, 4, 5])
        # Both trucks should be utilized
        for r in routes:
            self.assertGreater(len(r), 0)

    def test_multi_depot_arrays(self):
        starts = [(23.02, 72.57), (23.05, 72.55)]
        ends = [(23.27, 72.43), (23.25, 72.45)]
        customers = [
            {'id': 11, 'lat': 23.03, 'lng': 72.56},
            {'id': 12, 'lat': 23.04, 'lng': 72.57}
        ]
        aco = ACO_VRP(starts, ends, customers, num_trucks=2)
        routes, times, distances = aco.run()
        self.assertEqual(len(routes), 2)
        assigned_cids = [cid for r in routes for cid in r]
        self.assertEqual(sorted(assigned_cids), [11, 12])

    def test_identical_coordinates_handled_gracefully(self):
        # Two customers located at identical GPS coordinates (e.g. apartment building)
        customers = [
            {'id': 201, 'lat': 23.035, 'lng': 72.565},
            {'id': 202, 'lat': 23.035, 'lng': 72.565}
        ]
        aco = ACO_VRP(self.depot_start, self.depot_end, customers, num_trucks=1)
        routes, times, distances = aco.run()
        self.assertEqual(len(routes), 1)
        self.assertEqual(set(routes[0]), {201, 202})

if __name__ == '__main__':
    unittest.main()
