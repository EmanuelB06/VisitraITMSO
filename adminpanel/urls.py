from django.urls import path

from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.DashboardView.as_view(), name="dashboard"),
    path("users/", views.UsersListView.as_view(), name="users"),
    path("users/create/", views.UserCreateView.as_view(), name="user_create"),
    path("users/<str:uid>/edit/", views.UserEditView.as_view(), name="user_edit"),
    path("users/<str:uid>/delete/", views.UserDeleteView.as_view(), name="user_delete"),
    path("purposes/", views.PurposesView.as_view(), name="purposes"),
    path("visitors/", views.VisitorsView.as_view(), name="visitors"),
    path("visits/", views.VisitsView.as_view(), name="visits"),
    path("audit/", views.AuditView.as_view(), name="audit"),
]
