"""Read-side filtering for visits and purposes, shared by the dashboard and exports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from core.firestore import is_enabled
from visitors.models import Visitor

from .models import Purpose, Visit
from .repository import PurposeRepository, VisitRepository


@dataclass(frozen=True)
class VisitFilter:
    search: str = ""
    date_from: date | None = None
    date_to: date | None = None
    status: str = "ALL"
    visitor_type: str = "ALL"

    STATUS_CHOICES = (("ALL", "All statuses"), ("ACTIVE", "Active"), ("DONE", "Done"))
    TYPE_CHOICES = (("ALL", "All types"),) + tuple(Visitor.Type.choices)

    @staticmethod
    def _parse_date(value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    @classmethod
    def from_query(cls, query) -> "VisitFilter":
        status = (query.get("status") or "ALL").upper()
        visitor_type = (query.get("type") or "ALL").upper()
        return cls(
            search=(query.get("search") or "").strip()[:100],
            date_from=cls._parse_date(query.get("date_from")),
            date_to=cls._parse_date(query.get("date_to")),
            status=status if status in dict(cls.STATUS_CHOICES) else "ALL",
            visitor_type=visitor_type if visitor_type in dict(cls.TYPE_CHOICES) else "ALL",
        )

    def as_query(self) -> str:
        params = {}
        if self.search:
            params["search"] = self.search
        if self.date_from:
            params["date_from"] = self.date_from.isoformat()
        if self.date_to:
            params["date_to"] = self.date_to.isoformat()
        if self.status != "ALL":
            params["status"] = self.status
        if self.visitor_type != "ALL":
            params["type"] = self.visitor_type
        return urlencode(params)

    @property
    def is_filtered(self) -> bool:
        return bool(self.search or self.date_from or self.date_to or self.status != "ALL" or self.visitor_type != "ALL")


class VisitSelector:
    @staticmethod
    def apply(filters: VisitFilter):
        if is_enabled():
            return VisitRepository().query(filters)

        queryset = Visit.objects.visible().select_related("visitor", "purpose", "logged_by")

        if filters.search:
            queryset = queryset.filter(
                Q(visitor__name__icontains=filters.search)
                | Q(visitor__identifier__icontains=filters.search)
                | Q(purpose_text__icontains=filters.search)
            )
        queryset = queryset.for_date_range(filters.date_from, filters.date_to)

        if filters.status == "ACTIVE":
            queryset = queryset.filter(time_out__isnull=True)
        elif filters.status == "DONE":
            queryset = queryset.filter(time_out__isnull=False)
        if filters.visitor_type != "ALL":
            queryset = queryset.filter(visitor__visitor_type=filters.visitor_type)

        return queryset.order_by("-time_in")

    @staticmethod
    def get_visible(visit_id):
        if not visit_id:
            return None

        if is_enabled():
            return VisitRepository().get(visit_id)

        try:
            return (
                Visit.objects.visible()
                .select_related("visitor", "purpose")
                .filter(pk=visit_id)
                .first()
            )
        except (ValidationError, ValueError, TypeError):
            return None

    @staticmethod
    def active(limit: int = 50):
        if is_enabled():
            return VisitRepository().active(limit)

        return list(
            Visit.objects.active()
            .select_related("visitor", "purpose")
            .order_by("-time_in")[:limit]
        )

    @staticmethod
    def summary(*, date_from: date | None = None, date_to: date | None = None) -> dict:
        if is_enabled():
            return VisitRepository().summary(date_from=date_from, date_to=date_to)

        aggregates = (
            Visit.objects.visible()
            .for_date_range(date_from, date_to)
            .aggregate(
                total=Count("id"),
                active=Count("id", filter=Q(time_out__isnull=True)),
                done=Count("id", filter=Q(time_out__isnull=False)),
            )
        )
        return {
            "total": aggregates["total"] or 0,
            "active": aggregates["active"] or 0,
            "done": aggregates["done"] or 0,
        }


class PurposeSelector:
    @staticmethod
    def list_active():
        if is_enabled():
            return PurposeRepository().list_active()

        return list(Purpose.objects.filter(is_active=True))

    @staticmethod
    def get_active(purpose_id):
        if not purpose_id:
            return None

        if is_enabled():
            return PurposeRepository().get_active(purpose_id)

        try:
            return Purpose.objects.filter(pk=purpose_id, is_active=True).first()
        except (ValidationError, ValueError, TypeError):
            return None
