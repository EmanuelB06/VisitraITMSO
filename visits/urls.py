from django.urls import path

from . import views

app_name = "visits"

urlpatterns = [
    path("", views.KioskView.as_view(), name="kiosk"),
    path("api/time-in/", views.time_in, name="time-in"),
    path("api/<uuid:pk>/time-out/", views.time_out, name="time-out"),
    path("api/active/", views.active_visits, name="active"),
]
