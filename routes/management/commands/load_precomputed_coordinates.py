"""Management command to load precomputed station coordinates from JSON into the database."""

import json
import os
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.conf import settings
from routes.models import FuelStation, GeocodeStatus


class Command(BaseCommand):
    help = "Populate FuelStation coordinates from precomputed data/station_coordinates.json file."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=str(settings.BASE_DIR / 'data' / 'station_coordinates.json'),
            help="Path to coordinates JSON file (default: data/station_coordinates.json)"
        )

    def handle(self, *args, **options):
        file_path = options['file']
        if not os.path.exists(file_path):
            self.stdout.write(self.style.WARNING(f"File not found: {file_path}. Nothing loaded."))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            coords_data = json.load(f)

        self.stdout.write(f"Loaded {len(coords_data)} coordinate mappings from {file_path}")

        stations = FuelStation.objects.filter(latitude__isnull=True)
        total_pending = stations.count()
        self.stdout.write(f"Pending un-geocoded stations in database: {total_pending}")

        updated_count = 0
        to_update = []

        for st in stations:
            # Check by place key
            place_key = f"{st.city.strip().title()}, {st.state.strip().upper()}"
            alt_key = f"{st.city.strip().upper()}, {st.state.strip().upper()}"
            
            coord = coords_data.get(place_key) or coords_data.get(alt_key)
            if coord:
                st.latitude = coord['lat']
                st.longitude = coord['lon']
                st.geocode_status = GeocodeStatus.SUCCESS
                st.geocode_error = ""
                to_update.append(st)
                updated_count += 1

        if to_update:
            with transaction.atomic():
                FuelStation.objects.bulk_update(
                    to_update,
                    ['latitude', 'longitude', 'geocode_status', 'geocode_error', 'updated_at'],
                    batch_size=1000
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated {updated_count} stations with precomputed coordinates!"
            )
        )
