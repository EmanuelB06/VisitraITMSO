from __future__ import annotations

import json
import uuid

import pytest
from django.test import Client
from django.urls import reverse

from accounts.models import ApiToken
from audit.models import ActivityLog
from visitors.models import Visitor


def issue_token(owner, *scopes):
    return ApiToken.issue(name="test client", owner=owner, scopes=list(scopes))


def bearer(raw):
    return {"HTTP_AUTHORIZATION": f"Bearer {raw}"}


def post_json(client, url, payload, **extra):
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **extra,
    )


def registration_payload(**overrides):
    payload = {
        "visitor_type": "STUDENT",
        "name": "Maria Santos",
        "identifier": "2024-00123",
        "student_type": "COLLEGE",
        "course": "BS Information Technology",
        "year_level": "2nd Year",
        "consent": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_purposes_are_available_to_staff_and_scoped_tokens(client, staff_user, purpose):
    client.force_login(staff_user)
    response = client.get(reverse("api:purposes"))
    assert response.status_code == 200
    assert response.json()["purposes"][0]["name"] == purpose.name

    _, raw = issue_token(staff_user, ApiToken.Scope.PURPOSES_READ)
    response = client.get(reverse("api:purposes"), **bearer(raw))
    assert response.status_code == 200

    _, wrong_scope = issue_token(staff_user, ApiToken.Scope.VISITORS_READ)
    response = client.get(reverse("api:purposes"), **bearer(wrong_scope))
    assert response.status_code == 403


@pytest.mark.django_db
def test_anonymous_and_invalid_tokens_are_rejected(client):
    assert client.get(reverse("api:purposes")).status_code == 403

    response = client.get(reverse("api:purposes"), **bearer("visitra_bad_bad"))
    assert response.status_code == 401
    assert response["WWW-Authenticate"] == "Bearer"


@pytest.mark.django_db
def test_visitor_search_and_detail(client, staff_user, student):
    _, raw = issue_token(staff_user, ApiToken.Scope.VISITORS_READ)

    response = client.get(reverse("api:visitors"), {"q": "Maria"}, **bearer(raw))
    assert response.status_code == 200
    result = response.json()["results"][0]
    assert result["name"] == "Maria Santos"
    assert result["course"] == "BS Information Technology"

    response = client.get(
        reverse("api:visitor-detail", kwargs={"visitor_id": student.pk}),
        **bearer(raw),
    )
    assert response.status_code == 200
    assert response.json()["visitor"]["identifier"] == "2024-00123"

    response = client.get(
        reverse("api:visitor-detail", kwargs={"visitor_id": uuid.uuid4()}),
        **bearer(raw),
    )
    assert response.status_code == 404


@pytest.mark.django_db
def test_visitor_search_validates_parameters(client, staff_user):
    _, raw = issue_token(staff_user, ApiToken.Scope.VISITORS_READ)

    assert client.get(reverse("api:visitors"), **bearer(raw)).status_code == 400
    assert (
        client.get(reverse("api:visitors"), {"q": "x", "type": "NOPE"}, **bearer(raw)).status_code
        == 400
    )
    assert (
        client.get(reverse("api:visitors"), {"q": "x", "limit": "51"}, **bearer(raw)).status_code
        == 400
    )


@pytest.mark.django_db
def test_single_registration_uses_the_service_and_audit_trail(client, staff_user):
    _, raw = issue_token(staff_user, ApiToken.Scope.VISITORS_WRITE)

    response = post_json(client, reverse("api:visitors"), registration_payload(), **bearer(raw))

    assert response.status_code == 201
    assert response.json()["visitor"]["name"] == "Maria Santos"
    visitor = Visitor.objects.get(identifier="2024-00123")
    assert visitor.visitor_type == "STUDENT"
    assert ActivityLog.objects.filter(action="VISITOR_REGISTERED", actor=staff_user).exists()


@pytest.mark.django_db
def test_single_registration_requires_consent_and_rejects_duplicates(client, staff_user):
    _, raw = issue_token(staff_user, ApiToken.Scope.VISITORS_WRITE)
    url = reverse("api:visitors")

    response = post_json(
        client,
        url,
        registration_payload(consent=False),
        **bearer(raw),
    )
    assert response.status_code == 400

    response = post_json(client, url, registration_payload(), **bearer(raw))
    assert response.status_code == 201

    response = post_json(client, url, registration_payload(), **bearer(raw))
    assert response.status_code == 409


@pytest.mark.django_db
def test_session_writes_require_csrf_but_token_writes_do_not(client, staff_user):
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(staff_user)
    response = post_json(csrf_client, reverse("api:visitors"), registration_payload())
    assert response.status_code == 403

    _, raw = issue_token(staff_user, ApiToken.Scope.VISITORS_WRITE)
    response = post_json(client, reverse("api:visitors"), registration_payload(), **bearer(raw))
    assert response.status_code == 201


@pytest.mark.django_db
def test_bulk_import_is_idempotent_and_audited(client, admin_user):
    token, raw = issue_token(admin_user, ApiToken.Scope.VISITORS_BULK)
    assert token.has_scope(ApiToken.Scope.VISITORS_BULK)

    payload = {
        "source": "SIS",
        "mode": "upsert",
        "visitors": [
            {
                "visitor_type": "STUDENT",
                "name": "Maria Santos",
                "identifier": "2024-00123",
                "student_type": "COLLEGE",
                "course": "BS Information Technology",
                "year_level": "2nd Year",
            },
            {
                "visitor_type": "FACULTY",
                "name": "Dr. Juan Dela Cruz",
                "identifier": "EMP-2024-01",
                "department": "College of Information Technology",
            },
        ],
    }

    response = post_json(client, reverse("api:visitors-bulk"), payload, **bearer(raw))
    assert response.status_code == 200
    assert response.json()["created"] == 2

    response = post_json(client, reverse("api:visitors-bulk"), payload, **bearer(raw))
    assert response.status_code == 200
    assert response.json()["created"] == 0
    assert response.json()["skipped"] == 2

    assert Visitor.objects.count() == 2
    assert ActivityLog.objects.filter(action="VISITOR_IMPORTED", actor=admin_user).count() == 2


@pytest.mark.django_db
def test_bulk_import_reports_partial_failures_and_dry_runs(client, admin_user):
    _, raw = issue_token(admin_user, ApiToken.Scope.VISITORS_BULK)
    url = reverse("api:visitors-bulk")

    payload = {
        "source": "SIS",
        "mode": "dry_run",
        "visitors": [
            {
                "visitor_type": "STUDENT",
                "name": "Maria Santos",
                "identifier": "2024-00123",
            },
            {"visitor_type": "STUDENT", "identifier": "2024-99999"},
            {"visitor_type": "EXTERNAL", "name": "No Reference"},
        ],
    }

    response = post_json(client, url, payload, **bearer(raw))
    assert response.status_code == 207
    data = response.json()
    assert data["created"] == 1
    assert len(data["failed"]) == 2
    assert Visitor.objects.count() == 0
    assert not ActivityLog.objects.filter(action="VISITOR_IMPORTED").exists()


@pytest.mark.django_db
def test_bulk_import_requires_admin_and_respects_the_limit(client, staff_user, admin_user):
    _, staff_raw = issue_token(staff_user, ApiToken.Scope.VISITORS_BULK)
    response = post_json(
        client,
        reverse("api:visitors-bulk"),
        {"visitors": [{"visitor_type": "STUDENT", "name": "X", "identifier": "1"}]},
        **bearer(staff_raw),
    )
    assert response.status_code == 403

    _, admin_raw = issue_token(admin_user, ApiToken.Scope.VISITORS_BULK)
    rows = [
        {"visitor_type": "STUDENT", "name": "X", "identifier": str(index)}
        for index in range(501)
    ]
    response = post_json(
        client,
        reverse("api:visitors-bulk"),
        {"visitors": rows},
        **bearer(admin_raw),
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_bulk_import_updates_changed_profiles(client, admin_user):
    _, raw = issue_token(admin_user, ApiToken.Scope.VISITORS_BULK)
    url = reverse("api:visitors-bulk")

    row = {
        "visitor_type": "STUDENT",
        "name": "Maria Santos",
        "identifier": "2024-00123",
        "course": "BS Information Technology",
    }
    post_json(client, url, {"source": "SIS", "visitors": [row]}, **bearer(raw))

    row["course"] = "BS Computer Science"
    response = post_json(client, url, {"source": "SIS", "visitors": [row]}, **bearer(raw))

    assert response.status_code == 200
    assert response.json()["updated"] == 1
    assert Visitor.objects.get(identifier="2024-00123").course == "BS Computer Science"
