"""Bridge helpers between Firestore auth users and the SQL mirror rows.

The SQL models keep ``logged_by`` / ``actor`` foreign keys pointing at
``accounts.User``. Those columns are mirror-only references, so when a
Firestore-backed user (``FirestoreUser``) triggers a write we resolve the
matching mirror row instead of assigning a non-model object to the FK.
"""

from __future__ import annotations

from typing import Any


def sql_user(actor: Any):
    """Return the SQL ``accounts.User`` mirror row for ``actor``, if any.

    Accepts either a real ``accounts.User`` instance (returned unchanged) or a
    Firestore-backed user object exposing an integer ``pk`` that matches the
    mirror row id. Returns ``None`` when there is no mirror row.
    """
    if actor is None:
        return None
    pk = getattr(actor, "pk", None)
    if not pk:
        return None
    try:
        pk = int(pk)
    except (TypeError, ValueError):
        return None

    from django.contrib.auth import get_user_model

    User = get_user_model()
    if isinstance(actor, User):
        return actor
    try:
        return User.objects.filter(pk=pk).first()
    except Exception:
        return None
