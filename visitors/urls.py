from django.urls import path

from . import views

app_name = "visitors"

urlpatterns = [
    # Staff-assisted registration.
    path("register/", views.RegisterVisitorView.as_view(), name="register"),
    path("api/lookup/", views.visitor_lookup, name="lookup"),

    # Visitor self-service accounts.
    path("visitor-register/", views.VisitorRegisterView.as_view(), name="visitor_register"),
    path("visitor-login/", views.VisitorLoginView.as_view(), name="login"),
    path("visitor-logout/", views.visitor_logout, name="logout"),
    path("visitor-dashboard/", views.VisitorDashboardView.as_view(), name="dashboard"),
    path("visitor-profile/", views.VisitorProfileView.as_view(), name="profile"),
    path("visitor-password/", views.VisitorPasswordChangeView.as_view(), name="password_change"),

    # Staff visitor profile + QR badge.
    path("<uuid:pk>/", views.VisitorDetailView.as_view(), name="detail"),
    path("<uuid:pk>/qr.svg", views.VisitorQrView.as_view(), name="qr"),
]
