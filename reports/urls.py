from django.urls import path

from . import views

app_name = "reports"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("export/", views.ExportView.as_view(), name="export"),
    path("<uuid:pk>/delete/", views.DeleteVisitView.as_view(), name="delete"),
]
