"""Expose capabilities to server-rendered templates."""

from __future__ import annotations

from .permissions import capabilities_for


def visitra_capabilities(request):
    user = getattr(request, "user", None)
    return {"caps": capabilities_for(user)}
