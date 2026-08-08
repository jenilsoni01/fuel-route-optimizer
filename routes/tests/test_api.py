"""Integration tests for the route optimization API endpoint."""

from decimal import Decimal
from unittest.mock import patch
from rest_framework.test import APITestCase
from rest_framework import status
from routes.models import FuelStation
from routes.services.geocoder import GeocodedLocation, LocationNotFoundError
from routes.services.routing import RouteResult, RouteNotFoundError


class RouteOptimizeAPITests(APITestCase):

    def setUp(self):
        # Create stations along a hypothetical NY to Chicago route
        self.station1 = FuelStation.objects.create(
            opis_id=1001,
            name="Pilot Travel Center #1001",
            address="I-80, Exit 50",
            city="Clearfield",
            state="PA",
            retail_price=Decimal("3.299"),
            latitude=41.0,
            longitude=-78.5,
        )
        self.station2 = FuelStation.objects.create(
            opis_id=1002,
            name="Love's Travel Stop #1002",
            address="I-80, Exit 200",
            city="Hubbard",
            state="OH",
            retail_price=Decimal("2.999"),
            latitude=41.3,
            longitude=-80.5,
        )

    def test_missing_start_field(self):
        response = self.client.post('/api/v1/routes/optimize/', {'finish': 'Chicago, IL'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('start', response.data['details'])

    def test_missing_finish_field(self):
        response = self.client.post('/api/v1/routes/optimize/', {'start': 'New York, NY'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('finish', response.data['details'])

    def test_identical_start_and_finish(self):
        response = self.client.post(
            '/api/v1/routes/optimize/',
            {'start': 'Chicago, IL', 'finish': 'Chicago, IL'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('routes.views.GeocodingService.geocode')
    def test_invalid_location_geocoding_failure(self, mock_geocode):
        mock_geocode.side_effect = LocationNotFoundError("Location not found")
        response = self.client.post(
            '/api/v1/routes/optimize/',
            {'start': 'InvalidCity12345', 'finish': 'Chicago, IL'},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'Invalid Location')

    @patch('routes.views.GeocodingService.geocode')
    @patch('routes.views.RoutingService.get_route')
    def test_successful_short_route_optimization(self, mock_get_route, mock_geocode):
        # Short route < 500 miles (0 fuel stops needed)
        mock_geocode.side_effect = [
            GeocodedLocation("New York, NY", "New York, NY, USA", 40.7128, -74.006, "us"),
            GeocodedLocation("Philadelphia, PA", "Philadelphia, PA, USA", 39.9526, -75.1652, "us"),
        ]
        mock_get_route.return_value = RouteResult(
            distance_miles=95.0,
            duration_minutes=110.0,
            geometry={'type': 'LineString', 'coordinates': [[-74.006, 40.7128], [-75.1652, 39.9526]]},
            coordinates=[(40.7128, -74.006), (39.9526, -75.1652)],
        )

        response = self.client.post(
            '/api/v1/routes/optimize/',
            {'start': 'New York, NY', 'finish': 'Philadelphia, PA'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertIn('route', data)
        self.assertEqual(data['route']['distance_miles'], 95.0)
        self.assertEqual(data['summary']['number_of_stops'], 0)
        self.assertEqual(data['summary']['total_fuel_purchased_gallons'], 0.0)
        self.assertEqual(data['vehicle']['max_range_miles'], 500)
        self.assertEqual(data['vehicle']['fuel_efficiency_mpg'], 10)

    @patch('routes.views.GeocodingService.geocode')
    @patch('routes.views.RoutingService.get_route')
    def test_successful_long_route_with_fuel_stops(self, mock_get_route, mock_geocode):
        mock_geocode.side_effect = [
            GeocodedLocation("New York, NY", "New York, NY, USA", 40.7128, -74.006, "us"),
            GeocodedLocation("Chicago, IL", "Chicago, IL, USA", 41.8781, -87.6298, "us"),
        ]
        mock_get_route.return_value = RouteResult(
            distance_miles=790.0,
            duration_minutes=720.0,
            geometry={
                'type': 'LineString',
                'coordinates': [[-74.006, 40.7128], [-78.5, 41.0], [-80.5, 41.3], [-87.6298, 41.8781]],
            },
            coordinates=[(40.7128, -74.006), (41.0, -78.5), (41.3, -80.5), (41.8781, -87.6298)],
        )

        response = self.client.post(
            '/api/v1/routes/optimize/',
            {'start': 'New York, NY', 'finish': 'Chicago, IL'},
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.data
        self.assertEqual(data['route']['distance_miles'], 790.0)
        self.assertEqual(data['summary']['total_fuel_consumed_gallons'], 79.0)
        self.assertGreaterEqual(data['summary']['number_of_stops'], 1)
        self.assertGreaterEqual(len(data['fuel_stops']), 1)
        self.assertGreater(data['summary']['total_fuel_cost'], 0.0)
