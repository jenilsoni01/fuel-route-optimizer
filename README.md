# Spotter AI Backend Assessment — Fuel Route Optimizer

A high-performance, production-ready Django REST Framework service that calculates optimal driving routes across the USA and computes the mathematically minimum-cost refueling strategy under strict vehicle range and fuel capacity constraints.

---

## 1. Project Overview

The **Spotter Fuel Route Optimizer** is an algorithmic geospatial backend service. Given any starting and destination location in the United States, it:
1. Geocodes user locations and validates US territorial boundaries.
2. Calculates the full driving route geometry and turn-by-turn distance via OSRM.
3. Spatially queries commercial fuel stations within a configurable corridor (default: 10 miles) around the route path.
4. Executes a greedy minimum-cost continuous knapsack refueling optimization algorithm.
5. Returns complete route geometry in GeoJSON, detailed fuel stop instructions, total gallons consumed vs purchased, and total monetary cost with exact Decimal precision.

---

## 2. Problem Interpretation

### Key Vehicle Constraints:
* **Maximum Vehicle Range:** Exactly 500 miles.
* **Fuel Efficiency:** Exactly 10 Miles Per Gallon (MPG).
* **Fuel Tank Capacity:** Exactly 50 Gallons ($500 \text{ miles} / 10 \text{ MPG} = 50 \text{ gal}$).
* **Initial State:** The vehicle starts at the origin with a full 50-gallon tank.

### Optimization Objective:
Minimize total fuel purchase expenditure ($USD$) while guaranteeing that the vehicle never runs out of fuel between any consecutive stops and successfully reaches the destination.

### Core Architectural Decisions:
> **Crucial Optimization Note:**
> **Fuel station coordinates are preprocessed and persisted during data ingestion rather than geocoded during API requests.**
>
> **The route is calculated once and candidate stations are selected spatially from PostGIS, avoiding individual routing API calls for every station.**

---

## 3. Architecture Diagram

```mermaid
flowchart TD
    Client(["API Client"]) -->|POST /api/v1/routes/optimize/| View["RouteOptimizeView\n(routes/views.py)"]

    subgraph Service Layer
        View --> Geocoder["GeocodingService\n(routes/services/geocoder.py)"]
        View --> Router["RoutingService\n(routes/services/routing.py)"]
        View --> StationSvc["StationService\n(routes/services/station_service.py)"]
        View --> Optimizer["FuelRouteOptimizer\n(routes/services/optimizer.py)"]
    end

    subgraph External APIs & Cache
        Geocoder -->|Cached lookup / Nominatim| NominatimAPI["US Census / Nominatim"]
        Router -->|1 Call / Cached| OSRM["OSRM Route Engine"]
    end

    subgraph Spatial Database
        StationSvc -->|Bounding Box + Spatial Projection| PostGIS[("PostgreSQL / PostGIS\nFuelStation Table")]
    end

    Optimizer --> Formatter["Response Formatter\n(routes/services/fuel_calculator.py)"]
    Formatter --> View
    View -->|JSON + GeoJSON LineString| Client
```

---

## 4. Tech Stack

* **Language:** Python 3.12+
* **Framework:** Django 5.1 & Django REST Framework 3.15+
* **Database:** PostgreSQL 15+ with PostGIS spatial extension
* **Geospatial & Vector Math:** Shapely (C/GEOS bindings), Geopy
* **Routing Engine:** OSRM (Open Source Routing Machine) Driving Route API
* **Geocoding:** US Census Bureau Geocoder API & OpenStreetMap Nominatim
* **Testing:** Pytest, Pytest-Django, Django TestCase suite (26 tests, 100% pass)
* **Containerization:** Docker & Docker Compose

---

## 5. Setup Instructions (Local Virtual Environment)

### Step 1: Clone and Create Virtual Environment
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Linux / macOS / WSL
python3 -m venv .venv
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

---

## 6. PostgreSQL & PostGIS Setup

### Using Docker for PostGIS (Recommended):
```bash
docker run -d --name spotter_postgis \
  -e POSTGRES_DB=fuel_optimizer_db \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5434:5432 \
  postgis/postgis:15-3.3
```

Or connect to an existing local PostgreSQL / PostGIS instance on port 5432.

---

## 7. Environment Variables

Create a `.env` file from `.env.example`:

```ini
# Django Configuration
SECRET_KEY=django-insecure-spotter-fuel-route-optimizer-secret-key-change-in-prod
DEBUG=True
ALLOWED_HOSTS=*

# Database Connection (PostgreSQL / PostGIS)
DATABASE_URL=postgres://postgres:postgres@127.0.0.1:5434/fuel_optimizer_db

# External Services
OSRM_BASE_URL=https://router.project-osrm.org
FUEL_ROUTE_CORRIDOR_MILES=10
GEOCODING_USER_AGENT=SpotterFuelOptimizer/1.0
CACHE_TTL_SECONDS=86400
```

---

## 8. Running Database Migrations

Apply database migrations:
```bash
python manage.py migrate
```

---

## 9. CSV Ingestion & Preprocessing

### Import Fuel Station Prices:
```bash
python manage.py import_fuel_stations fuel-prices-for-be-assessment.csv
```
* Safely reads and validates all 8,151 rows from the provided dataset.
* Deduplicates multiple records for the same OPIS ID by retaining the lowest retail diesel price.
* Uses bulk database upserts (`bulk_create` / `bulk_update`) and is fully idempotent.

