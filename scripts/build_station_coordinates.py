"""Script to build data/station_coordinates.json using US Census and Nominatim APIs with caching."""

import json
import os
import sys
import time
from pathlib import Path
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from routes.models import FuelStation, GeocodeStatus

OUTPUT_FILE = BASE_DIR / 'data' / 'station_coordinates.json'


def main():
    os.makedirs(BASE_DIR / 'data', exist_ok=True)

    stations = FuelStation.objects.all()
    print(f"Total fuel stations: {stations.count()}")

    # Load existing file if present
    coords_map = {}
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                coords_map = json.load(f)
            print(f"Loaded {len(coords_map)} cached coordinates from {OUTPUT_FILE}")
        except Exception:
            pass

    # Collect unique (city, state)
    city_map = {}
    for st in stations:
        key = f"{st.city.strip().title()}, {st.state.strip().upper()}"
        if key not in city_map:
            city_map[key] = []
        city_map[key].append(st.opis_id)

    print(f"Total unique city/state entries: {len(city_map)}")

    session = requests.Session()
    session.headers.update({
        'User-Agent': 'SpotterPrecomputation/1.0',
        'Accept': 'application/json',
    })

    updated = 0
    for idx, (place, opis_ids) in enumerate(city_map.items(), 1):
        if place in coords_map:
            continue

        # Try Census onelineaddress
        lat, lon = None, None
        try:
            res = session.get(
                "https://nominatim.openstreetmap.org/search",
                params={'q': f"{place}, USA", 'format': 'json', 'limit': 1, 'countrycodes': 'us'},
                timeout=5
            )
            if res.status_code == 200:
                d = res.json()
                if d and isinstance(d, list) and len(d) > 0:
                    lat = float(d[0]['lat'])
                    lon = float(d[0]['lon'])
        except Exception as e:
            pass

        if lat and lon and 17.5 <= lat <= 71.5 and -179.5 <= lon <= -64.5:
            coords_map[place] = {'lat': round(lat, 5), 'lon': round(lon, 5)}
            updated += 1
            if updated % 25 == 0:
                print(f"[{idx}/{len(city_map)}] Saved {place} -> ({lat:.4f}, {lon:.4f})")
                with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                    json.dump(coords_map, f, indent=2)

        time.sleep(0.1)

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(coords_map, f, indent=2)

    print(f"Completed! Total coordinates saved: {len(coords_map)}")


if __name__ == '__main__':
    main()
