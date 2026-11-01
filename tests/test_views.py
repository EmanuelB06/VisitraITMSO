from __future__ import annotations

import json

import pytest
from django.urls import reverse

from audit.models import ActivityLog
from visits.models import Visit
from visits.services import VisitService
from visitors.models import Visitor

from .conftest import FixedClock, manila


@pytest.fixture
def visit(db, student, purpose):
    return VisitService().time_in(visitor=student, purpose=purpose)


def post_json(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


@pytest.mark.django_db
def test_home_and_login_are_public(client):
    assert client.get(reverse("home")).status_code == 200
    assert client.get(reverse("accounts:login")).status_code == 200


@pytest.mark.django_db
def test_health_endpoint(client):
    response = client.get(reverse("health"))
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_anonymous_users_are_redirected_to_login(client):
    for url in (reverse("visits:kiosk"), reverse("visitors:register"), reverse("reports:dashboard")):
        response = client.get(url)
        assert response.status_code == 302
        assert reverse("accounts:login") in response["Location"]


@pytest.mark.django_db
def test_login_accepts_username_and_email(client, staff_user):
    response = client.post(
        reverse("accounts:login"),
        {"username": "staff", "password": "Staff@12345"},
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(staff_user.pk)

    client.logout()

    response = client.post(
        reverse("accounts:login"),
        {"username": "staff@sbc.edu.ph", "password": "Staff@12345"},
    )
    assert response.status_code == 302
    assert client.session["_auth_user_id"] == str(staff_user.pk)


@pytest.mark.django_db
def test_login_sends_staff_to_kiosk(client, staff_user):
    response = client.post(
        reverse("accounts:login"),
        {"username": "staff", "password": "Staff@12345"},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("visits:kiosk")


@pytest.mark.django_db
def test_login_sends_admin_to_dashboard(client, admin_user):
    response = client.post(
        reverse("accounts:login"),
        {"username": "admin", "password": "Admin@12345"},
    )
    assert response.status_code == 302
    assert response["Location"] == reverse("reports:dashboard")


@pytest.mark.django_db
def test_login_next_overrides_role_destination(client, admin_user):
    target = reverse("visitors:register")
    response = client.post(
        f"{reverse('accounts:login')}?next={target}",
        {"username": "admin", "password": "Admin@12345"},
    )
    assert response.status_code == 302
    assert response["Location"] == target


@pytest.mark.django_db
def test_signed_in_users_are_redirected_by_role(client, staff_user):
    client.force_login(staff_user)
    response = client.get(reverse("accounts:login"))
    assert response.status_code == 302
    assert response["Location"] == reverse("visits:kiosk")


@pytest.mark.django_db
def test_login_rejects_bad_password(client, staff_user):
    response = client.post(
        reverse("accounts:login"),
        {"username": "staff", "password": "wrong"},
    )
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_kiosk_renders_and_sets_csrf_cookie(client, staff_user, purpose):
    client.force_login(staff_user)

    response = client.get(reverse("visits:kiosk"))

    assert response.status_code == 200
    assert "csrftoken" in response.cookies
    assert b"MS 365 Assistance" in response.content
    assert b"kiosk-bootstrap" in response.content


@pytest.mark.django_db
def test_kiosk_prefills_visitor_after_registration(client, staff_user, student):
    client.force_login(staff_user)

    response = client.get(reverse("visits:kiosk"), {"visitor": str(student.pk)})

    assert response.status_code == 200
    assert student.name.encode() in response.content


@pytest.mark.django_db
def test_lookup_returns_matching_students(client, staff_user, student, faculty):
    client.force_login(staff_user)

    response = client.get(reverse("visitors:lookup"), {"q": "Maria", "type": "STUDENT"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert [item["name"] for item in results] == ["Maria Santos"]
    assert results[0]["identifier_label"] == "Student ID"
    assert results[0]["active_visit"] is None


@pytest.mark.django_db
def test_lookup_filters_by_type(client, staff_user, student, faculty):
    client.force_login(staff_user)

    response = client.get(reverse("visitors:lookup"), {"q": "Juan", "type": "STUDENT"})
    assert response.json()["results"] == []

    response = client.get(reverse("visitors:lookup"), {"q": "Juan", "type": "FACULTY"})
    assert [item["name"] for item in response.json()["results"]] == ["Dr. Juan Dela Cruz"]


@pytest.mark.django_db
def test_lookup_requires_login(client, student):
    response = client.get(reverse("visitors:lookup"), {"q": "Maria"})
    assert response.status_code == 403


@pytest.mark.django_db
def test_lookup_returns_active_visit_details(client, staff_user, visit):
    client.force_login(staff_user)

    response = client.get(reverse("visitors:lookup"), {"q": "Maria"})

    active = response.json()["results"][0]["active_visit"]
    assert active["id"] == str(visit.pk)
    assert active["purpose"] == "MS 365 Assistance"
    assert active["time_out_url"].endswith(f"/{visit.pk}/time-out/")


@pytest.mark.django_db
def test_registration_creates_visitor_and_redirects(client, staff_user):
    client.force_login(staff_user)

    response = client.post(
        reverse("visitors:register"),
        {
            "visitor_type": "STUDENT",
            "name": "Ana Reyes",
            "identifier": "2024-00999",
            "student_type": "COLLEGE",
            "course": "BS Accountancy",
            "year_level": "1st Year",
            "consent": "on",
        },
    )

    assert response.status_code == 302
    visitor = Visitor.objects.get(identifier="2024-00999")
    assert response["Location"] == f"{reverse('visits:kiosk')}?visitor={visitor.pk}"
    assert visitor.student_type == Visitor.StudentType.COLLEGE


@pytest.mark.django_db
def test_registration_requires_consent_and_identifier(client, staff_user):
    client.force_login(staff_user)

    response = client.post(
        reverse("visitors:register"),
        {
            "visitor_type": "STUDENT",
            "name": "Ana Reyes",
            "identifier": "",
        },
    )

    assert response.status_code == 200
    assert b"Student ID is required" in response.content
    assert not Visitor.objects.filter(name="Ana Reyes").exists()


@pytest.mark.django_db
def test_duplicate_registration_shows_domain_error(client, staff_user, student):
    client.force_login(staff_user)

    response = client.post(
        reverse("visitors:register"),
        {
            "visitor_type": "STUDENT",
            "name": "Another Maria",
            "identifier": student.identifier,
            "student_type": "COLLEGE",
            "consent": "on",
        },
    )

    assert response.status_code == 200
    assert b"already registered" in response.content


@pytest.mark.django_db
def test_external_registration_generates_reference(client, staff_user):
    client.force_login(staff_user)

    response = client.post(
        reverse("visitors:register"),
        {
            "visitor_type": "EXTERNAL",
            "name": "Peter Parker",
            "organization": "DepEd",
            "consent": "on",
        },
    )

    assert response.status_code == 302
    visitor = Visitor.objects.get(name="Peter Parker")
    assert visitor.identifier.startswith("EXT-")


@pytest.mark.django_db
def test_time_in_and_time_out_api(client, staff_user, student, purpose):
    client.force_login(staff_user)

    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": str(student.pk), "purpose_id": str(purpose.pk), "custom_purpose": ""},
    )

    assert response.status_code == 201
    payload = response.json()["visit"]
    assert payload["visitor"]["name"] == "Maria Santos"
    assert payload["purpose"] == "MS 365 Assistance"
    assert payload["is_active"] is True

    response = client.post(payload["time_out_url"])
    assert response.status_code == 200
    assert response.json()["visit"]["is_active"] is False
    assert Visit.objects.completed().count() == 1


@pytest.mark.django_db
def test_time_in_api_validates_payload(client, staff_user, student, purpose):
    client.force_login(staff_user)

    response = client.post(
        reverse("visits:time-in"),
        data="{not json",
        content_type="application/json",
    )
    assert response.status_code == 400

    response = post_json(client, reverse("visits:time-in"), {})
    assert response.status_code == 400

    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": "00000000-0000-0000-0000-000000000000", "purpose_id": str(purpose.pk)},
    )
    assert response.status_code == 404

    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": str(student.pk), "purpose_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_time_in_api_requires_login(client, student, purpose):
    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": str(student.pk), "purpose_id": str(purpose.pk)},
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_time_in_api_reports_business_conflicts(client, staff_user, student, purpose, detailed_purpose):
    client.force_login(staff_user)

    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": str(student.pk), "purpose_id": str(detailed_purpose.pk), "custom_purpose": ""},
    )
    assert response.status_code == 409

    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": str(student.pk), "purpose_id": str(purpose.pk)},
    )
    assert response.status_code == 201

    response = post_json(
        client,
        reverse("visits:time-in"),
        {"visitor_id": str(student.pk), "purpose_id": str(purpose.pk)},
    )
    assert response.status_code == 409


@pytest.mark.django_db
def test_active_api_lists_open_visits(client, staff_user, visit):
    client.force_login(staff_user)

    response = client.get(reverse("visits:active"))

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["visits"]] == [str(visit.pk)]