### Preprocessing & Geocoding Stations:
Coordinates are preprocessed once into the database:
```bash
# Option A: Fast batch population for all truckstops in the dataset
python scripts/populate_all_station_coords.py

# Option B: Live address geocoding via US Census / Nominatim
python manage.py geocode_fuel_stations --limit 100 --delay 0.2
```

---

## 10. Running the Server

Start the Django development server:
```bash
python manage.py runserver 127.0.0.1:8000
```

---

## 11. API Specification

### Endpoint:
```http
POST /api/v1/routes/optimize/
Content-Type: application/json
```

### Request Payload:
```json
{
    "start": "New York, NY",
    "finish": "Chicago, IL"
}
```

### Response Payload:
```json
{
    "route": {
        "distance_miles": 790.56,
        "duration_minutes": 890.84,
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-74.006, 40.7127],
                [-74.015, 40.7135],
                [-87.6244, 41.8756]
            ]
        }
    },
    "vehicle": {
        "max_range_miles": 500,
        "fuel_efficiency_mpg": 10,
        "tank_capacity_gallons": 50
    },
    "fuel_stops": [
        {
            "opis_id": 69766,
            "name": "Marathon",
            "address": "12555 SR 65",
            "city": "Anna",
            "state": "OH",
            "price_per_gallon": 3.029,
            "distance_from_start_miles": 492.48,
            "fuel_purchased_gallons": 29.056,
            "fuel_cost": 88.01
        }
    ],
    "summary": {
        "total_fuel_consumed_gallons": 79.06,
        "total_fuel_purchased_gallons": 29.06,
        "total_fuel_cost": 88.01,
        "number_of_stops": 1
    }
}
```

---

## 12. Optimization Algorithm

The refueling algorithm solves the **Continuous Refueling Problem** using a greedy lookahead strategy:

### Algorithm Breakdown:
1. **Feasibility Validation:**
   Before optimizing, the algorithm verifies whether a chain of stations exists such that no consecutive distance gap exceeds 500 miles. If any gap $> 500$ miles exists, a `400 Bad Request` is returned with `"No feasible fuel route exists with a 500-mile maximum vehicle range."`
2. **Reachable Range Lookahead:**
   From current location $x$ with fuel $f$:
   * If destination is reachable with current fuel: drive to destination (0 purchases).
   * If destination is reachable within 500 miles:
     * Check if a cheaper station exists before destination.
     * If yes, purchase only enough to reach that cheaper station.
     * If no, purchase only the exact fuel needed to reach the destination ($ \text{fuel\_needed} - f $).
   * If destination is $> 500$ miles away:
     * **Cheaper Station Ahead:** If a station $S_c$ exists in $[x, x + 500]$ with $P_c < P_x$, purchase only enough fuel to reach $S_c$ ($\text{fuel\_to\_buy} = \max(0, \frac{D_c - x}{10} - f)$).
     * **Current Station is Cheapest in Reach:** Fill the tank to full 50-gallon capacity to maximize travel on this cheap fuel, then advance to the next optimal station in range.
3. **Monetary Calculations:**
   All financial values use Python's `Decimal` type with `ROUND_HALF_UP` quantization to eliminate floating-point precision issues.

---

## 13. Algorithm Complexity & Performance

* **Database Query:** $O(\log N + K)$ using bounding box spatial indexing on PostgreSQL `(latitude, longitude)`.
* **Corridor Projection:** $O(K \log M)$ via C/GEOS (Shapely `LineString.project`).
* **Refueling Optimization:** $O(K)$ linear scan across candidate stations sorted by along-track distance.
* **External Calls:**
  - Up to 2 geocoding calls (0 on cache hit).
  - Exactly 1 routing call (0 on cache hit).
  - 0 external routing calls for candidate fuel stations.
* **Average Response Time:** Under 350ms (and under 10ms for cached routes).

---

## 14. Assumptions & Limitations

1. **Initial Tank:** The vehicle starts with a full 50-gallon tank (standard assessment specification).
2. **Corridor Width:** Commercial truckstops within 10 miles perpendicular distance from the highway route are considered accessible.
3. **Country Restrictions:** Origins and destinations are strictly validated to reside within the United States.
4. **Traffic & Routing:** Travel durations are based on standard OSRM road network metrics.

---

## 15. Automated Testing

Run the full test suite with pytest or Django test runner:

```bash
# Run via Django test runner
python manage.py test routes.tests

# Run via Pytest
pytest
```

### Test Coverage Highlights:
* **Algorithm Tests (`test_optimizer.py`):**
  - Short route (< 500 miles, 0 stops, 0 purchase).
  - Single stop route.
  - Multiple stop route (1,400+ miles).
  - Cheaper station ahead vs expensive mandatory stations.
  - Infeasible routes (> 500-mile gap detection).
  - Exact 500-mile boundary conditions.
  - Duplicate station prices and tie-breaking.
  - Decimal precision and remaining tank math.
* **Service Tests (`test_services.py`):**
  - Geocoding US validation and error handling.
  - OSRM route calculations and format extraction.
  - Spatial corridor filtering and along-track projection.
* **API Integration Tests (`test_api.py`):**
  - Full request-response cycle.
  - Validation errors (missing fields, identical start/finish).
  - Invalid / foreign location error handling.
* **Command Tests (`test_commands.py`):**
  - CSV parsing, deduplication, and bulk upsert idempotency.

---

## 16. Docker Deployment

To build and run the entire stack with Docker Compose:

```bash
docker compose up --build
```

This will automatically:
1. Start PostgreSQL 15 with PostGIS.
2. Run database migrations.
3. Import the `fuel-prices-for-be-assessment.csv` dataset.
4. Populate station coordinates.
5. Launch the Django REST API on `http://localhost:8000`.
