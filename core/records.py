"""Plain domain records returned by the Firestore repositories.

They expose the same read-only surface the templates, serializers and exporters
already use on the Django models (``pk``, ``type_label``, ``display_purpose``,
``duration_label`` ...), so views do not need to know which store answered.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone as dt_timezone

VISITOR_TYPE_LABELS = {
    "STUDENT": "Student",
    "FACULTY": "Faculty",
    "EXTERNAL": "External",
}

STUDENT_TYPE_LABELS = {
    "COLLEGE": "College",
    "IBED": "IBED",
}

VISITOR_TYPE_VALUES = tuple(VISITOR_TYPE_LABELS)
STUDENT_TYPE_VALUES = tuple(STUDENT_TYPE_LABELS)


def as_aware(value: datetime | None) -> datetime | None:
    """Firestore returns naive UTC datetimes; the app works with aware ones."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt_timezone.utc)
    return value


def as_date(value) -> date | None:
    if value is None or isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value))


@dataclass(frozen=True)
class VisitorRecord:
    id: str
    visitor_type: str
    name: str
    identifier: str = ""
    student_type: str = ""
    course: str = ""
    year_level: str = ""
    department: str = ""
    organization: str = ""
    contact_number: str = ""
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    active_visits: tuple = field(default=(), compare=False)

    @property
    def pk(self) -> str:
        return self.id

    @property
    def type_label(self) -> str:
        return VISITOR_TYPE_LABELS.get(self.visitor_type, self.visitor_type.title())

    def get_visitor_type_display(self) -> str:
        return self.type_label

    def get_student_type_display(self) -> str:
        return STUDENT_TYPE_LABELS.get(self.student_type, self.student_type.title())

    @property
    def identifier_label(self) -> str:
        from visitors.policies import get_policy

        return get_policy(self.visitor_type).identifier_label

    @property
    def detail_line(self) -> str:
        from visitors.policies import get_policy

        return get_policy(self.visitor_type).detail_line(self)

    def __str__(self) -> str:
        return f"{self.name} ({self.identifier or 'external'})"


@dataclass(frozen=True)
class PurposeRecord:
    id: str
    name: str
    requires_specification: bool = False
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def pk(self) -> str:
        return self.id

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class VisitRecord:
    id: str
    visitor: VisitorRecord
    purpose_id: str
    purpose_text: str
    time_in: datetime
    visit_date: date
    custom_purpose: str = ""
    time_out: datetime | None = None
    logged_by_id: str | None = None
    deleted_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def pk(self) -> str:
        return self.id

    @property
    def visitor_id(self) -> str:
        return self.visitor.id

    @property
    def display_purpose(self) -> str:
        return self.purpose_text or self.visitor.name

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

    def __str__(self) -> str:
        return f"{self.visitor.name} · {self.display_purpose}"


@dataclass(frozen=True)
class ActivityLogRecord:
    id: str
    action: str
    actor_id: str | None = None
    entity_type: str = ""
    entity_id: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime | None = None

    @property
    def pk(self) -> str:
        return self.id