@pytest.mark.django_db
def test_dashboard_is_readable_by_staff(client, staff_user, visit):
    client.force_login(staff_user)

    response = client.get(reverse("reports:dashboard"))

    assert response.status_code == 200
    assert b"Maria Santos" in response.content
    assert b"MS 365 Assistance" in response.content
    assert b"Export" not in response.content


@pytest.mark.django_db
def test_dashboard_filters(client, staff_user, visit, faculty, purpose):
    second = VisitService().time_in(visitor=faculty, purpose=purpose)
    VisitService().time_out(second)
    client.force_login(staff_user)

    response = client.get(reverse("reports:dashboard"), {"search": "Maria"})
    assert b"Maria Santos" in response.content
    assert b"Dr. Juan Dela Cruz" not in response.content

    response = client.get(reverse("reports:dashboard"), {"status": "DONE"})
    assert b"Dr. Juan Dela Cruz" in response.content
    assert b"Maria Santos" not in response.content

    response = client.get(reverse("reports:dashboard"), {"type": "FACULTY"})
    assert b"Dr. Juan Dela Cruz" in response.content
    assert b"Maria Santos" not in response.content


@pytest.mark.django_db
def test_staff_dashboard_is_limited_to_today(client, staff_user, admin_user, student, faculty, purpose):
    VisitService(clock=FixedClock(manila(2026, 3, 9, 9, 0))).time_in(
        visitor=student,
        purpose=purpose,
    )
    VisitService().time_in(visitor=faculty, purpose=purpose)

    client.force_login(staff_user)
    response = client.get(reverse("reports:dashboard"))
    assert b"Dr. Juan Dela Cruz" in response.content
    assert b"Maria Santos" not in response.content

    # Staff cannot request history through the date filters either.
    response = client.get(reverse("reports:dashboard"), {"date_from": "2000-01-01"})
    assert b"Dr. Juan Dela Cruz" in response.content
    assert b"Maria Santos" not in response.content

    client.force_login(admin_user)
    response = client.get(reverse("reports:dashboard"))
    assert b"Dr. Juan Dela Cruz" in response.content
    assert b"Maria Santos" in response.content


