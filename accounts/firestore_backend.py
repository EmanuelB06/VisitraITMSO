"""Authentication backend using the Firestore users collection.

When ``FIRESTORE_ENABLED`` is off (tests, offline development) the backend
delegates to the original SQL backend so login keeps working unchanged.
"""

from __future__ import annotations

import logging

from django.contrib.auth.backends import BaseBackend

from accounts import firestore_users
from accounts.firestore_user import FirestoreUser
from core.firestore import is_enabled

logger = logging.getLogger(__name__)


class FirestoreAuthBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not is_enabled():
            return self._sql_backend().authenticate(
                request, username=username, password=password, **kwargs
            )

        if username is None:
            username = kwargs.get("username") or kwargs.get("email")
        if username is None or password is None:
            return None

        user_data = firestore_users.get_by_login(username)
        if not user_data:
            # Not migrated yet (or a stale SQL-only account): fall back to the
            # SQL mirror so existing logins keep working.
            return self._sql_backend().authenticate(
                request, username=username, password=password, **kwargs
            )

        if not firestore_users.check_password(user_data, password):
            return None

        if not user_data.get("is_active", True):
            return None

        return FirestoreUser(user_data)

    def get_user(self, user_id):
        if not is_enabled():
            return self._sql_backend().get_user(user_id)

        # Django passes the integer pk stored in the session here.
        user_data = firestore_users.get_by_sql_id(user_id)
        if not user_data:
            # Back-compat: older sessions stored the Firestore uid string.
            user_data = firestore_users.get_by_uid(str(user_id))
        if not user_data:
            # Account exists only in the SQL mirror: keep the session alive
            # with the mirror row.
            return self._sql_backend().get_user(user_id)
        if not user_data.get("is_active", True):
            return None
        return FirestoreUser(user_data)

    @staticmethod
    def _sql_backend():
        from accounts.backends import EmailOrUsernameBackend

        return EmailOrUsernameBackend()

    def has_perm(self, user_obj, perm, obj=None):
        if not user_obj or not user_obj.is_authenticated:
            return False
        if getattr(user_obj, "is_superuser", False):
            return True
        if getattr(user_obj, "is_admin_role", False):
            return True
        return False

    def has_module_perms(self, user_obj, app_label):
        if not user_obj or not user_obj.is_authenticated:
            return False
        if getattr(user_obj, "is_superuser", False):
            return True
        if getattr(user_obj, "is_admin_role", False):
            return True
        return False
