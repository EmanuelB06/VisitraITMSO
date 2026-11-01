from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.urls import path, reverse

from .forms import LoginForm
from .permissions import is_admin
from .throttle import clear_failures, register_failure

app_name = "accounts"


class VisitraLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_invalid(self, form):
        username = (self.request.POST.get("username") or "").strip()
        if username:
            register_failure(self.request, username)
        return super().form_invalid(form)

    def form_valid(self, form):
        clear_failures(self.request, form.cleaned_data.get("username", ""))
        return super().form_valid(form)

    def get_default_redirect_url(self):
        """Send each role to the screen it works in.

        An explicit ``?next=`` still wins because ``get_success_url()`` checks
        it first; this only decides where a plain sign-in lands.
        """
        if is_admin(self.request.user):
            return reverse("reports:dashboard")
        return reverse("visits:kiosk")


class VisitraLogoutView(auth_views.LogoutView):
    next_page = "home"

    def post(self, request, *args, **kwargs):
        messages.info(request, "You have been signed out.")
        return super().post(request, *args, **kwargs)


urlpatterns = [
    path("login/", VisitraLoginView.as_view(), name="login"),
    path("logout/", VisitraLogoutView.as_view(), name="logout"),
]
