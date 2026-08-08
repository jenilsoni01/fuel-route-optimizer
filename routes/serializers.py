"""Django REST Framework serializers for route optimization API."""

from rest_framework import serializers


class RouteOptimizeRequestSerializer(serializers.Serializer):
    start = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        help_text="Starting location in the USA (e.g., 'New York, NY' or '10001')"
    )
    finish = serializers.CharField(
        required=True,
        allow_blank=False,
        max_length=255,
        help_text="Destination location in the USA (e.g., 'Chicago, IL' or '60601')"
    )

    def validate_start(self, value: str) -> str:
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Start location cannot be empty.")
        return val

    def validate_finish(self, value: str) -> str:
        val = value.strip()
        if not val:
            raise serializers.ValidationError("Finish location cannot be empty.")
        return val

    def validate(self, attrs):
        start = attrs.get('start', '').strip()
        finish = attrs.get('finish', '').strip()
        if start.lower() == finish.lower():
            raise serializers.ValidationError({
                "finish": "Destination location must be different from start location."
            })
        return attrs


class RouteGeometrySerializer(serializers.Serializer):
    type = serializers.CharField(default="LineString")
    coordinates = serializers.ListField(
        child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2)
    )


class RouteDetailSerializer(serializers.Serializer):
    distance_miles = serializers.FloatField()
    duration_minutes = serializers.FloatField()
    geometry = serializers.DictField()


class VehicleSpecsSerializer(serializers.Serializer):
    max_range_miles = serializers.IntegerField()
    fuel_efficiency_mpg = serializers.IntegerField()
    tank_capacity_gallons = serializers.IntegerField()


class FuelStopSerializer(serializers.Serializer):
    opis_id = serializers.IntegerField()
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    price_per_gallon = serializers.FloatField()
    distance_from_start_miles = serializers.FloatField()
    fuel_purchased_gallons = serializers.FloatField()
    fuel_cost = serializers.FloatField()


class RouteSummarySerializer(serializers.Serializer):
    total_fuel_consumed_gallons = serializers.FloatField()
    total_fuel_purchased_gallons = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    number_of_stops = serializers.IntegerField()


class RouteOptimizeResponseSerializer(serializers.Serializer):
    route = RouteDetailSerializer()
    vehicle = VehicleSpecsSerializer()
    fuel_stops = serializers.ListField(child=FuelStopSerializer())
    summary = RouteSummarySerializer()
