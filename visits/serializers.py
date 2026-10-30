"""JSON representation of a visit for the kiosk."""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone


def format_moment(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%b %d, %Y %I:%M %p")


def visit_payload(visit) -> dict:
    return {
        "id": str(visit.pk),
        "visitor": {
            "id": str(visit.visitor_id),
            "name": visit.visitor.name,
            "identifier": visit.visitor.identifier,
            "visitor_type": visit.visitor.visitor_type,
            "type_label": visit.visitor.type_label,
        },
        "purpose": visit.display_purpose,
        "time_in": format_moment(visit.time_in),
        "time_out": format_moment(visit.time_out),
        "is_active": visit.is_active,
        "duration": visit.duration_label,
        "time_out_url": reverse("visits:time-out", kwargs={"pk": visit.pk}),
    }
