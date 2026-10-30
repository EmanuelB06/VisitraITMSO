"""Per-visitor-type strategy objects.

Each policy encapsulates the type-specific rules (which fields are required,
what the identifier is called, and how the profile reads in the UI). New
visitor types can be added by implementing ``VisitorPolicy`` and registering it
in ``POLICIES`` — no changes to services or templates.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class VisitorPolicy(ABC):
    visitor_type: str
    identifier_label: str
    required_fields: tuple[str, ...] = ()

    def missing_fields(self, data: dict) -> list[str]:
        missing = []
        for field in self.required_fields:
            if not str(data.get(field) or "").strip():
                missing.append(field)
        return missing

    @abstractmethod
    def detail_line(self, visitor) -> str:
        """Short human-readable subtitle (course/year, department, ...)."""


class StudentPolicy(VisitorPolicy):
    visitor_type = "STUDENT"
    identifier_label = "Student ID"
    required_fields = ("name", "identifier")

    def detail_line(self, visitor) -> str:
        parts = [part for part in (visitor.course, visitor.year_level) if part]
        if parts:
            return " · ".join(parts)
        return visitor.get_student_type_display() or "Student"


class FacultyPolicy(VisitorPolicy):
    visitor_type = "FACULTY"
    identifier_label = "Employee ID"
    required_fields = ("name", "identifier")

    def detail_line(self, visitor) -> str:
        return visitor.department or "Faculty"


class ExternalPolicy(VisitorPolicy):
    visitor_type = "EXTERNAL"
    identifier_label = "Reference"
    required_fields = ("name",)

    def detail_line(self, visitor) -> str:
        return visitor.organization or "External visitor"


POLICIES: dict[str, VisitorPolicy] = {
    policy.visitor_type: policy
    for policy in (StudentPolicy(), FacultyPolicy(), ExternalPolicy())
}


def get_policy(visitor_type: str) -> VisitorPolicy:
    try:
        return POLICIES[visitor_type]
    except KeyError as exc:
        raise ValueError(f"Unknown visitor type: {visitor_type}") from exc
