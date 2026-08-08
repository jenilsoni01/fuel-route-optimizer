"""Station search service for querying and projecting candidate fuel stations along a route corridor."""

import logging
import math
from dataclasses import dataclass
from decimal import Decimal
from typing import List, Tuple
from django.conf import settings
from shapely.geometry import Point, LineString
from routes.models import FuelStation

logger = logging.getLogger(__name__)

EARTH_RADIUS_MILES = 3958.8


@dataclass
class CandidateStation:
    opis_id: int
    name: str
    address: str
    city: str
    state: str
    retail_price: Decimal
    latitude: float
    longitude: float
    distance_from_start_miles: float
    distance_to_route_miles: float

    def to_dict(self) -> dict:
        return {
            'opis_id': self.opis_id,
            'name': self.name,
            'address': self.address,
            'city': self.city,
            'state': self.state,
            'retail_price': float(self.retail_price),
            'latitude': self.latitude,
            'longitude': self.longitude,
            'distance_from_start_miles': round(self.distance_from_start_miles, 2),
            'distance_to_route_miles': round(self.distance_to_route_miles, 2),
        }


def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in miles."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return EARTH_RADIUS_MILES * c


class StationService:
    """
    Finds fuel stations located within a spatial corridor along a driving route.
    Uses Shapely vectorized geometric projections for high-performance spatial search.
    """

    def __init__(self, corridor_miles: float = None):
        self.corridor_miles = corridor_miles or getattr(settings, 'FUEL_ROUTE_CORRIDOR_MILES', 10.0)

    def find_candidate_stations(
        self,
        route_coordinates: List[Tuple[float, float]],
        total_route_distance_miles: float,
    ) -> List[CandidateStation]:
        """
        Queries fuel stations within the route corridor and projects them onto the 1D route path.
        Returns stations ordered by distance_from_start_miles.
        """
        if not route_coordinates or len(route_coordinates) < 2:
            return []

        # 1. Compute route bounding box with corridor buffer
        lats = [pt[0] for pt in route_coordinates]
        lons = [pt[1] for pt in route_coordinates]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Buffer in degrees (~1 degree lat ~= 69 miles)
        lat_buffer = (self.corridor_miles / 69.0) + 0.15
        mid_lat = (min_lat + max_lat) / 2.0
        cos_mid = max(math.cos(math.radians(mid_lat)), 0.1)
        lon_buffer = (self.corridor_miles / (69.0 * cos_mid)) + 0.15

        # 2. Database query: filter stations inside bounding box
        stations_qs = FuelStation.objects.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=min_lat - lat_buffer,
            latitude__lte=max_lat + lat_buffer,
            longitude__gte=min_lon - lon_buffer,
            longitude__lte=max_lon + lon_buffer,
        ).only(
            'opis_id', 'name', 'address', 'city', 'state',
            'retail_price', 'latitude', 'longitude'
        )

        stations_list = list(stations_qs)
        logger.info(
            "Found %d candidate stations within route bounding box (corridor: %.1f miles)",
            len(stations_list), self.corridor_miles
        )

        if not stations_list:
            return []

        # 3. Construct Shapely LineString for high performance C/GEOS projection
        # Coordinates in (lon, lat) order
        line = LineString([(pt[1], pt[0]) for pt in route_coordinates])
        # Degree buffer threshold corresponding to corridor_miles
        degree_corridor_threshold = (self.corridor_miles / 69.0) * 1.2

        candidates: List[CandidateStation] = []

        for st in stations_list:
            st_pt = Point(st.longitude, st.latitude)

            # Fast Shapely distance check in degree space
            deg_dist = line.distance(st_pt)
            if deg_dist > degree_corridor_threshold:
                continue

            # Compute normalized projection distance along route [0.0 to 1.0]
            norm_dist = line.project(st_pt, normalized=True)
            along_track_miles = norm_dist * total_route_distance_miles

            # Find exact nearest point on line to compute true Haversine cross-track distance
            nearest_geom_pt = line.interpolate(line.project(st_pt))
            cross_track_miles = haversine_distance_miles(
                st.latitude, st.longitude,
                nearest_geom_pt.y, nearest_geom_pt.x
            )

            if cross_track_miles <= self.corridor_miles:
                clamped_along_track = max(0.0, min(total_route_distance_miles, along_track_miles))
                candidates.append(
                    CandidateStation(
                        opis_id=st.opis_id,
                        name=st.name,
                        address=st.address,
                        city=st.city,
                        state=st.state,
                        retail_price=Decimal(str(st.retail_price)),
                        latitude=st.latitude,
                        longitude=st.longitude,
                        distance_from_start_miles=clamped_along_track,
                        distance_to_route_miles=cross_track_miles,
                    )
                )

        # 4. Sort candidates strictly by distance along route
        candidates.sort(key=lambda c: (c.distance_from_start_miles, c.retail_price))

        logger.info(
            "Found %d candidate stations strictly within the %.1f-mile corridor",
            len(candidates), self.corridor_miles
        )
        return candidates
