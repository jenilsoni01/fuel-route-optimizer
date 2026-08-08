"""Routing service interfacing with OSRM driving route engine."""

import logging
import time
from dataclasses import dataclass
from typing import List, Tuple
from django.conf import settings
from django.core.cache import cache
import requests

logger = logging.getLogger(__name__)

METERS_TO_MILES = 0.000621371
SECONDS_TO_MINUTES = 1.0 / 60.0


class RoutingError(Exception):
    """Base exception for routing engine failures."""
    pass


class RouteNotFoundError(RoutingError):
    """Raised when no drivable route exists between start and finish."""
    pass


@dataclass(frozen=True)
class RouteResult:
    distance_miles: float
    duration_minutes: float
    geometry: dict
    coordinates: List[Tuple[float, float]]  # List of (latitude, longitude)

    def to_dict(self) -> dict:
        return {
            'distance_miles': self.distance_miles,
            'duration_minutes': self.duration_minutes,
            'geometry': self.geometry,
        }


class RoutingService:
    """
    Calculates driving route between two points using OSRM with response caching.
    """

    def __init__(
        self,
        base_url: str = None,
        timeout: int = None,
    ):
        self.base_url = (base_url or getattr(settings, 'OSRM_BASE_URL', 'https://router.project-osrm.org')).rstrip('/')
        self.timeout = timeout or getattr(settings, 'ROUTING_TIMEOUT_SECONDS', 15)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': getattr(settings, 'GEOCODING_USER_AGENT', 'SpotterFuelOptimizer/1.0'),
            'Accept': 'application/json',
        })

    def get_route(
        self,
        start_lat: float,
        start_lon: float,
        finish_lat: float,
        finish_lon: float,
    ) -> RouteResult:
        """
        Calculates driving route between origin and destination coordinates.
        Coordinates are passed as (lat, lon) and sent to OSRM as (lon, lat).
        """
        cache_key = f"route:{start_lat:.4f}_{start_lon:.4f}_{finish_lat:.4f}_{finish_lon:.4f}"
        cached = cache.get(cache_key)
        if cached:
            logger.debug("Routing cache hit for %s", cache_key)
            coords = [(p[1], p[0]) for p in cached['geometry'].get('coordinates', [])]
            return RouteResult(
                distance_miles=cached['distance_miles'],
                duration_minutes=cached['duration_minutes'],
                geometry=cached['geometry'],
                coordinates=coords,
            )

        url = f"{self.base_url}/route/v1/driving/{start_lon},{start_lat};{finish_lon},{finish_lat}"
        params = {
            'overview': 'full',
            'geometries': 'geojson',
            'steps': 'false',
        }

        logger.info(
            "Calling OSRM route API: start=(%.4f, %.4f) -> finish=(%.4f, %.4f)",
            start_lat, start_lon, finish_lat, finish_lon
        )
        start_time = time.perf_counter()

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            duration_s = time.perf_counter() - start_time
            logger.info("OSRM responded in %.2f seconds (HTTP %d)", duration_s, response.status_code)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            logger.error("Routing request timed out: %s", exc)
            raise RoutingError("The routing service timed out while calculating the route.") from exc
        except requests.RequestException as exc:
            logger.error("Routing HTTP request failed: %s", exc)
            raise RoutingError("Failed to reach the external routing engine.") from exc
        except ValueError as exc:
            logger.error("Invalid JSON response from routing engine: %s", exc)
            raise RoutingError("Received invalid response from the routing engine.") from exc

        code = data.get('code')
        if code != 'Ok' or not data.get('routes'):
            logger.warning("OSRM returned non-OK status: %s", data)
            raise RouteNotFoundError(f"Could not calculate a drivable route between specified coordinates (OSRM status: {code}).")

        best_route = data['routes'][0]
        distance_meters = best_route.get('distance', 0.0)
        duration_seconds = best_route.get('duration', 0.0)
        geometry = best_route.get('geometry', {})

        distance_miles = round(distance_meters * METERS_TO_MILES, 2)
        duration_minutes = round(duration_seconds * SECONDS_TO_MINUTES, 2)

        # Extract (lat, lon) tuples from GeoJSON [lon, lat] coordinates
        raw_coords = geometry.get('coordinates', [])
        lat_lon_coords = [(pt[1], pt[0]) for pt in raw_coords]

        result = RouteResult(
            distance_miles=distance_miles,
            duration_minutes=duration_minutes,
            geometry=geometry,
            coordinates=lat_lon_coords,
        )

        cache.set(cache_key, result.to_dict(), timeout=getattr(settings, 'CACHE_TTL_SECONDS', 86400))
        return result
