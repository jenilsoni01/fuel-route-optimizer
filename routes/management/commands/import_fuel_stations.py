"""Management command to import fuel stations from the provided CSV dataset."""

import csv
import logging
import os
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from routes.models import FuelStation

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {
    'OPIS Truckstop ID',
    'Truckstop Name',
    'Address',
    'City',
    'State',
    'Rack ID',
    'Retail Price',
}


class Command(BaseCommand):
    help = "Import and deduplicate fuel stations from CSV file into the database."

    def add_arguments(self, parser):
        parser.add_argument(
            'csv_path',
            type=str,
            help="Path to the fuel station CSV file"
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help="Database batch insert size (default: 1000)"
        )

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        batch_size = options['batch_size']

        if not os.path.exists(csv_path):
            raise CommandError(f"CSV file not found at: {csv_path}")

        self.stdout.write(self.style.NOTICE(f"Opening CSV file: {csv_path}"))

        station_records = {}  # Map opis_id -> record dict (keeps lowest price on duplicate)
        total_rows_read = 0
        skipped_rows = 0

        with open(csv_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)

            # Validate header columns
            fieldnames = set(reader.fieldnames or [])
            missing_cols = REQUIRED_COLUMNS - fieldnames
            if missing_cols:
                raise CommandError(f"CSV is missing required columns: {missing_cols}")

            for row in reader:
                total_rows_read += 1
                try:
                    raw_opis_id = row['OPIS Truckstop ID'].strip()
                    if not raw_opis_id:
                        skipped_rows += 1
                        continue
                    opis_id = int(raw_opis_id)

                    name = row['Truckstop Name'].strip()
                    address = row['Address'].strip()
                    city = row['City'].strip()
                    state = row['State'].strip().upper()[:2]
                    raw_rack_id = row['Rack ID'].strip()
                    rack_id = int(raw_rack_id) if raw_rack_id.isdigit() else None

                    raw_price = row['Retail Price'].strip()
                    retail_price = Decimal(raw_price)

                    if retail_price <= Decimal('0'):
                        skipped_rows += 1
                        continue

                    # Deduplication Strategy:
                    # If OPIS ID already seen, keep record with the lower retail price
                    if opis_id in station_records:
                        existing = station_records[opis_id]
                        if retail_price < existing['retail_price']:
                            existing['retail_price'] = retail_price
                            existing['name'] = name or existing['name']
                            existing['address'] = address or existing['address']
                            existing['city'] = city or existing['city']
                            existing['state'] = state or existing['state']
                            existing['rack_id'] = rack_id or existing['rack_id']
                    else:
                        station_records[opis_id] = {
                            'opis_id': opis_id,
                            'name': name,
                            'address': address,
                            'city': city,
                            'state': state,
                            'rack_id': rack_id,
                            'retail_price': retail_price,
                        }

                except (ValueError, InvalidOperation, KeyError) as err:
                    logger.warning("Error parsing CSV row %d: %s (row: %s)", total_rows_read, err, row)
                    skipped_rows += 1
                    continue

        self.stdout.write(
            f"Read {total_rows_read} rows. Deduplicated to {len(station_records)} unique OPIS stations. Skipped: {skipped_rows}"
        )

        # Bulk upsert into PostgreSQL database
        existing_stations = {
            s.opis_id: s for s in FuelStation.objects.filter(opis_id__in=station_records.keys())
        }

        to_create = []
        to_update = []

        for opis_id, data in station_records.items():
            if opis_id in existing_stations:
                st = existing_stations[opis_id]
                st.name = data['name']
                st.address = data['address']
                st.city = data['city']
                st.state = data['state']
                st.rack_id = data['rack_id']
                st.retail_price = data['retail_price']
                to_update.append(st)
            else:
                to_create.append(FuelStation(**data))

        with transaction.atomic():
            if to_create:
                FuelStation.objects.bulk_create(to_create, batch_size=batch_size)
            if to_update:
                FuelStation.objects.bulk_update(
                    to_update,
                    ['name', 'address', 'city', 'state', 'rack_id', 'retail_price'],
                    batch_size=batch_size
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully imported {len(to_create)} new stations, updated {len(to_update)} existing stations."
            )
        )
