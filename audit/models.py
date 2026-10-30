"""Append-only activity trail for sensitive operations."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import TimeStampedModel, UUIDModel


class ActivityLog(UUIDModel, TimeStampedModel):
    class Action(models.TextChoices):
        LOGIN = "LOGIN", "Signed in"
        LOGIN_FAILED = "LOGIN_FAILED", "Sign-in failed"
        VISITOR_REGISTERED = "VISITOR_REGISTERED", "Visitor registered"
        TIME_IN = "TIME_IN", "Time in"
        TIME_OUT = "TIME_OUT", "Time out"
        VISIT_DELETED = "VISIT_DELETED", "Visit deleted"
        EXPORT = "EXPORT", "Report exported"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    entity_type = models.CharField(max_length=40, blank=True)
    entity_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "activity log entry"
        verbose_name_plural = "activity log"

    def __str__(self) -> str:
        return f"{self.get_action_display()} · {self.created_at:%Y-%m-%d %H:%M}"

    @classmethod
    def record(cls, *, action: str, actor=None, entity_type: str = "", entity_id: str = "", **metadata):
        return cls.objects.create(
            actor=actor if getattr(actor, "pk", None) else None,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            metadata=metadata,
        )
