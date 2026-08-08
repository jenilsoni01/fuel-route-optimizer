"""Tests for GeocodingService, RoutingService, and StationService."""

from decimal import Decimal
import unittest
from unittest.mock import patch, MagicMock
from django.test import TestCase
from routes.models import FuelStation
from routes.services.geocoder import (
    GeocodingService,
    GeocodingError,
    LocationNotFoundError,
    LocationOutsideUSAErr,
    GeocodedLocation,
)
from routes.services.routing import (
    RoutingService,
    RoutingError,
    RouteNotFoundError,
    RouteResult,
)
from routes.services.station_service import StationService, CandidateStation


class GeocodingServiceTests(unittest.TestCase):

    def setUp(self):
        self.geocoder = GeocodingService()

    def test_empty_query_raises_error(self):
        with self.assertRaises(LocationNotFoundError):
            self.geocoder.geocode("")

    @patch('routes.services.geocoder.requests.Session.get')
    def test_successful_us_geocoding(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'lat': '40.7128',
                'lon': '-74.0060',
                'display_name': 'New York, USA',
                'address': {'country_code': 'us'},
            }
        ]
        mock_get.return_value = mock_response

        loc = self.geocoder.geocode("New York, NY")
        self.assertIsInstance(loc, GeocodedLocation)
        self.assertEqual(loc.latitude, 40.7128)
        self.assertEqual(loc.longitude, -74.0060)
        self.assertEqual(loc.country_code, 'us')

    @patch('routes.services.geocoder.requests.Session.get')
    def test_non_us_location_raises_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {
                'lat': '48.8566',
                'lon': '2.3522',
                'display_name': 'Paris, France',
                'address': {'country_code': 'fr'},
            }
        ]
        mock_get.return_value = mock_response

        with self.assertRaises(LocationOutsideUSAErr):
            self.geocoder.geocode("Paris, France")

    @patch('routes.services.geocoder.requests.Session.get')
    def test_location_not_found(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        with self.assertRaises(LocationNotFoundError):
            self.geocoder.geocode("NonExistentCityXYZ12345")


class RoutingServiceTests(unittest.TestCase):

    def setUp(self):
        self.router = RoutingService()

    @patch('routes.services.routing.requests.Session.get')
    def test_successful_route_calculation(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'code': 'Ok',
            'routes': [
                {
                    'distance': 160934.4,
                    'duration': 7200.0,
                    'geometry': {
                        'type': 'LineString',
                        'coordinates': [[-74.006, 40.7128], [-75.1652, 39.9526]],
                    },
                }
            ],
        }
        mock_get.return_value = mock_response

        result = self.router.get_route(40.7128, -74.006, 39.9526, -75.1652)
        self.assertIsInstance(result, RouteResult)
        self.assertEqual(result.distance_miles, 100.0)
        self.assertEqual(result.duration_minutes, 120.0)
        self.assertEqual(len(result.coordinates), 2)

    @patch('routes.services.routing.requests.Session.get')
    def test_no_route_found_raises_error(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'code': 'NoRoute', 'routes': []}
        mock_get.return_value = mock_response

        with self.assertRaises(RouteNotFoundError):
            self.router.get_route(0.0, 0.0, 10.0, 10.0)


class StationServiceTests(TestCase):

    def test_find_candidate_stations_in_corridor(self):
        FuelStation.objects.create(
            opis_id=99901,
            name="Near Route Station",
            address="100 Main St",
            city="Midway",
            state="PA",
            retail_price=Decimal("3.2500"),
            latitude=40.35,
            longitude=-74.55,
        )
        FuelStation.objects.create(
            opis_id=99902,
            name="Far Off Station",
            address="500 Far Away",
            city="Remote",
            state="TX",
            retail_price=Decimal("2.9900"),
            latitude=30.0,
            longitude=-95.0,
        )

        service = StationService(corridor_miles=15.0)
        route_coords = [(40.7128, -74.0060), (40.0, -75.0)]
        candidates = service.find_candidate_stations(route_coords, total_route_distance_miles=70.0)

        self.assertGreaterEqual(len(candidates), 1)
        found_ids = [c.opis_id for c in candidates]
        self.assertIn(99901, found_ids)
        self.assertNotIn(99902, found_ids)
