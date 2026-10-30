"""Firestore-primary behaviour, exercised against the in-memory backend.

These tests prove that services/selectors/views read and write through the
document store when ``FIRESTORE_ENABLED`` is on, while the SQL mirror still
receives a copy.
"""

from __future__ import annotations

import os
import uuid

import pytest
from django.core.management import call_command
from django.urls import reverse

from audit.models import ActivityLog
from audit.repository import AuditRepository
from core.firestore import config, get_store, reset_store
from core.records import PurposeRecord
from core.store import StoreUnavailable
from visits.exceptions import DuplicateVisitError, OpenVisitError
from visits.models import Purpose, Visit
from visits.repository import PurposeRepository, VisitRepository
from visits.selectors import VisitSelector
from visits.services import VisitService
from visitors.exceptions import DuplicateVisitorError
from visitors.models import Visitor
from visitors.repository import VisitorRepository
from visitors.selectors import VisitorSelector
from visitors.services import VisitorRegistration, VisitorService

from .conftest import FixedClock, manila


@pytest.fixture
def firestore(settings):
    """Point the app at Firestore.

    Defaults to the in-memory store so the suite needs no network. Set
    ``FIRESTORE_TEST_BACKEND=firestore`` plus ``FIRESTORE_EMULATOR_HOST`` to run
    the very same tests against a real server (the Google emulator).
    """
    settings.FIRESTORE_ENABLED = True
    settings.FIRESTORE_BACKEND = os.getenv("FIRESTORE_TEST_BACKEND", "memory")
    settings.FIRESTORE_PROJECT = os.getenv("FIRESTORE_TEST_PROJECT", "demo-visitra")
    # A unique prefix per test keeps emulator runs isolated from each other.
    settings.FIRESTORE_COLLECTION_PREFIX = f"test{uuid.uuid4().hex[:8]}"
    reset_store()
    yield
    reset_store()


def register_student(name="Maria Santos", identifier="2024-00123"):
    return VisitorService().register(
        VisitorRegistration(
            visitor_type=Visitor.Type.STUDENT,
            name=name,
            identifier=identifier,
            student_type=Visitor.StudentType.COLLEGE,
            course="BS Information Technology",
            year_level="2nd Year",
        )
    )


@pytest.mark.django_db
def test_registration_writes_firestore_and_mirrors_sql(firestore):
    visitor = register_student()

    stored = VisitorRepository().get(visitor.pk)
    assert stored is not None
    assert stored.name == "Maria Santos"
    assert stored.type_label == "Student"
    assert stored.detail_line == "BS Information Technology · 2nd Year"

    # The SQL row is the backup copy, written with the same primary key.
    assert Visitor.objects.filter(pk=visitor.pk, name="Maria Santos").exists()


@pytest.mark.django_db
def test_duplicate_identifier_is_rejected_from_firestore(firestore):
    register_student()

    with pytest.raises(DuplicateVisitorError):
        register_student()


@pytest.mark.django_db
def test_store_failure_is_not_masked_as_a_duplicate(firestore, monkeypatch):
    def unavailable(self, record):
        raise StoreUnavailable("Firestore is offline.")

    monkeypatch.setattr(VisitorRepository, "create", unavailable)

    with pytest.raises(StoreUnavailable):
        register_student()


@pytest.mark.django_db
def test_firestore_writes_run_in_transactions(firestore, purpose, monkeypatch):
    store = get_store()
    original = store.run_transaction
    calls = {"count": 0}

    def counting_run(callback):
        calls["count"] += 1
        return original(callback)

    monkeypatch.setattr(store, "run_transaction", counting_run)

    visitor = register_student()
    VisitService().time_in(visitor=visitor, purpose=purpose)

    assert calls["count"] == 2


@pytest.mark.django_db
def test_failed_time_in_is_rolled_back(firestore, purpose, monkeypatch):
    visitor = register_student()
    original_save = VisitRepository.save

    def save_then_fail(self, record):
        original_save(self, record)
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(VisitRepository, "save", save_then_fail)

    with pytest.raises(RuntimeError):
        VisitService().time_in(visitor=visitor, purpose=purpose)

    assert VisitRepository().summary()["total"] == 0


