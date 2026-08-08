"""Generate comprehensive US coordinates for all truckstop cities/states."""

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from routes.models import FuelStation

DATA_FILE = BASE_DIR / 'data' / 'station_coordinates.json'


def main():
    os.makedirs(BASE_DIR / 'data', exist_ok=True)

    places = list(FuelStation.objects.values_list('city', 'state').distinct())
    print(f"Total unique (city, state) places: {len(places)}")

    # Load existing coordinates if available
    coords = {}
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                coords = json.load(f)
            print(f"Loaded {len(coords)} existing entries.")
        except Exception:
            pass

    # We can use geopy / census / nominatim or batch US coordinates
    from geopy.geocoders import Nominatim
    geolocator = Nominatim(user_agent="SpotterCoordBuilder/1.0", timeout=5)

    import time
    saved = 0
    for idx, (city, state) in enumerate(places, 1):
        place_key = f"{city.strip().title()}, {state.strip().upper()}"
        if place_key in coords:
            continue

        try:
            query = f"{city.strip()}, {state.strip()}, USA"
            loc = geolocator.geocode(query, country_codes='us')
            if loc:
                coords[place_key] = {'lat': round(loc.latitude, 5), 'lon': round(loc.longitude, 5)}
                saved += 1
                if saved % 20 == 0:
                    print(f"[{idx}/{len(places)}] Saved {place_key} -> ({loc.latitude:.4f}, {loc.longitude:.4f})")
                    with open(DATA_FILE, 'w', encoding='utf-8') as f:
                        json.dump(coords, f, indent=2)
            time.sleep(0.05)
        except Exception as err:
            time.sleep(0.5)

    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(coords, f, indent=2)

    print(f"Finished! Total saved: {len(coords)}")


if __name__ == '__main__':
    main()
