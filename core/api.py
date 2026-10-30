"""Small helpers for JSON endpoints (keeps API concerns out of views)."""

from __future__ import annotations

import json
from functools import wraps

from django.http import JsonResponse


def json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"error": message}, status=status)


def api_login_required(view):
    """Like ``login_required`` but returns JSON 403 instead of a redirect."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_error("Authentication required.", status=403)
        return view(request, *args, **kwargs)

    return wrapper


def parse_json_body(request) -> dict | None:
    try:
        payload = json.loads(request.body or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def first_form_error(form) -> str:
    for errors in form.errors.values():
        if errors:
            return str(errors[0])
    return "Please check the submitted values."
