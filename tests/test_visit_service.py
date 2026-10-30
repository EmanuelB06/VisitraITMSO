from __future__ import annotations

from datetime import timedelta

import pytest

from audit.models import ActivityLog
from core.exceptions import DomainError
from visits.exceptions import (
    DuplicateVisitError,
    InvalidPurposeError,
    OpenVisitError,
    VisitAlreadyClosedError,
)
from visits.models import Purpose, Visit
from visits.services import VisitService
from visitors.models import Visitor
from visitors.services import VisitorRegistration, VisitorService

from .conftest import FixedClock, manila


@pytest.fixture
def clock():
    return FixedClock(manila(2026, 3, 10, 9, 0))


@pytest.fixture
def service(clock):
    return VisitService(clock=clock)


@pytest.fixture
def visitor(db):
    return VisitorService().register(
        VisitorRegistration(
            visitor_type=Visitor.Type.STUDENT,
            name="Maria Santos",
            identifier="2024-00123",
        )
    )


@pytest.fixture
def other_purpose(db):
    return Purpose.objects.create(name="ID Printing", sort_order=30)


@pytest.mark.django_db
def test_time_in_records_purpose_and_local_date(service, visitor, purpose, staff_user):
    visit = service.time_in(
        visitor=visitor,
        purpose=purpose,
        actor=staff_user,
    )

    assert visit.time_in == manila(2026, 3, 10, 9, 0)
    assert visit.visit_date.isoformat() == "2026-03-10"
    assert visit.purpose_text == "MS 365 Assistance"
    assert visit.logged_by == staff_user
    assert visit.is_active is True
    assert Visit.objects.active().filter(pk=visit.pk).exists()


@pytest.mark.django_db
def test_custom_purpose_is_required_when_configured(service, visitor, detailed_purpose):
    with pytest.raises(InvalidPurposeError):
        service.time_in(visitor=visitor, purpose=detailed_purpose)

    visit = service.time_in(
        visitor=visitor,
        purpose=detailed_purpose,
        custom_purpose="  Cannot open School Automate  ",
    )

    assert visit.purpose_text == "Cannot open School Automate"
    assert visit.custom_purpose == "Cannot open School Automate"


@pytest.mark.django_db
def test_custom_purpose_is_ignored_for_plain_purposes(service, visitor, purpose):
    visit = service.time_in(
        visitor=visitor,
        purpose=purpose,
        custom_purpose="unused detail",
    )

    assert visit.purpose_text == "MS 365 Assistance"
    assert visit.custom_purpose == ""


@pytest.mark.django_db
def test_same_purpose_twice_in_one_day_is_rejected(service, visitor, purpose):
    service.time_in(visitor=visitor, purpose=purpose)

    with pytest.raises(DuplicateVisitError):
        service.time_in(visitor=visitor, purpose=purpose)


@pytest.mark.django_db
def test_same_purpose_on_another_day_is_allowed(service, clock, visitor, purpose):
    first = service.time_in(visitor=visitor, purpose=purpose)
    clock.set(manila(2026, 3, 10, 9, 30))
    service.time_out(first)

    clock.set(manila(2026, 3, 11, 9, 0))
    visit = service.time_in(visitor=visitor, purpose=purpose)
    assert visit.visit_date.isoformat() == "2026-03-11"


@pytest.mark.django_db
def test_open_visit_blocks_a_second_visit(service, visitor, purpose, other_purpose):
    service.time_in(visitor=visitor, purpose=purpose)

    with pytest.raises(OpenVisitError):
        service.time_in(visitor=visitor, purpose=other_purpose)


@pytest.mark.django_db
def test_inactive_purpose_is_rejected(service, visitor, purpose):
    purpose.is_active = False
    purpose.save(update_fields=["is_active"])

    with pytest.raises(InvalidPurposeError):
        service.time_in(visitor=visitor, purpose=purpose)


@pytest.mark.django_db
def test_time_out_closes_the_visit(service, clock, visitor, purpose):
    visit = service.time_in(visitor=visitor, purpose=purpose)
    clock.set(manila(2026, 3, 10, 9, 45))

    closed = service.time_out(visit)

    assert closed.time_out == manila(2026, 3, 10, 9, 45)
    assert closed.is_active is False
    assert closed.duration_label == "45m"
    assert not Visit.objects.active().filter(pk=visit.pk).exists()


@pytest.mark.django_db
def test_time_out_before_time_in_is_rejected(service, clock, visitor, purpose):
    visit = service.time_in(visitor=visitor, purpose=purpose)
    clock.set(manila(2026, 3, 10, 8, 0))

    with pytest.raises(DomainError):
        service.time_out(visit)


@pytest.mark.django_db
def test_double_time_out_is_rejected(service, clock, visitor, purpose):
    visit = service.time_in(visitor=visitor, purpose=purpose)
    clock.set(manila(2026, 3, 10, 9, 30))
    service.time_out(visit)

    clock.set(manila(2026, 3, 10, 10, 0))
    with pytest.raises(VisitAlreadyClosedError):
        service.time_out(visit)


@pytest.mark.django_db
def test_soft_delete_hides_visit_and_cannot_be_timed_out(service, clock, visitor, purpose):
    visit = service.time_in(visitor=visitor, purpose=purpose)

    service.soft_delete(visit)

    assert not Visit.objects.visible().filter(pk=visit.pk).exists()
    assert Visit.objects.filter(pk=visit.pk).exists()
    assert visit.deleted_at is not None
    with pytest.raises(DomainError):
        service.time_out(visit)


@pytest.mark.django_db
def test_soft_delete_is_idempotent(service, clock, visitor, purpose):
    visit = service.time_in(visitor=visitor, purpose=purpose)
    service.soft_delete(visit)
    first = visit.deleted_at

    clock.set(manila(2026, 3, 10, 12, 0))
    service.soft_delete(visit)
    assert visit.deleted_at == first


@pytest.mark.django_db
def test_time_in_and_time_out_are_audited(service, clock, visitor, purpose, staff_user):
    visit = service.time_in(visitor=visitor, purpose=purpose, actor=staff_user)
    clock.set(manila(2026, 3, 10, 10, 0))
    service.time_out(visit, actor=staff_user)
    service.soft_delete(visit, actor=staff_user)

    actions = list(
        ActivityLog.objects.filter(entity_type="Visit")
        .order_by("created_at")
        .values_list("action", flat=True)
    )
    assert actions == [
        ActivityLog.Action.TIME_IN,
        ActivityLog.Action.TIME_OUT,
        ActivityLog.Action.VISIT_DELETED,
    ]


@pytest.mark.django_db
def test_duration_label_formats_hours(service, clock, visitor, purpose):
    visit = service.time_in(visitor=visitor, purpose=purpose)
    clock.set(visit.time_in + timedelta(hours=2, minutes=5))
    visit = service.time_out(visit)

    assert visit.duration_label == "2h 05m"
