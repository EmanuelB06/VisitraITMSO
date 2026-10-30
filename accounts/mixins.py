from __future__ import annotations

from functools import wraps

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied

from core.api import json_error

from .permissions import is_admin, is_staff_member


class AccessControlMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Redirect anonymous users to the login page, forbid signed-in users.

    ``UserPassesTestMixin`` normally redirects *everyone* who fails the test,
    which sends authenticated-but-unauthorised users back to the login page.
    Raising ``PermissionDenied`` for them renders the 403 page instead.
    """

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied(self.get_permission_denied_message())
        return super().handle_no_permission()


class StaffRequiredMixin(AccessControlMixin):
    """Require an active staff member (front desk or administrator)."""

    def test_func(self) -> bool:
        return is_staff_member(self.request.user)


class AdminRequiredMixin(AccessControlMixin):
    """Require an active administrator."""

    def test_func(self) -> bool:
        return is_admin(self.request.user)


def api_staff_required(view):
    """JSON API decorator: requires an active staff member, returns 403 on failure."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not getattr(request.user, "is_authenticated", False):
            return json_error("Authentication required.", status=403)
        if not is_staff_member(request.user):
            return json_error("Staff access required.", status=403)
        return view(request, *args, **kwargs)

    return wrapper
