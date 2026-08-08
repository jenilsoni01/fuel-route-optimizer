"""Views for route fuel optimization API."""

import logging
import time
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .serializers import RouteOptimizeRequestSerializer, RouteOptimizeResponseSerializer
from .services.geocoder import (
    GeocodingService,
    GeocodingError,
    LocationNotFoundError,
    LocationOutsideUSAErr,
)
from .services.routing import RoutingService, RoutingError, RouteNotFoundError
from .services.station_service import StationService
from .services.optimizer import FuelRouteOptimizer, InfeasibleRouteError, OptimizationError
from .services.fuel_calculator import format_optimization_response

logger = logging.getLogger(__name__)


class RouteOptimizeView(APIView):
    """
    POST /api/v1/routes/optimize/
    Calculates driving route between two US locations and returns the cost-optimal refueling plan.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.geocoder = GeocodingService()
        self.router = RoutingService()
        self.station_service = StationService()
        self.optimizer = FuelRouteOptimizer()

    def post(self, request, *args, **kwargs):
        serializer = RouteOptimizeRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Validation Error", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_query = serializer.validated_data['start']
        finish_query = serializer.validated_data['finish']

        start_time = time.perf_counter()
        logger.info("Processing route optimization request: '%s' -> '%s'", start_query, finish_query)

        # 1. Geocode Start & Finish Locations
        try:
            t0 = time.perf_counter()
            start_geo = self.geocoder.geocode(start_query)
            finish_geo = self.geocoder.geocode(finish_query)
            logger.info("Geocoded locations in %.2fs", time.perf_counter() - t0)
        except (LocationNotFoundError, LocationOutsideUSAErr) as exc:
            return Response(
                {"error": "Invalid Location", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except GeocodingError as exc:
            return Response(
                {"error": "Geocoding Service Unavailable", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # 2. Calculate Driving Route via OSRM
        try:
            t0 = time.perf_counter()
            route_result = self.router.get_route(
                start_lat=start_geo.latitude,
                start_lon=start_geo.longitude,
                finish_lat=finish_geo.latitude,
                finish_lon=finish_geo.longitude,
            )
            logger.info(
                "Calculated route in %.2fs (Distance: %.2f miles)",
                time.perf_counter() - t0, route_result.distance_miles
            )
        except RouteNotFoundError as exc:
            return Response(
                {"error": "Route Not Found", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except RoutingError as exc:
            return Response(
                {"error": "Routing Service Unavailable", "detail": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # 3. Spatial Candidate Station Query along Corridor
        t0 = time.perf_counter()
        candidate_stations = self.station_service.find_candidate_stations(
            route_coordinates=route_result.coordinates,
            total_route_distance_miles=route_result.distance_miles,
        )
        logger.info(
            "Found %d candidate stations in %.2fs",
            len(candidate_stations), time.perf_counter() - t0
        )

        # 4. Optimize Refueling Strategy
        try:
            t0 = time.perf_counter()
            plan = self.optimizer.optimize(
                total_distance_miles=route_result.distance_miles,
                candidate_stations=candidate_stations,
            )
            logger.info(
                "Optimization completed in %.4fs (Stops: %d, Cost: $%.2f)",
                time.perf_counter() - t0, plan.number_of_stops, plan.total_fuel_cost
            )
        except InfeasibleRouteError as exc:
            logger.warning("Infeasible route: %s", exc)
            return Response(
                {"error": "Infeasible Route", "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except OptimizationError as exc:
            logger.error("Optimization error: %s", exc)
            return Response(
                {"error": "Optimization Failed", "detail": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 5. Format & Serialize Response
        response_payload = format_optimization_response(
            route_result=route_result,
            optimization_plan=plan,
        )

        total_duration = time.perf_counter() - start_time
        logger.info("Request completed successfully in %.2fs", total_duration)

        return Response(response_payload, status=status.HTTP_200_OK)
