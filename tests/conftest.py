from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone

from visits.models import Purpose
from visitors.models import Visitor
from visitors.services import VisitorRegistration, VisitorService

User = get_user_model()
MANILA = ZoneInfo("Asia/Manila")


@pytest.fixture(autouse=True)
def clear_login_throttle_cache():
    """Keep failed-login counters from leaking between tests."""
    cache.clear()
    yield
    cache.clear()


class FixedClock:
    """Deterministic clock for service tests."""

    def __init__(self, moment):
        self.moment = moment

    def now(self):
        return self.moment

    def local_date(self, moment):
        return timezone.localdate(moment)

    def local(self, moment):
        return timezone.localtime(moment)

    def set(self, moment):
        self.moment = moment


def manila(year, month, day, hour=9, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=MANILA)


@pytest.fixture
def admin_user(db):
    return User.objects.create_user(
        username="admin",
        email="admin@sbc.edu.ph",
        password="Admin@12345",
        role=User.Role.ADMIN,
        is_superuser=True,
        is_staff=True,
        first_name="ITMSO",
        last_name="Administrator",
    )


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="staff",
        email="staff@sbc.edu.ph",
        password="Staff@12345",
        role=User.Role.STAFF,
    )


@pytest.fixture
def purpose(db):
    return Purpose.objects.create(name="MS 365 Assistance", sort_order=10)


@pytest.fixture
def detailed_purpose(db):
    return Purpose.objects.create(
        name="Other Concerns",
        requires_specification=True,
        sort_order=20,
    )


@pytest.fixture
def student(db):
    return VisitorService().register(
        VisitorRegistration(
            visitor_type=Visitor.Type.STUDENT,
            name="Maria Santos",
            identifier="2024-00123",
            student_type=Visitor.StudentType.COLLEGE,
            course="BS Information Technology",
            year_level="2nd Year",
        )
    )


@pytest.fixture
def faculty(db):
    return VisitorService().register(
        VisitorRegistration(
            visitor_type=Visitor.Type.FACULTY,
            name="Dr. Juan Dela Cruz",
            identifier="EMP-2024-01",
            department="College of Information Technology",
        )
    )
