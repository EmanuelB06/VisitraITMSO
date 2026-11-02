"""Staff and administrator accounts.

Visitors are business records, not login accounts: only the people operating
the system (front desk and ITMSO administrators) authenticate here.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import TimeStampedModel, UUIDModel


class User(AbstractUser):
    """A staff or administrator account that can sign into Visitra ITMSO.

    Visitor records (the people processed at the front desk) live in a separate
    model and never authenticate here.
    """

    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        STAFF = "STAFF", "Front Desk Staff"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STAFF,
        help_text="Administrators can delete records and export reports.",
    )

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"
        constraints = [
            # Django's built-in username uniqueness is case-sensitive on some
            # databases. Login is case-insensitive, so the database must be too.
            models.UniqueConstraint(
                Lower("username"),
                name="unique_user_username_ci",
            ),
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="unique_user_email_ci",
            ),
        ]

    @property
    def is_admin_role(self) -> bool:
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    def __str__(self) -> str:
        return self.display_name


class ApiToken(UUIDModel, TimeStampedModel):
    """Scoped Bearer token for server-to-server API clients."""

    class Scope(models.TextChoices):
        PURPOSES_READ = "purposes:read", "Read purposes"
        VISITORS_READ = "visitors:read", "Read visitors"
        VISITORS_WRITE = "visitors:write", "Register visitors"
        VISITORS_BULK = "visitors:bulk", "Bulk import visitors"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="api_tokens",
    )
    name = models.CharField(max_length=120)
    key_prefix = models.CharField(max_length=16, unique=True)
    secret_hash = models.CharField(max_length=64)
    scopes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.key_prefix})"

    @staticmethod
    def hash_secret(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def issue(cls, *, name: str, owner, scopes, expires_at=None):
        valid = set(cls.Scope.values)
        unknown = sorted(set(scopes) - valid)
        if unknown:
            raise ValueError(f"Unknown API scope(s): {', '.join(unknown)}")

        prefix = secrets.token_hex(4)
        raw = f"visitra_{prefix}_{secrets.token_urlsafe(32)}"
        token = cls.objects.create(
            name=name,
            owner=owner,
            key_prefix=prefix,
            secret_hash=cls.hash_secret(raw),
            scopes=list(scopes),
            expires_at=expires_at,
        )
        return token, raw

    @property
    def is_expired(self) -> bool:
        return bool(self.expires_at and self.expires_at <= timezone.now())

    def clean(self):
        super().clean()
        unknown = sorted(set(self.scopes or []) - set(self.Scope.values))
        if unknown:
            raise ValidationError({"scopes": f"Unknown API scope(s): {', '.join(unknown)}"})

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])
