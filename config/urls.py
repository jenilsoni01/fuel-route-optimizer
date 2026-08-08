"""URL Configuration for spotter-fuel-route-optimizer."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/routes/', include('routes.urls')),
]
