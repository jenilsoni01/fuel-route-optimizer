"""Geocoding service for resolving US locations into geographic coordinates."""

import logging
import re
from dataclasses import dataclass
from typing import Optional
from django.conf import settings
from django.core.cache import cache
import requests

logger = logging.getLogger(__name__)


class GeocodingError(Exception):
    """Base exception for geocoding failures."""
    pass


class LocationNotFoundError(GeocodingError):
    """Raised when a location query cannot be resolved to coordinates."""
    pass


class LocationOutsideUSAErr(GeocodingError):
    """Raised when a resolved location falls outside the USA."""
    pass


@dataclass(frozen=True)
class GeocodedLocation:
    query: str
    display_name: str
    latitude: float
    longitude: float
    country_code: str

    def to_dict(self) -> dict:
        return {
            'query': self.query,
            'display_name': self.display_name,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'country_code': self.country_code,
        }


class GeocodingService:
    """
    Handles address geocoding with caching, timeouts, retries, and US boundary validation.
    """

    # US geographic bounding box (including AK, HI, PR, VI)
    US_LAT_MIN = 17.5
    US_LAT_MAX = 71.5
    US_LON_MIN = -179.5
    US_LON_MAX = -64.5

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: Optional[int] = None,
    ):
        self.user_agent = user_agent or getattr(settings, 'GEOCODING_USER_AGENT', 'SpotterFuelOptimizer/1.0')
        self.timeout = timeout or getattr(settings, 'GEOCODING_TIMEOUT_SECONDS', 10)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': self.user_agent,
            'Accept': 'application/json',
        })

    def geocode(self, location_query: str) -> GeocodedLocation:
        """
        Geocode a location string into coordinates within the United States.
        Utilizes caching to avoid repeated remote API requests.
        """
        if not location_query or not location_query.strip():
            raise LocationNotFoundError("Location query cannot be empty.")

        clean_query = location_query.strip()
        cache_key = f"geocode:{re.sub(r'[^a-zA-Z0-9]', '_', clean_query.lower())}"

        # Check cache
        cached_result = cache.get(cache_key)
        if cached_result:
            logger.debug("Geocoding cache hit for query: %s", clean_query)
            return GeocodedLocation(**cached_result)

        logger.info("Geocoding location via Nominatim API: %s", clean_query)
        result = self._query_nominatim(clean_query)

        # Cache result
        cache.set(cache_key, result.to_dict(), timeout=getattr(settings, 'CACHE_TTL_SECONDS', 86400))
        return result

    def _query_nominatim(self, query: str) -> GeocodedLocation:
        """Query Nominatim OpenStreetMap Geocoding API."""
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'us',
            'addressdetails': 1,
        }

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except requests.Timeout as exc:
            logger.error("Geocoding request timed out for '%s': %s", query, exc)
            raise GeocodingError(f"Geocoding service timed out for location: '{query}'.") from exc
        except requests.RequestException as exc:
            logger.error("Geocoding HTTP request failed for '%s': %s", query, exc)
            raise GeocodingError(f"Geocoding service request failed for location: '{query}'.") from exc
        except ValueError as exc:
            logger.error("Invalid JSON response from geocoder for '%s': %s", query, exc)
            raise GeocodingError("Failed to parse geocoding service response.") from exc

        if not data or not isinstance(data, list) or len(data) == 0:
            logger.warning("Geocoding returned no results for '%s'", query)
            raise LocationNotFoundError(f"Could not resolve location: '{query}'. Please check the spelling.")

        first_match = data[0]
        try:
            lat = float(first_match['lat'])
            lon = float(first_match['lon'])
            display_name = first_match.get('display_name', query)
            country_code = first_match.get('address', {}).get('country_code', 'us').lower()
        except (KeyError, ValueError, TypeError) as exc:
            logger.error("Malformed geocoding data: %s", first_match)
            raise GeocodingError("Invalid coordinates returned by geocoder.") from exc

        # Validate US boundary
        self._validate_us_coordinates(lat, lon, country_code, query)

        return GeocodedLocation(
            query=query,
            display_name=display_name,
            latitude=lat,
            longitude=lon,
            country_code=country_code,
        )

    def _validate_us_coordinates(self, lat: float, lon: float, country_code: str, query: str) -> None:
        """Ensure resolved coordinates are strictly within the United States."""
        if country_code not in ('us', 'usa', 'united states'):
            raise LocationOutsideUSAErr(f"Location '{query}' resolved outside the USA (country: {country_code}).")

        if not (self.US_LAT_MIN <= lat <= self.US_LAT_MAX and self.US_LON_MIN <= lon <= self.US_LON_MAX):
            raise LocationOutsideUSAErr(
                f"Location '{query}' coordinates ({lat}, {lon}) are outside standard US territory."
            )
