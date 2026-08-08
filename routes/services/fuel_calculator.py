"""Fuel calculation helpers and summary generator."""

from decimal import Decimal
from typing import Dict, Any
from django.conf import settings
from .optimizer import OptimizationPlan, FuelStop
from .routing import RouteResult


def build_vehicle_specs() -> Dict[str, Any]:
    """Returns standardized vehicle specifications."""
    return {
        'max_range_miles': int(getattr(settings, 'MAX_RANGE_MILES', 500)),
        'fuel_efficiency_mpg': int(getattr(settings, 'MPG', 10)),
        'tank_capacity_gallons': int(getattr(settings, 'TANK_CAPACITY_GALLONS', 50)),
    }


def format_optimization_response(
    route_result: RouteResult,
    optimization_plan: OptimizationPlan,
) -> Dict[str, Any]:
    """
    Constructs the final API payload matching the assessment specification.
    """
    return {
        'route': {
            'distance_miles': route_result.distance_miles,
            'duration_minutes': route_result.duration_minutes,
            'geometry': route_result.geometry,
        },
        'vehicle': build_vehicle_specs(),
        'fuel_stops': [stop.to_dict() for stop in optimization_plan.stops],
        'summary': {
            'total_fuel_consumed_gallons': float(optimization_plan.total_fuel_consumed_gallons),
            'total_fuel_purchased_gallons': float(optimization_plan.total_fuel_purchased_gallons),
            'total_fuel_cost': float(optimization_plan.total_fuel_cost),
            'number_of_stops': optimization_plan.number_of_stops,
        },
    }