@pytest.mark.django_db
def test_visitor_admin_change_is_mirrored_to_firestore(firestore, client, admin_user):
    visitor = register_student()
    client.force_login(admin_user)

    response = client.post(
        reverse("admin:visitors_visitor_change", args=[visitor.pk]),
        {
            "visitor_type": Visitor.Type.STUDENT,
            "name": "Maria Updated",
            "identifier": visitor.identifier,
            "is_active": "on",
            "student_type": Visitor.StudentType.COLLEGE,
            "course": "BS Information Technology",
            "year_level": "2nd Year",
            "department": "",
            "organization": "",
            "contact_number": "",
            "_save": "Save",
        },
    )

    assert response.status_code == 302
    assert VisitorRepository().get(visitor.pk).name == "Maria Updated"


@pytest.mark.django_db
def test_visitor_admin_delete_is_mirrored_to_firestore(firestore, client, admin_user):
    visitor = register_student()
    client.force_login(admin_user)

    response = client.post(
        reverse("admin:visitors_visitor_delete", args=[visitor.pk]),
        {"post": "yes"},
    )

    assert response.status_code == 302
    assert VisitorRepository().get(visitor.pk) is None
    assert not Visitor.objects.filter(pk=visitor.pk).exists()


@pytest.mark.django_db
def test_time_in_and_time_out_round_trip(firestore, purpose, staff_user):
    clock = FixedClock(manila(2026, 3, 10, 9, 0))
    service = VisitService(clock=clock)
    visitor = register_student()

    visit = service.time_in(visitor=visitor, purpose=purpose, actor=staff_user)
    stored = VisitRepository().get(visit.pk)
    assert stored is not None
    assert stored.is_active is True
    assert stored.display_purpose == "MS 365 Assistance"

    clock.set(manila(2026, 3, 10, 9, 45))
    closed = service.time_out(visit, actor=staff_user)

    assert closed.duration_label == "45m"
    assert VisitRepository().get(visit.pk).time_out == manila(2026, 3, 10, 9, 45)
    assert Visit.objects.get(pk=visit.pk).time_out == manila(2026, 3, 10, 9, 45)


@pytest.mark.django_db
def test_duplicate_and_open_rules_come_from_firestore(firestore, purpose):
    clock = FixedClock(manila(2026, 3, 10, 9, 0))
    service = VisitService(clock=clock)
    visitor = register_student()
    other = Purpose.objects.create(name="ID Printing", sort_order=30)

    service.time_in(visitor=visitor, purpose=purpose)

    with pytest.raises(DuplicateVisitError):
        service.time_in(visitor=visitor, purpose=purpose)

    with pytest.raises(OpenVisitError):
        service.time_in(visitor=visitor, purpose=other)


@pytest.mark.django_db
def test_soft_delete_hides_visit_in_both_stores(firestore, purpose):
    clock = FixedClock(manila(2026, 3, 10, 9, 0))
    service = VisitService(clock=clock)
    visitor = register_student()
    visit = service.time_in(visitor=visitor, purpose=purpose)

    service.soft_delete(visit)

    assert VisitRepository().get(visit.pk) is None
    assert Visit.objects.get(pk=visit.pk).deleted_at is not None


@pytest.mark.django_db
def test_dashboard_reads_firestore(firestore, client, staff_user, purpose):
    visitor = register_student()
    VisitService().time_in(visitor=visitor, purpose=purpose)

    client.force_login(staff_user)
    response = client.get(reverse("reports:dashboard"))

    assert response.status_code == 200
    assert b"Maria Santos" in response.content
    assert b"Export" not in response.content
    assert VisitSelector.summary()["active"] == 1


@pytest.mark.django_db
def test_delete_view_soft_deletes_firestore(firestore, client, admin_user, purpose):
    visitor = register_student()
    visit = VisitService().time_in(visitor=visitor, purpose=purpose)

    client.force_login(admin_user)
    response = client.post(reverse("reports:delete", kwargs={"pk": visit.pk}))

    assert response.status_code == 302
    assert VisitRepository().get(visit.pk) is None


