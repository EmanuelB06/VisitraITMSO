from __future__ import annotations

from django.db import models
from django.db.models import Q

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

    objects = VisitorQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["visitor_type", "identifier"],
                condition=~Q(identifier=""),
                name="unique_visitor_identifier_per_type",
            )
        ]
        indexes = [models.Index(fields=["visitor_type", "name"])]

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
