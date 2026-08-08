"""URL mappings for the routes app."""

from django.urls import path
from .views import RouteOptimizeView

urlpatterns = [
    path('optimize/', RouteOptimizeView.as_view(), name='route-optimize'),
]
