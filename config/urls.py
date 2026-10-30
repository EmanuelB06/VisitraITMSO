"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path

from core.views import HomeView, health

urlpatterns = [
    path("", HomeView.as_view(), name="home"),
    path("healthz/", health, name="health"),
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("visitors/", include("visitors.urls")),
    path("visits/", include("visits.urls")),
    path("dashboard/", include("reports.urls")),
]
