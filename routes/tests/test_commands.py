"""Tests for Django management commands (CSV import and geocoding)."""

import os
import tempfile
from decimal import Decimal
from django.test import TestCase
from django.core.management import call_command
from django.core.management.base import CommandError
from routes.models import FuelStation, GeocodeStatus


class ImportFuelStationsCommandTests(TestCase):

    def test_import_valid_csv(self):
        csv_data = (
            "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
            '101,STATION A,"I-80, EXIT 10",Omaha,NE,100,3.299\n'
            '102,STATION B,US-30,Lincoln,NE,100,3.199\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_data)
            f_path = f.name

        try:
            call_command('import_fuel_stations', f_path)
            self.assertTrue(FuelStation.objects.filter(opis_id=101).exists())
            self.assertTrue(FuelStation.objects.filter(opis_id=102).exists())
            st = FuelStation.objects.get(opis_id=101)
            self.assertEqual(st.retail_price, Decimal('3.299'))
            self.assertEqual(st.state, 'NE')
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_import_deduplicates_and_keeps_lowest_price(self):
        csv_data = (
            "OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price\n"
            '201,STATION X,Address 1,Dallas,TX,100,3.500\n'
            '201,STATION X CHEAP,Address 1,Dallas,TX,100,2.890\n'
        )
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_data)
            f_path = f.name

        try:
            call_command('import_fuel_stations', f_path)
            self.assertEqual(FuelStation.objects.filter(opis_id=201).count(), 1)
            st = FuelStation.objects.get(opis_id=201)
            self.assertEqual(st.retail_price, Decimal('2.890'))
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)

    def test_missing_required_columns_raises_error(self):
        csv_data = "Name,Address,Price\nStation,123 St,3.00\n"
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as f:
            f.write(csv_data)
            f_path = f.name

        try:
            with self.assertRaises(CommandError):
                call_command('import_fuel_stations', f_path)
        finally:
            if os.path.exists(f_path):
                os.remove(f_path)
