"""JSON representations shared by the lookup API and the kiosk bootstrap."""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone


def _format_moment(value) -> str:
    if not value:
        return ""
    return timezone.localtime(value).strftime("%b %d, %Y %I:%M %p")


def active_visit_brief(visitor):
    visits = getattr(visitor, "active_visits", None)
    if visits is None:
        visits = list(visitor.visits.active().select_related("purpose")[:1])
    visit = visits[0] if visits else None
    if visit is None:
        return None
    return {
        "id": str(visit.pk),
        "purpose": visit.display_purpose,
        "time_in": _format_moment(visit.time_in),
        "time_out_url": reverse("visits:time-out", kwargs={"pk": visit.pk}),
    }


def visitor_payload(visitor) -> dict:
    active = active_visit_brief(visitor)
    return {
        "id": str(visitor.pk),
        "name": visitor.name,
        "identifier": visitor.identifier,
        "visitor_type": visitor.visitor_type,
        "type_label": visitor.type_label,
        "identifier_label": visitor.identifier_label,
        "detail": visitor.detail_line,
        "active_visit": active,
    }
