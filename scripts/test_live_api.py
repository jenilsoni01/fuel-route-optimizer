"""Live API test script covering various routes across the USA."""

import requests
import json

URL = "http://127.0.0.1:8000/api/v1/routes/optimize/"


def test_route(name, start, finish):
    print(f"\n==========================================")
    print(f"TEST: {name} ('{start}' -> '{finish}')")
    print(f"==========================================")
    response = requests.post(URL, json={"start": start, "finish": finish})
    print(f"HTTP Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Distance: {data['route']['distance_miles']} miles")
        print(f"Duration: {data['route']['duration_minutes']} minutes")
        print(f"Geometry Type: {data['route']['geometry']['type']} (coords: {len(data['route']['geometry']['coordinates'])})")
        print(f"Vehicle: {data['vehicle']}")
        print(f"Number of Stops: {data['summary']['number_of_stops']}")
        print(f"Total Fuel Consumed: {data['summary']['total_fuel_consumed_gallons']} gallons")
        print(f"Total Fuel Purchased: {data['summary']['total_fuel_purchased_gallons']} gallons")
        print(f"Total Fuel Cost: ${data['summary']['total_fuel_cost']:.2f}")
        print("Selected Stops:")
        for idx, stop in enumerate(data['fuel_stops'], 1):
            print(
                f"  [{idx}] {stop['name']} (OPIS #{stop['opis_id']}) in {stop['city']}, {stop['state']}\n"
                f"      Distance from start: {stop['distance_from_start_miles']} mi\n"
                f"      Fuel purchased: {stop['fuel_purchased_gallons']} gal @ ${stop['price_per_gallon']:.3f}/gal\n"
                f"      Cost: ${stop['fuel_cost']:.2f}"
            )
    else:
        print("Error Response:", json.dumps(response.json(), indent=2))


if __name__ == '__main__':
    test_route("Short Route (<500 mi)", "New York, NY", "Philadelphia, PA")
    test_route("Medium Route (~790 mi)", "New York, NY", "Chicago, IL")
    test_route("Interstate Route (~880 mi)", "New York, NY", "Atlanta, GA")
    test_route("Midwest to South (~1380 mi)", "Chicago, IL", "Miami, FL")
    test_route("Invalid Location", "FakeNonExistentPlace9999", "Chicago, IL")
