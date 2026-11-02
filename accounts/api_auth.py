"""Bearer-token authentication for the versioned JSON API."""

from __future__ import annotations

import hmac
from functools import wraps

from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect

from core.api import json_error

from .models import ApiToken
from .permissions import is_admin, is_staff_member

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})


def bearer_token(request) -> str | None:
    header = request.META.get("HTTP_AUTHORIZATION", "")
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    credentials = credentials.strip()
    return credentials or None


def authenticate_token(raw: str) -> ApiToken | None:
    parts = raw.split("_", 2)
    if len(parts) != 3 or parts[0] != "visitra":
        return None

    prefix, secret = parts[1], parts[2]
    if not prefix or not secret:
        return None

    token = (
        ApiToken.objects.select_related("owner")
        .filter(key_prefix=prefix, is_active=True)
        .first()
    )
    if token is None:
        return None
    if not hmac.compare_digest(token.secret_hash, ApiToken.hash_secret(raw)):
        return None
    if token.is_expired or not token.owner.is_active:
        return None

    ApiToken.objects.filter(pk=token.pk).update(last_used_at=timezone.now())
    return token


def api_auth_required(scope: str, *, require_admin: bool = False):
    """Allow a scoped Bearer token or a signed-in staff session.

    Token requests are CSRF-exempt because they do not use cookies. Session
    writes go through Django's CSRF protection.
    """

    def decorator(view):
        csrf_view = csrf_protect(view)

        @wraps(view)
        def wrapper(request, *args, **kwargs):
            raw = bearer_token(request)
            if raw is not None:
                token = authenticate_token(raw)
                if token is None:
                    response = json_error("Invalid or expired API token.", status=401)
                    response["WWW-Authenticate"] = "Bearer"
                    return response
                if require_admin and not is_admin(token.owner):
                    return json_error("Admin access required.", status=403)
                if not is_staff_member(token.owner):
                    return json_error("Staff access required.", status=403)
                if not token.has_scope(scope):
                    return json_error(f"Missing scope: {scope}.", status=403)
                request.api_token = token
                request.user = token.owner
                return view(request, *args, **kwargs)

            if not getattr(request.user, "is_authenticated", False):
                return json_error("Authentication required.", status=403)
            if require_admin and not is_admin(request.user):
                return json_error("Admin access required.", status=403)
            if not is_staff_member(request.user):
                return json_error("Staff access required.", status=403)
            if request.method not in SAFE_METHODS:
                return csrf_view(request, *args, **kwargs)
            return view(request, *args, **kwargs)

        return csrf_exempt(wrapper)

    return decorator
