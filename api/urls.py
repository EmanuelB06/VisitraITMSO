from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("purposes/", views.purposes, name="purposes"),
    path("visitors/", views.visitors, name="visitors"),
    path("visitors/bulk/", views.visitors_bulk, name="visitors-bulk"),
    path("visitors/<uuid:visitor_id>/", views.visitor_detail, name="visitor-detail"),
]
