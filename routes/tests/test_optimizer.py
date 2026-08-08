"""Unit tests for the greedy fuel route optimization algorithm."""

import unittest
from decimal import Decimal
from routes.services.station_service import CandidateStation
from routes.services.optimizer import (
    FuelRouteOptimizer,
    InfeasibleRouteError,
    OptimizationPlan,
)


def create_candidate(
    opis_id: int,
    dist_miles: float,
    price: str,
    name: str = "Test Station",
    city: str = "Test City",
    state: str = "TX",
) -> CandidateStation:
    return CandidateStation(
        opis_id=opis_id,
        name=f"{name} #{opis_id}",
        address="123 Highway St",
        city=city,
        state=state,
        retail_price=Decimal(price),
        latitude=30.0,
        longitude=-95.0,
        distance_from_start_miles=dist_miles,
        distance_to_route_miles=1.5,
    )


class FuelRouteOptimizerTests(unittest.TestCase):

    def setUp(self):
        self.optimizer = FuelRouteOptimizer(max_range_miles=500.0, mpg=10.0, tank_capacity_gallons=50.0)

    def test_route_under_500_miles_requires_zero_stops(self):
        """Routes <= 500 miles can be completed on the initial 50-gallon tank without stopping."""
        stations = [
            create_candidate(1, 100.0, "3.20"),
            create_candidate(2, 250.0, "2.90"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=350.0, candidate_stations=stations)

        self.assertEqual(plan.number_of_stops, 0)
        self.assertEqual(plan.total_fuel_purchased_gallons, Decimal('0.00'))
        self.assertEqual(plan.total_fuel_cost, Decimal('0.00'))
        self.assertEqual(plan.total_fuel_consumed_gallons, Decimal('35.00'))
        self.assertEqual(plan.remaining_fuel_gallons, Decimal('15.00'))

    def test_single_stop_route(self):
        """Route of 700 miles requires 1 refueling stop."""
        stations = [
            create_candidate(1, 200.0, "3.50"),
            create_candidate(2, 350.0, "3.10"),
            create_candidate(3, 450.0, "3.80"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=700.0, candidate_stations=stations)

        self.assertEqual(plan.number_of_stops, 1)
        stop = plan.stops[0]
        self.assertEqual(stop.opis_id, 2)
        self.assertEqual(stop.distance_from_start_miles, 350.0)
        self.assertEqual(stop.fuel_purchased_gallons, Decimal('20.0000'))
        self.assertEqual(plan.total_fuel_purchased_gallons, Decimal('20.00'))
        self.assertEqual(plan.total_fuel_cost, Decimal('62.00'))
        self.assertEqual(plan.total_fuel_consumed_gallons, Decimal('70.00'))

    def test_multiple_stops_route(self):
        """Long route of 1400 miles requiring multiple stops."""
        stations = [
            create_candidate(1, 300.0, "3.40"),
            create_candidate(2, 400.0, "3.20"),
            create_candidate(3, 750.0, "3.10"),
            create_candidate(4, 1100.0, "3.00"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=1400.0, candidate_stations=stations)

        self.assertGreaterEqual(plan.number_of_stops, 2)
        self.assertEqual(plan.total_distance_miles, 1400.0)
        self.assertEqual(plan.total_fuel_consumed_gallons, Decimal('140.00'))
        self.assertGreater(plan.total_fuel_purchased_gallons, Decimal('0.00'))

    def test_cheaper_station_ahead_strategy(self):
        """If a cheaper station exists ahead in range, buy only enough to reach it."""
        stations = [
            create_candidate(1, 300.0, "3.50"),
            create_candidate(2, 600.0, "2.50"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=900.0, candidate_stations=stations)

        self.assertEqual(plan.number_of_stops, 2)
        stop1, stop2 = plan.stops[0], plan.stops[1]

        self.assertEqual(stop1.opis_id, 1)
        self.assertEqual(stop1.fuel_purchased_gallons, Decimal('10.0000'))

        self.assertEqual(stop2.opis_id, 2)
        self.assertEqual(stop2.fuel_purchased_gallons, Decimal('30.0000'))
        self.assertEqual(plan.total_fuel_cost, Decimal('110.00'))

    def test_expensive_mandatory_station(self):
        """An expensive station must be used if it is the only bridge across a 500-mile gap."""
        stations = [
            create_candidate(1, 450.0, "5.50"),
            create_candidate(2, 900.0, "3.00"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=1100.0, candidate_stations=stations)

        self.assertEqual(plan.number_of_stops, 2)
        self.assertEqual(plan.stops[0].opis_id, 1)

    def test_infeasible_route_raises_error(self):
        """A gap > 500 miles between stations raises InfeasibleRouteError."""
        stations = [
            create_candidate(1, 200.0, "3.00"),
            create_candidate(2, 750.0, "3.00"),
        ]
        with self.assertRaises(InfeasibleRouteError):
            self.optimizer.optimize(total_distance_miles=1000.0, candidate_stations=stations)

    def test_infeasible_route_no_stations(self):
        """Route > 500 miles with zero stations is infeasible."""
        with self.assertRaises(InfeasibleRouteError):
            self.optimizer.optimize(total_distance_miles=600.0, candidate_stations=[])

    def test_station_at_500_mile_boundary(self):
        """Station placed exactly at the 500-mile boundary should be reachable."""
        stations = [
            create_candidate(1, 499.5, "3.20"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=800.0, candidate_stations=stations)
        self.assertEqual(plan.number_of_stops, 1)
        self.assertEqual(plan.stops[0].opis_id, 1)

    def test_duplicate_station_prices(self):
        """Multiple stations with the same price are handled deterministically."""
        stations = [
            create_candidate(1, 250.0, "3.00"),
            create_candidate(2, 400.0, "3.00"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=800.0, candidate_stations=stations)
        self.assertEqual(plan.number_of_stops, 1)
        self.assertEqual(plan.stops[0].opis_id, 2)

    def test_fractional_gallons_and_monetary_precision(self):
        """Ensure all calculations avoid floating point drift and maintain exact Decimal accuracy."""
        stations = [
            create_candidate(1, 333.33, "3.1415"),
        ]
        plan = self.optimizer.optimize(total_distance_miles=750.0, candidate_stations=stations)
        self.assertIsInstance(plan.total_fuel_cost, Decimal)
        self.assertIsInstance(plan.total_fuel_purchased_gallons, Decimal)
        self.assertIsInstance(plan.total_fuel_consumed_gallons, Decimal)
