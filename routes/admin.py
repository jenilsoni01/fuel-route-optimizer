from django.contrib import admin
from .models import FuelStation


@admin.register(FuelStation)
class FuelStationAdmin(admin.ModelAdmin):
    list_display = (
        'opis_id',
        'name',
        'city',
        'state',
        'retail_price',
        'geocode_status',
        'latitude',
        'longitude',
        'updated_at',
    )
    list_filter = ('state', 'geocode_status')
    search_fields = ('opis_id', 'name', 'city', 'address', 'state')
    ordering = ('state', 'city')
    readonly_fields = ('created_at', 'updated_at')
