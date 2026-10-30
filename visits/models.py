from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import TimeStampedModel, UUIDModel
from visitors.models import Visitor


class Purpose(UUIDModel, TimeStampedModel):
    name = models.CharField(max_length=80, unique=True)
    requires_specification = models.BooleanField(
        default=False,
        help_text="Show an extra 'specify concern' field for this purpose.",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class VisitQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(deleted_at__isnull=True)

    def active(self):
        return self.visible().filter(time_out__isnull=True)

    def completed(self):
        return self.visible().filter(time_out__isnull=False)

    def for_visitor(self, visitor):
        return self.filter(visitor=visitor)

    def for_date_range(self, start=None, end=None):
        queryset = self
        if start:
            queryset = queryset.filter(visit_date__gte=start)
        if end:
            queryset = queryset.filter(visit_date__lte=end)
        return queryset


class Visit(UUIDModel, TimeStampedModel):
    visitor = models.ForeignKey(Visitor, on_delete=models.PROTECT, related_name="visits")
    purpose = models.ForeignKey(Purpose, on_delete=models.PROTECT, related_name="visits")
    custom_purpose = models.CharField(max_length=200, blank=True)
    purpose_text = models.CharField(
        max_length=200,
        editable=False,
        help_text="Effective purpose at the time of the visit (kept for audit).",
    )
    time_in = models.DateTimeField()
    time_out = models.DateTimeField(null=True, blank=True)
    visit_date = models.DateField(db_index=True)
    logged_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="logged_visits",
    )
    deleted_at = models.DateTimeField(null=True, blank=True)

    objects = VisitQuerySet.as_manager()

    class Meta:
        ordering = ["-time_in"]
        constraints = [
            models.CheckConstraint(
                condition=Q(time_out__isnull=True) | Q(time_out__gt=models.F("time_in")),
                name="visit_time_out_after_time_in",
            ),
            models.UniqueConstraint(
                fields=["visitor", "purpose_text", "visit_date"],
                condition=Q(deleted_at__isnull=True),
                name="unique_visit_per_purpose_per_day",
            ),
            models.UniqueConstraint(
                fields=["visitor"],
                condition=Q(time_out__isnull=True) & Q(deleted_at__isnull=True),
                name="unique_active_visit_per_visitor",
            ),
        ]
        indexes = [
            models.Index(fields=["visit_date", "time_out"]),
            models.Index(fields=["visitor", "visit_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.visitor.name} · {self.display_purpose}"

    def save(self, *args, **kwargs):
        if not self.purpose_text and self.purpose_id:
            self.purpose_text = (self.custom_purpose or self.purpose.name).strip()
        if not self.visit_date and self.time_in:
            self.visit_date = timezone.localdate(self.time_in)
        super().save(*args, **kwargs)

    @property
    def display_purpose(self) -> str:
        return self.purpose_text or self.purpose.name

    @property
    def is_active(self) -> bool:
        return self.time_out is None and self.deleted_at is None

    @property
    def status_label(self) -> str:
        return "Active" if self.is_active else "Done"

    @property
    def duration(self) -> timedelta | None:
        if self.time_out is None:
            return None
        return self.time_out - self.time_in

    @property
    def duration_label(self) -> str:
        if self.time_out is None:
            return "In progress"
        minutes = max(int(self.duration.total_seconds() // 60), 0)
        hours, remainder = divmod(minutes, 60)
        if hours:
            return f"{hours}h {remainder:02d}m"
        return f"{remainder}m"
