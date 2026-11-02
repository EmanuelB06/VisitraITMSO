from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.contrib.auth.hashers import make_password, check_password

from core.models import TimeStampedModel, UUIDModel


class VisitorQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def of_type(self, visitor_type: str):
        return self.filter(visitor_type=visitor_type)

    def search(self, term: str):
        term = (term or "").strip()
        if not term:
            return self
        return self.filter(Q(name__icontains=term) | Q(identifier__icontains=term))

    def by_email(self, email: str):
        """Match an email address regardless of case (empty emails never match)."""
        email = (email or "").strip()
        if not email:
            return self.none()
        return self.filter(email__iexact=email)


class Visitor(UUIDModel, TimeStampedModel):
    """A person who visits the ITMSO office.

    One table holds every visitor type. Behaviour that varies per type lives in
    ``visitors.policies`` (strategy objects) so adding a new type does not
    require editing the visit service or the dashboard.
    """

    class Type(models.TextChoices):
        STUDENT = "STUDENT", "Student"
        FACULTY = "FACULTY", "Faculty"
        EXTERNAL = "EXTERNAL", "External"

    class StudentType(models.TextChoices):
        COLLEGE = "COLLEGE", "College"
        IBED = "IBED", "IBED"

    visitor_type = models.CharField(max_length=10, choices=Type.choices, db_index=True)
    name = models.CharField(max_length=120)
    identifier = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text="Student ID, employee ID, or generated external reference.",
    )

    # Student fields
    student_type = models.CharField(max_length=10, choices=StudentType.choices, blank=True)
    course = models.CharField(max_length=80, blank=True)
    year_level = models.CharField(max_length=40, blank=True)

    # Faculty fields
    department = models.CharField(max_length=120, blank=True)

    # External fields
    organization = models.CharField(max_length=120, blank=True)
    contact_number = models.CharField(max_length=30, blank=True)

    is_active = models.BooleanField(default=True)

    # NEW: Visitor login credentials
    email = models.EmailField(
        blank=True,
        db_index=True,
        help_text="Email address for visitor account login.",
    )
    password_hash = models.CharField(
        max_length=128,
        blank=True,
        help_text="Hashed password for visitor authentication.",
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        help_text="Phone number for verification and notifications.",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Whether the visitor has verified their email address.",
    )
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time this visitor logged in.",
    )

    objects = VisitorQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["visitor_type", "identifier"],
                condition=~Q(identifier=""),
                name="unique_visitor_identifier_per_type",
            ),
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="unique_visitor_email_ci",
            ),
        ]
        indexes = [
            models.Index(fields=["visitor_type", "name"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.identifier or 'external'})"

    @property
    def type_label(self) -> str:
        return self.get_visitor_type_display()

    @property
    def identifier_label(self) -> str:
        from .policies import get_policy

        return get_policy(self.visitor_type).identifier_label

    @property
    def detail_line(self) -> str:
        from .policies import get_policy

        return get_policy(self.visitor_type).detail_line(self)

    # NEW: Password management methods
    def set_password(self, raw_password: str) -> None:
        """Set the visitor's password."""
        if raw_password:
            self.password_hash = make_password(raw_password)
        else:
            self.password_hash = ""

    def check_password(self, raw_password: str) -> bool:
        """Check if the provided password matches the stored hash."""
        if not self.password_hash:
            return False
        return check_password(raw_password, self.password_hash)

    @property
    def has_login_credentials(self) -> bool:
        """Check if visitor has email and password set up."""
        return bool(self.email and self.password_hash)

    @property
    def can_login(self) -> bool:
        """Check if visitor can log in (has credentials, is active, and verified)."""
        return self.is_active and self.has_login_credentials and self.is_verified

    def record_login(self) -> None:
        """Update last login timestamp."""
        from django.utils import timezone
        
        self.last_login = timezone.now()
        self.save(update_fields=["last_login"])