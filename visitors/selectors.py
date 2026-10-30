"""Read-side queries for visitors.

The selector hides whether the answer comes from Firestore (system of record)
or the relational mirror, so views and serializers stay unchanged.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db.models import Prefetch

from core.firestore import is_enabled

from .models import Visitor
from .repository import VisitorRepository


class VisitorSelector:
    @staticmethod
    def lookup(term: str, visitor_type: str | None = None, limit: int = 8) -> list[Visitor]:
        term = (term or "").strip()
        if not term:
            return []

        if is_enabled():
            return VisitorRepository().lookup(term, visitor_type, limit)

        queryset = Visitor.objects.active().search(term)
        if visitor_type:
            queryset = queryset.of_type(visitor_type)

        # Import lazily: visits depends on visitors, so a module-level import
        # would create a cycle.
        from visits.models import Visit

        queryset = queryset.prefetch_related(
            Prefetch(
                "visits",
                queryset=Visit.objects.active().select_related("purpose"),
                to_attr="active_visits",
            )
        )
        return list(queryset[:limit])

    @staticmethod
    def find_by_identifier(identifier: str, visitor_type: str) -> Visitor | None:
        if is_enabled():
            return VisitorRepository().find_by_identifier(visitor_type, identifier)

        return (
            Visitor.objects.active()
            .filter(visitor_type=visitor_type, identifier__iexact=(identifier or "").strip())
            .first()
        )

    @staticmethod
    def get_by_id(visitor_id) -> Visitor | None:
        if not visitor_id:
            return None

        if is_enabled():
            record = VisitorRepository().get(visitor_id)
            return record if record and record.is_active else None

        try:
            return Visitor.objects.active().filter(pk=visitor_id).first()
        except (ValidationError, ValueError, TypeError):
            return None
