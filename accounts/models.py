"""Staff and administrator accounts.

Visitors are business records, not login accounts: only the people operating
the system (front desk and ITMSO administrators) authenticate here.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrator"
        STAFF = "STAFF", "Front Desk Staff"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.STAFF,
        help_text="Administrators can delete records and export reports.",
    )
    email = models.EmailField("email address", blank=True)

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
