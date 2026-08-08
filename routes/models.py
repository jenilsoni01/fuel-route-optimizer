import logging
from decimal import Decimal
from django.db import models

logger = logging.getLogger(__name__)


class GeocodeStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending'
    SUCCESS = 'SUCCESS', 'Success'
    FAILED = 'FAILED', 'Failed'


class FuelStation(models.Model):
    """
    Model representing a commercial truck stop / fuel station.
    Stores station identifiers, location, retail diesel price, and geocoding status.
    """
    opis_id = models.IntegerField(
        unique=True,
        db_index=True,
        help_text="OPIS Truckstop Unique Identifier"
    )
    name = models.CharField(
        max_length=255,
        help_text="Truckstop Name"
    )
    address = models.CharField(
        max_length=255,
        help_text="Street / Highway Exit Address"
    )
    city = models.CharField(
        max_length=100,
        db_index=True,
        help_text="City"
    )
    state = models.CharField(
        max_length=2,
        db_index=True,
        help_text="2-letter US State abbreviation"
    )
    rack_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Rack ID from fuel supplier"
    )
    retail_price = models.DecimalField(
        max_digits=7,
        decimal_places=4,
        db_index=True,
        help_text="Retail diesel price per gallon in USD"
    )
    latitude = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text="WGS84 Latitude coordinate"
    )
    longitude = models.FloatField(
        null=True,
        blank=True,
        db_index=True,
        help_text="WGS84 Longitude coordinate"
    )
    geocode_status = models.CharField(
        max_length=20,
        choices=GeocodeStatus.choices,
        default=GeocodeStatus.PENDING,
        db_index=True,
        help_text="Status of address geocoding"
    )
    geocode_error = models.TextField(
        blank=True,
        default='',
        help_text="Error message if geocoding failed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Fuel Station"
        verbose_name_plural = "Fuel Stations"
        ordering = ['state', 'city', 'opis_id']
        indexes = [
            models.Index(fields=['state', 'city']),
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['geocode_status', 'retail_price']),
        ]

    def __str__(self) -> str:
        return f"{self.name} (OPIS #{self.opis_id}) - {self.city}, {self.state} [${self.retail_price:.2f}/gal]"

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None
