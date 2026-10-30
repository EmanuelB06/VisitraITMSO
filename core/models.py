"""Reusable abstract models shared by every app."""

from __future__ import annotations

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Primary key that is safe to expose in URLs and exports."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
