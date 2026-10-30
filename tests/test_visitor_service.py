from __future__ import annotations

import pytest

from audit.models import ActivityLog
from visitors.exceptions import DuplicateVisitorError, InvalidVisitorError
from visitors.models import Visitor
from visitors.services import VisitorRegistration, VisitorService


def register(**overrides):
    data = {
        "visitor_type": Visitor.Type.STUDENT,
        "name": "Maria Santos",
        "identifier": "2024-00123",
    }
    data.update(overrides)
    return VisitorService().register(VisitorRegistration(**data))


@pytest.mark.django_db
def test_student_registration_is_normalised():
    visitor = register(
        name="  Maria Santos  ",
        identifier="  2024-00123 ",
        course="  BS Information Technology ",
    )

    assert visitor.name == "Maria Santos"
    assert visitor.identifier == "2024-00123"
    assert visitor.course == "BS Information Technology"
    assert visitor.student_type == Visitor.StudentType.COLLEGE
    assert visitor.is_active is True


@pytest.mark.django_db
def test_external_visitor_receives_generated_reference():
    visitor = register(
        visitor_type=Visitor.Type.EXTERNAL,
        name="Peter Parker",
        identifier="",
        organization="DepEd Batangas",
    )

    assert visitor.identifier.startswith("EXT-")
    assert len(visitor.identifier) == 10
    assert visitor.organization == "DepEd Batangas"


@pytest.mark.django_db
def test_duplicate_identifier_is_rejected_case_insensitively():
    register(identifier="2024-00123")

    with pytest.raises(DuplicateVisitorError):
        register(name="Another Student", identifier="2024-00123")

    with pytest.raises(DuplicateVisitorError):
        register(name="Another Student", identifier="2024-00123".lower())


@pytest.mark.django_db
def test_identifier_is_required_for_students_and_faculty():
    with pytest.raises(InvalidVisitorError):
        register(identifier="")

    with pytest.raises(InvalidVisitorError):
        register(
            visitor_type=Visitor.Type.FACULTY,
            name="No ID Faculty",
            identifier="",
        )


@pytest.mark.django_db
def test_name_is_required():
    with pytest.raises(InvalidVisitorError):
        register(name="   ")


@pytest.mark.django_db
def test_unknown_visitor_type_is_rejected():
    with pytest.raises(ValueError):
        register(visitor_type="ALIEN")


@pytest.mark.django_db
def test_fields_from_other_types_are_cleared():
    visitor = register(
        visitor_type=Visitor.Type.FACULTY,
        name="Dr. Juan Dela Cruz",
        identifier="EMP-2024-01",
        department="College of IT",
        course="BS IT",
        organization="Should be removed",
    )

    assert visitor.department == "College of IT"
    assert visitor.course == ""
    assert visitor.organization == ""


@pytest.mark.django_db
def test_registration_writes_an_activity_log(admin_user):
    visitor = VisitorService().register(
        VisitorRegistration(
            visitor_type=Visitor.Type.EXTERNAL,
            name="Peter Parker",
            organization="DepEd",
        ),
        actor=admin_user,
    )

    log = ActivityLog.objects.get(action=ActivityLog.Action.VISITOR_REGISTERED)
    assert log.actor == admin_user
    assert log.entity_id == str(visitor.pk)
    assert log.metadata["name"] == "Peter Parker"


@pytest.mark.django_db
def test_policy_detail_lines():
    student = register(
        course="BS Information Technology",
        year_level="2nd Year",
    )
    faculty = register(
        visitor_type=Visitor.Type.FACULTY,
        name="Dr. Juan Dela Cruz",
        identifier="EMP-2024-01",
        department="College of IT",
    )
    external = register(
        visitor_type=Visitor.Type.EXTERNAL,
        name="Peter Parker",
        identifier="",
        organization="DepEd",
    )

    assert student.detail_line == "BS Information Technology · 2nd Year"
    assert faculty.identifier_label == "Employee ID"
    assert faculty.detail_line == "College of IT"
    assert external.identifier_label == "Reference"
    assert external.detail_line == "DepEd"