@pytest.mark.django_db
def test_lookup_attaches_the_active_visit(firestore, purpose):
    visitor = register_student()
    visit = VisitService().time_in(visitor=visitor, purpose=purpose)

    results = VisitorSelector.lookup("maria")

    assert [record.pk for record in results] == [visitor.pk]
    assert results[0].active_visits[0].pk == visit.pk
    assert results[0].active_visits[0].display_purpose == "MS 365 Assistance"


@pytest.mark.django_db
def test_kiosk_bootstrap_uses_firestore_purposes(firestore, client, staff_user):
    purpose = Purpose.objects.create(name="Canva Registration", sort_order=30)
    PurposeRepository().save(
        PurposeRecord(
            id=str(purpose.pk),
            name=purpose.name,
            requires_specification=purpose.requires_specification,
            is_active=purpose.is_active,
            sort_order=purpose.sort_order,
        )
    )

    client.force_login(staff_user)
    response = client.get(reverse("visits:kiosk"))

    assert response.status_code == 200
    assert b"Canva Registration" in response.content


@pytest.mark.django_db
def test_sync_command_backfills_firestore_from_sql(firestore):
    purpose = Purpose.objects.create(name="MS 365 Assistance", sort_order=10)
    visitor = Visitor.objects.create(
        visitor_type=Visitor.Type.FACULTY,
        name="Dr. Juan Dela Cruz",
        identifier="EMP-2024-01",
    )

    call_command("sync_firestore", "--direction=to-firestore", verbosity=0)

    assert PurposeRepository().get(purpose.pk).name == "MS 365 Assistance"
    assert VisitorRepository().get(visitor.pk).name == "Dr. Juan Dela Cruz"


@pytest.mark.django_db
def test_sync_command_rebuilds_the_sql_backup(firestore):
    purpose = Purpose.objects.create(name="MS 365 Assistance", sort_order=10)
    visitor = register_student()
    visit = VisitService().time_in(visitor=visitor, purpose=purpose)

    Visit.objects.filter(pk=visit.pk).delete()
    assert not Visit.objects.filter(pk=visit.pk).exists()

    call_command("sync_firestore", "--direction=to-sql", verbosity=0)

    assert Visit.objects.filter(pk=visit.pk).exists()


@pytest.mark.django_db
def test_health_reports_firestore_ok(firestore, client):
    response = client.get(reverse("health"))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["firestore"]["ok"] is True
    assert body["firestore"]["backend"] == config().backend


@pytest.mark.django_db
def test_health_reports_503_when_firestore_is_unreachable(settings, client):
    settings.FIRESTORE_ENABLED = True
    settings.FIRESTORE_BACKEND = "not-a-real-backend"
    reset_store()

    response = client.get(reverse("health"))

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["firestore"]["ok"] is False


@pytest.mark.django_db
def test_health_stays_plain_when_firestore_is_disabled(settings, client):
    settings.FIRESTORE_ENABLED = False

    response = client.get(reverse("health"))

    assert response.status_code == 200
    assert "firestore" not in response.json()


@pytest.mark.django_db
def test_check_firestore_reports_memory_backend(firestore):
    call_command("check_firestore", verbosity=0)


@pytest.mark.django_db
def test_activity_trail_is_written_to_firestore(firestore, purpose, staff_user):
    visitor = register_student()
    VisitService().time_in(visitor=visitor, purpose=purpose, actor=staff_user)

    actions = [entry.action for entry in AuditRepository().list()]

    assert "VISITOR_REGISTERED" in actions
    assert "TIME_IN" in actions
    # The SQL mirror keeps the same entries for backup/admin browsing.
    assert ActivityLog.objects.filter(action=ActivityLog.Action.TIME_IN).exists()


@pytest.mark.django_db
def test_export_activity_metadata_stays_flat(firestore, client, admin_user, purpose):
    visitor = register_student()
    VisitService().time_in(visitor=visitor, purpose=purpose)

    client.force_login(admin_user)
    response = client.get(reverse("reports:export"), {"format": "csv"})
    assert response.status_code == 200

    entry = ActivityLog.objects.filter(action=ActivityLog.Action.EXPORT).first()
    assert entry is not None
    assert entry.metadata["format"] == "csv"
    assert "metadata" not in entry.metadata

    stored = AuditRepository().list(action="EXPORT")
    assert stored[0].metadata["format"] == "csv"

