"""Fuel route optimization service implementing greedy minimum-cost refueling strategy."""

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from django.conf import settings
from .station_service import CandidateStation

logger = logging.getLogger(__name__)

MAX_RANGE_MILES = 500.0
MPG = 10.0
TANK_CAPACITY_GALLONS = 50.0
TOLERANCE_MILES = 0.5


class OptimizationError(Exception):
    """Base exception for fuel optimization errors."""
    pass


class InfeasibleRouteError(OptimizationError):
    """Raised when a route cannot be completed within vehicle range limits."""
    pass


@dataclass
class FuelStop:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price_per_gallon: Decimal
    distance_from_start_miles: float
    fuel_purchased_gallons: Decimal
    fuel_cost: Decimal

    def to_dict(self) -> dict:
        return {
            'opis_id': self.opis_id,
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'price_per_gallon': float(self.price_per_gallon),
            'distance_from_start_miles': round(self.distance_from_start_miles, 2),
            'fuel_purchased_gallons': float(self.fuel_purchased_gallons),
            'fuel_cost': float(self.fuel_cost),
        }


@dataclass
class OptimizationPlan:
    total_distance_miles: float
    total_fuel_consumed_gallons: Decimal
    total_fuel_purchased_gallons: Decimal
    total_fuel_cost: Decimal
    stops: List[FuelStop]
    number_of_stops: int
    remaining_fuel_gallons: Decimal

    def to_summary_dict(self) -> dict:
        return {
            'total_fuel_consumed_gallons': float(self.total_fuel_consumed_gallons),
            'total_fuel_purchased_gallons': float(self.total_fuel_purchased_gallons),
            'total_fuel_cost': float(self.total_fuel_cost),
            'number_of_stops': self.number_of_stops,
        }


