"""Management command to preprocess and geocode fuel stations in the database."""

import logging
import time
from typing import Optional, Tuple
import requests
from django.core.management.base import BaseCommand
from routes.models import FuelStation, GeocodeStatus

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Preprocess and geocode fuel stations using US Census Geocoder & Nominatim."

    def add_arguments(self, parser):
        parser.add_argument(
            '--limit',
            type=int,
            default=None,
            help="Maximum number of stations to geocode in this run"
        )
        parser.add_argument(
            '--retry-failed',
            action='store_true',
            help="Retry previously failed stations"
        )
        parser.add_argument(
            '--delay',
            type=float,
            default=0.2,
            help="Delay in seconds between requests (default: 0.2s)"
        )

    def handle(self, *args, **options):
        limit = options['limit']
        retry_failed = options['retry_failed']
        delay = options['delay']

        qs = FuelStation.objects.filter(latitude__isnull=True)
        if not retry_failed:
            qs = qs.filter(geocode_status=GeocodeStatus.PENDING)
        else:
            qs = qs.filter(geocode_status__in=[GeocodeStatus.PENDING, GeocodeStatus.FAILED])

        if limit:
            qs = qs[:limit]

        stations = list(qs)
        total = len(stations)

        if total == 0:
            self.stdout.write(self.style.SUCCESS("No pending stations to geocode."))
            return

        self.stdout.write(self.style.NOTICE(f"Starting geocoding for {total} stations..."))

        success_count = 0
        failed_count = 0

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'SpotterFuelStationGeocoder/1.0',
            'Accept': 'application/json',
        })

        # Cache city/state queries in memory during batch run
        city_cache = {}

        for index, station in enumerate(stations, 1):
            coords = self._resolve_station_coordinates(session, station, city_cache)

            if coords:
                lat, lon = coords
                station.latitude = lat
                station.longitude = lon
                station.geocode_status = GeocodeStatus.SUCCESS
                station.geocode_error = ""
                station.save(update_fields=['latitude', 'longitude', 'geocode_status', 'geocode_error', 'updated_at'])
                success_count += 1
                self.stdout.write(f"[{index}/{total}] Geocoded: {station.name} ({station.city}, {station.state}) -> ({lat:.4f}, {lon:.4f})")
            else:
                station.geocode_status = GeocodeStatus.FAILED
                station.geocode_error = "Could not resolve location to US coordinates"
                station.save(update_fields=['geocode_status', 'geocode_error', 'updated_at'])
                failed_count += 1
                self.stdout.write(self.style.WARNING(f"[{index}/{total}] Failed: {station.name} ({station.city}, {station.state})"))

            if delay > 0 and index < total:
                time.sleep(delay)

        self.stdout.write(
            self.style.SUCCESS(
                f"Geocoding run completed. Success: {success_count}, Failed: {failed_count}"
            )
        )

    def _resolve_station_coordinates(
        self,
        session: requests.Session,
        station: FuelStation,
        city_cache: dict,
    ) -> Optional[Tuple[float, float]]:
        """
        Attempts to resolve coordinates using:
        1. Exact address + city + state via US Census / Nominatim
        2. City + state fallback for highway exits / rural locations
        """
        city_key = (station.city.strip().lower(), station.state.strip().lower())
        if city_key in city_cache:
            return city_cache[city_key]

        # 1. Try full address
        coords = self._query_census(session, f"{station.address}, {station.city}, {station.state}")
        if not coords:
            coords = self._query_nominatim(session, f"{station.address}, {station.city}, {station.state}")

        # 2. Fallback to city + state
        if not coords:
            coords = self._query_nominatim(session, f"{station.city}, {station.state}, USA")
            if not coords:
                coords = self._query_census(session, f"{station.city}, {station.state}")

        if coords:
            city_cache[city_key] = coords

        return coords

    def _query_census(self, session: requests.Session, query: str) -> Optional[Tuple[float, float]]:
        url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
        params = {
            'address': query,
            'benchmark': 'Public_AR_Current',
            'format': 'json',
        }
        try:
            res = session.get(url, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                matches = data.get('result', {}).get('addressMatches', [])
                if matches:
                    coords = matches[0].get('coordinates', {})
                    lon = float(coords.get('x'))
                    lat = float(coords.get('y'))
                    if 17.5 <= lat <= 71.5 and -179.5 <= lon <= -64.5:
                        return lat, lon
        except Exception:
            pass
        return None

    def _query_nominatim(self, session: requests.Session, query: str) -> Optional[Tuple[float, float]]:
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            'q': query,
            'format': 'json',
            'limit': 1,
            'countrycodes': 'us',
        }
        try:
            res = session.get(url, params=params, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if data and isinstance(data, list) and len(data) > 0:
                    lat = float(data[0]['lat'])
                    lon = float(data[0]['lon'])
                    if 17.5 <= lat <= 71.5 and -179.5 <= lon <= -64.5:
                        return lat, lon
        except Exception:
            pass
        return None