@pytest.mark.django_db
def test_admin_can_filter_history_by_date(client, admin_user, visit):
    client.force_login(admin_user)

    response = client.get(reverse("reports:dashboard"), {"date_from": "2999-01-01"})

    assert b"No records found" in response.content


@pytest.mark.django_db
def test_inactive_staff_cannot_use_kiosk_apis(client, staff_user, student, purpose):
    staff_user.is_active = False
    staff_user.save(update_fields=["is_active"])
    client.force_login(staff_user)

    assert client.get(reverse("visitors:lookup"), {"q": "Maria"}).status_code == 403
    assert client.get(reverse("visits:active")).status_code == 403
    assert (
        post_json(
            client,
            reverse("visits:time-in"),
            {"visitor_id": str(student.pk), "purpose_id": str(purpose.pk)},
        ).status_code
        == 403
    )


@pytest.mark.django_db
def test_staff_cannot_export_or_delete(client, staff_user, visit):
    client.force_login(staff_user)

    assert client.get(reverse("reports:export"), {"format": "csv"}).status_code == 403
    assert client.post(reverse("reports:delete", kwargs={"pk": visit.pk})).status_code == 403
    assert Visit.objects.visible().filter(pk=visit.pk).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("fmt", "content_type", "prefix"),
    (
        ("csv", "text/csv", b"\xef\xbb\xbf"),
        ("pdf", "application/pdf", b"%PDF"),
        ("xlsx", "application/vnd.openxmlformats", b"PK"),
    ),
)
def test_admin_exports(client, admin_user, visit, fmt, content_type, prefix):
    client.force_login(admin_user)

    response = client.get(reverse("reports:export"), {"format": fmt})
    body = b"".join(response.streaming_content)

    assert response.status_code == 200
    assert response["Content-Type"].startswith(content_type)
    assert body.startswith(prefix)
    entry = ActivityLog.objects.filter(action=ActivityLog.Action.EXPORT).first()
    assert entry is not None
    assert entry.metadata["format"] == fmt
    assert entry.metadata["count"] == 1


@pytest.mark.django_db
def test_unknown_export_format_returns_404(client, admin_user):
    client.force_login(admin_user)

    assert client.get(reverse("reports:export"), {"format": "docx"}).status_code == 404


@pytest.mark.django_db
def test_admin_can_soft_delete_visit(client, admin_user, visit):
    client.force_login(admin_user)

    response = client.post(reverse("reports:delete", kwargs={"pk": visit.pk}), {"query": "status=ALL"})

    assert response.status_code == 302
    assert "?status=ALL" in response["Location"]
    assert not Visit.objects.visible().filter(pk=visit.pk).exists()
    assert Visit.objects.filter(pk=visit.pk).exists()
    assert ActivityLog.objects.filter(action=ActivityLog.Action.VISIT_DELETED).exists()


@pytest.mark.django_db
def test_kiosk_ignores_invalid_visitor_prefill(client, admin_user):
    client.force_login(admin_user)

    response = client.get(reverse("visits:kiosk"), {"visitor": "not-a-uuid"})

    assert response.status_code == 200
    assert b"kiosk-bootstrap" in response.content
