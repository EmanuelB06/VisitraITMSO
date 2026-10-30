"""Lightweight, cache-backed login throttling.

Failed attempts are counted per client address *and* submitted identity. A
shared cache backend (Redis, Memcached, database) is required when more than one
worker process serves the site; the default in-process cache is enough for a
single front-desk server.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.core.cache import cache


def _identity(request, username: str) -> str:
    address = request.META.get("REMOTE_ADDR", "") if request is not None else ""
    return f"{address}\0{(username or '').strip().lower()}"


def _key(request, username: str) -> str:
    digest = hashlib.sha256(_identity(request, username).encode("utf-8")).hexdigest()
    return f"visitra:login-failures:{digest}"


def _max_attempts() -> int:
    return max(int(getattr(settings, "LOGIN_MAX_ATTEMPTS", 5)), 1)


def _lockout_seconds() -> int:
    return max(int(getattr(settings, "LOGIN_LOCKOUT_SECONDS", 900)), 1)


def failure_count(request, username: str) -> int:
    return int(cache.get(_key(request, username), 0) or 0)


def is_locked_out(request, username: str) -> bool:
    return failure_count(request, username) >= _max_attempts()


def register_failure(request, username: str) -> int:
    key = _key(request, username)
    count = failure_count(request, username) + 1
    cache.set(key, count, timeout=_lockout_seconds())
    return count


def clear_failures(request, username: str) -> None:
    cache.delete(_key(request, username))


def lockout_message() -> str:
    minutes = max(1, round(_lockout_seconds() / 60))
    return (
        "Too many failed sign-in attempts. "
        f"Try again in {minutes} minute{'s' if minutes != 1 else ''}."
    )