class FuelRouteOptimizer:
    """
    Computes the minimum-cost refueling strategy along a route given vehicle constraints.
    - Vehicle starts with a full tank (50 gallons).
    - Range = 500 miles.
    - Fuel Efficiency = 10 MPG.
    """

    def __init__(
        self,
        max_range_miles: float = MAX_RANGE_MILES,
        mpg: float = MPG,
        tank_capacity_gallons: float = TANK_CAPACITY_GALLONS,
    ):
        self.max_range = max_range_miles
        self.mpg = mpg
        self.tank_capacity = tank_capacity_gallons

    def optimize(
        self,
        total_distance_miles: float,
        candidate_stations: List[CandidateStation],
    ) -> OptimizationPlan:
        logger.info(
            "Starting fuel optimization for route of %.2f miles with %d candidate stations",
            total_distance_miles, len(candidate_stations)
        )

        # 1. Zero or short route within initial tank range
        if total_distance_miles <= self.max_range:
            consumed = Decimal(str(round(total_distance_miles / self.mpg, 4)))
            remaining = Decimal(str(self.tank_capacity)) - consumed
            return OptimizationPlan(
                total_distance_miles=total_distance_miles,
                total_fuel_consumed_gallons=consumed.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
                total_fuel_purchased_gallons=Decimal('0.00'),
                total_fuel_cost=Decimal('0.00'),
                stops=[],
                number_of_stops=0,
                remaining_fuel_gallons=remaining.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            )

        # 2. Check Feasibility
        self._validate_feasibility(total_distance_miles, candidate_stations)

        # 3. Execute Greedy Minimum-Cost Strategy
        return self._run_greedy_optimizer(total_distance_miles, candidate_stations)

    def _validate_feasibility(
        self,
        total_distance: float,
        stations: List[CandidateStation],
    ) -> None:
        if not stations:
            raise InfeasibleRouteError(
                "No feasible fuel route exists with a 500-mile maximum vehicle range."
            )

        current_max_reach = self.max_range
        i = 0
        n = len(stations)

        while current_max_reach < total_distance - TOLERANCE_MILES:
            farthest_reach = current_max_reach
            while i < n and stations[i].distance_from_start_miles <= current_max_reach + TOLERANCE_MILES:
                station_reach = stations[i].distance_from_start_miles + self.max_range
                if station_reach > farthest_reach:
                    farthest_reach = station_reach
                i += 1

            if farthest_reach <= current_max_reach + TOLERANCE_MILES:
                raise InfeasibleRouteError(
                    "No feasible fuel route exists with a 500-mile maximum vehicle range."
                )
            current_max_reach = farthest_reach

    def _run_greedy_optimizer(
        self,
        total_distance: float,
        stations: List[CandidateStation],
    ) -> OptimizationPlan:
        stops: List[FuelStop] = []
        current_pos = 0.0
        current_fuel = self.tank_capacity  # Start full (50 gal)
        current_station_idx = -1  # -1 represents Start

        valid_stations = [s for s in stations if 0.0 < s.distance_from_start_miles < total_distance]

        while current_pos < total_distance - TOLERANCE_MILES:
            dist_to_dest = total_distance - current_pos
            fuel_to_dest = dist_to_dest / self.mpg

            # Reachable with current fuel?
            if current_fuel >= fuel_to_dest - 1e-6:
                current_fuel -= fuel_to_dest
                current_pos = total_distance
                break

            # Reachable stations within full range from current_pos
            reachable_indices = [
                idx for idx, s in enumerate(valid_stations)
                if current_pos < s.distance_from_start_miles <= current_pos + self.max_range + TOLERANCE_MILES
            ]

            # At Start: select the best first station within 500 miles
            if current_station_idx == -1:
                if not reachable_indices:
                    raise InfeasibleRouteError(
                        "No feasible fuel route exists with a 500-mile maximum vehicle range."
                    )
                best_first_idx = self._find_best_first_station(valid_stations, reachable_indices, total_distance)
                target_station = valid_stations[best_first_idx]
                travel_dist = target_station.distance_from_start_miles - current_pos
                current_fuel -= (travel_dist / self.mpg)
                current_pos = target_station.distance_from_start_miles
                current_station_idx = best_first_idx
                continue

            current_st = valid_stations[current_station_idx]
            current_price = current_st.retail_price

            # Look for a cheaper station reachable within max_range
            cheaper_idx = None
            for idx in reachable_indices:
                if valid_stations[idx].retail_price < current_price:
                    cheaper_idx = idx
                    break

            if cheaper_idx is not None:
                # Cheaper station ahead: buy only enough to reach it
                target_station = valid_stations[cheaper_idx]
                travel_dist = target_station.distance_from_start_miles - current_pos
                fuel_needed = travel_dist / self.mpg

                fuel_to_buy = max(0.0, fuel_needed - current_fuel)
                if fuel_to_buy > 0.0:
                    cost = Decimal(str(fuel_to_buy)) * current_price
                    stops.append(
                        FuelStop(
                            opis_id=current_st.opis_id,
                            name=current_st.name,
                            address=current_st.address,
                            city=current_st.city,
                            state=current_st.state,
                            price_per_gallon=current_price,
                            distance_from_start_miles=current_st.distance_from_start_miles,
                            fuel_purchased_gallons=Decimal(str(round(fuel_to_buy, 4))),
                            fuel_cost=cost.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP),
                        )
                    )
                    current_fuel += fuel_to_buy

                current_fuel -= fuel_needed
                current_pos = target_station.distance_from_start_miles
                current_station_idx = cheaper_idx

            else:
                # No cheaper station reachable ahead
                # If destination is reachable from here within max_range:
                if dist_to_dest <= self.max_range + TOLERANCE_MILES:
                    fuel_to_buy = max(0.0, fuel_to_dest - current_fuel)
                    if fuel_to_buy > 0.0:
                        cost = Decimal(str(fuel_to_buy)) * current_price
                        stops.append(
                            FuelStop(
                                opis_id=current_st.opis_id,
                                name=current_st.name,
                                address=current_st.address,
                                city=current_st.city,
                                state=current_st.state,
                                price_per_gallon=current_price,
                                distance_from_start_miles=current_st.distance_from_start_miles,
                                fuel_purchased_gallons=Decimal(str(round(fuel_to_buy, 4))),
                                fuel_cost=cost.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP),
                            )
                        )
                        current_fuel += fuel_to_buy

                    current_fuel -= fuel_to_dest
                    current_pos = total_distance
                    break
                else:
                    # Must fill tank to 50 gal
                    if not reachable_indices:
                        raise InfeasibleRouteError(
                            "No feasible fuel route exists with a 500-mile maximum vehicle range."
                        )
                    fuel_to_buy = self.tank_capacity - current_fuel
                    if fuel_to_buy > 0.0:
                        cost = Decimal(str(fuel_to_buy)) * current_price
                        stops.append(
                            FuelStop(
                                opis_id=current_st.opis_id,
                                name=current_st.name,
                                address=current_st.address,
                                city=current_st.city,
                                state=current_st.state,
                                price_per_gallon=current_price,
                                distance_from_start_miles=current_st.distance_from_start_miles,
                                fuel_purchased_gallons=Decimal(str(round(fuel_to_buy, 4))),
                                fuel_cost=cost.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP),
                            )
                        )
                        current_fuel = self.tank_capacity

                    best_next_idx = self._find_best_next_station(valid_stations, reachable_indices, total_distance)
                    target_station = valid_stations[best_next_idx]
                    travel_dist = target_station.distance_from_start_miles - current_pos
                    current_fuel -= (travel_dist / self.mpg)
                    current_pos = target_station.distance_from_start_miles
                    current_station_idx = best_next_idx

        # Calculate totals
        total_consumed = Decimal(str(round(total_distance / self.mpg, 4))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        total_purchased = sum(s.fuel_purchased_gallons for s in stops).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        total_cost = sum(s.fuel_cost for s in stops).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        remaining_fuel = Decimal(str(round(max(0.0, current_fuel), 4))).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        return OptimizationPlan(
            total_distance_miles=total_distance,
            total_fuel_consumed_gallons=total_consumed,
            total_fuel_purchased_gallons=total_purchased,
            total_fuel_cost=total_cost,
            stops=stops,
            number_of_stops=len(stops),
            remaining_fuel_gallons=remaining_fuel,
        )

    def _find_best_first_station(
        self,
        stations: List[CandidateStation],
        reachable_indices: List[int],
        total_distance: float,
    ) -> int:
        best_idx = reachable_indices[0]
        min_price = stations[best_idx].retail_price
        for idx in reachable_indices:
            if stations[idx].retail_price < min_price:
                min_price = stations[idx].retail_price
                best_idx = idx
            elif stations[idx].retail_price == min_price and stations[idx].distance_from_start_miles > stations[best_idx].distance_from_start_miles:
                best_idx = idx
        return best_idx

    def _find_best_next_station(
        self,
        stations: List[CandidateStation],
        reachable_indices: List[int],
        total_distance: float,
    ) -> int:
        best_idx = reachable_indices[-1]
        min_price = stations[best_idx].retail_price
        for idx in reachable_indices:
            if stations[idx].retail_price < min_price:
                min_price = stations[idx].retail_price
                best_idx = idx
        return best_idx
