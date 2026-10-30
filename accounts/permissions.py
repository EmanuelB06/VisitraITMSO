"""Central capability checks for Visitra staff and administrators.

Keep role decisions here instead of scattering ``is_admin_role`` checks through
views, templates, and API endpoints.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

UserModel = get_user_model()


def is_active_user(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_active", False))


def is_staff_member(user) -> bool:
    """Front-desk or administrator account that may use the kiosk."""
    if not is_active_user(user):
        return False
    if getattr(user, "is_superuser", False):
        return True
    return getattr(user, "role", "") in {UserModel.Role.STAFF, UserModel.Role.ADMIN}


def is_admin(user) -> bool:
    """Administrator account (business admin role or superuser)."""
    return bool(is_active_user(user) and getattr(user, "is_admin_role", False))


def can_view_full_history(user) -> bool:
    return is_admin(user)


def can_export_reports(user) -> bool:
    return is_admin(user)


def can_delete_visits(user) -> bool:
    return is_admin(user)


def can_restore_visits(user) -> bool:
    return is_admin(user)


def can_manage_purposes(user) -> bool:
    return is_admin(user)


def can_manage_users(user) -> bool:
    return is_admin(user)


def can_view_audit(user) -> bool:
    return is_admin(user)


def can_use_django_admin(user) -> bool:
    return bool(
        is_admin(user)
        and getattr(user, "is_staff", False)
    )


def capabilities_for(user) -> dict[str, bool]:
    return {
        "staff": is_staff_member(user),
        "admin": is_admin(user),
        "view_full_history": can_view_full_history(user),
        "export_reports": can_export_reports(user),
        "delete_visits": can_delete_visits(user),
        "restore_visits": can_restore_visits(user),
        "manage_purposes": can_manage_purposes(user),
        "manage_users": can_manage_users(user),
        "view_audit": can_view_audit(user),
        "use_django_admin": can_use_django_admin(user),
    }
