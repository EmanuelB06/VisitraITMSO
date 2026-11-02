"""Expose the signed-in visitor account to server-rendered templates."""

from __future__ import annotations

from .accounts import current_visitor


def visitor_account(request):
    return {"visitor_account": current_visitor(request)}
