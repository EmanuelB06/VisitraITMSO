from django.urls import path

from . import views

app_name = "visitors"

urlpatterns = [
    path("register/", views.RegisterVisitorView.as_view(), name="register"),
    path("api/lookup/", views.visitor_lookup, name="lookup"),
]
