"""Tests for visitor self-service registration and login."""

from __future__ import annotations

import pytest
from django.urls import reverse

from visitors.accounts import authenticate_visitor, register_visitor_account
from visitors.forms import VisitorLoginForm, VisitorSelfRegistrationForm
from visitors.models import Visitor
from visitors.services import VisitorRegistration

pytestmark = pytest.mark.django_db

PASSWORD = "Visitor@12345"


def registration_payload(**overrides):
    data = {
        "visitor_type": Visitor.Type.STUDENT,
        "name": "Maria Santos",
        "email": "maria@example.com",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
        "identifier": "2024-00123",
        "student_type": Visitor.StudentType.COLLEGE,
        "course": "BS Information Technology",
        "year_level": "2nd Year",
        "consent": True,
    }
    data.update(overrides)
    return data


def make_account(**overrides):
    payload = registration_payload(**overrides)
    form = VisitorSelfRegistrationForm(data=payload)
    assert form.is_valid(), form.errors
    return form.save()


def test_registration_form_creates_verified_visitor_with_hashed_password():
    visitor = make_account(email="Maria@Example.com")

    assert visitor.email == "maria@example.com"
    assert visitor.is_verified is True
    assert visitor.is_active is True
    assert visitor.has_login_credentials is True
    assert visitor.password_hash != PASSWORD
    assert visitor.check_password(PASSWORD) is True
    assert Visitor.objects.by_email("MARIA@example.com").get() == visitor


def test_registration_rejects_duplicate_email_case_insensitively():
    make_account()

    form = VisitorSelfRegistrationForm(
        data=registration_payload(identifier="2024-99999", email="MARIA@example.com")
    )

    assert form.is_valid() is False
    assert "email" in form.errors


def test_authenticate_visitor_reports_reasons():
    visitor = make_account()

    assert authenticate_visitor("maria@example.com", PASSWORD)[0] == visitor
    assert authenticate_visitor("maria@example.com", "wrong")[1] == "invalid"
    assert authenticate_visitor("nobody@example.com", PASSWORD)[1] == "invalid"

    visitor.is_active = False
    visitor.save(update_fields=["is_active"])
    assert authenticate_visitor("maria@example.com", PASSWORD)[1] == "inactive"


def test_login_form_requires_correct_password():
    make_account()

    form = VisitorLoginForm(data={"email": "maria@example.com", "password": PASSWORD})
    assert form.is_valid(), form.errors

    bad = VisitorLoginForm(data={"email": "maria@example.com", "password": "nope"})
    assert bad.is_valid() is False


def test_register_view_creates_and_signs_in_visitor(client):
    response = client.post(reverse("visitors:visitor_register"), registration_payload())

    assert response.status_code == 302
    assert response.url == reverse("visitors:dashboard")

    visitor = Visitor.objects.by_email("maria@example.com").get()
    session = client.session
    assert session["visitor_id"] == str(visitor.pk)

    dashboard = client.get(reverse("visitors:dashboard"))
    assert dashboard.status_code == 200
    assert "Maria Santos" in dashboard.content.decode()


def test_login_view_signs_visitor_in_and_respects_local_next(client):
    make_account()

    response = client.post(
        reverse("visitors:login"),
        {"email": "maria@example.com", "password": PASSWORD, "next": "/visitors/visitor-profile/"},
    )

    assert response.status_code == 302
    assert response.url == "/visitors/visitor-profile/"
    assert client.session["visitor_id"]


def test_login_view_ignores_external_next(client):
    make_account()

    response = client.post(
        reverse("visitors:login"),
        {
            "email": "maria@example.com",
            "password": PASSWORD,
            "next": "https://evil.example.com/phish",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("visitors:dashboard")


def test_dashboard_requires_login(client):
    response = client.get(reverse("visitors:dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("visitors:login"))


def test_logout_is_post_only_and_clears_session(client):
    make_account()
    client.post(
        reverse("visitors:login"),
        {"email": "maria@example.com", "password": PASSWORD},
    )

    assert client.get(reverse("visitors:logout")).status_code == 405

    response = client.post(reverse("visitors:logout"))
    assert response.status_code == 302
    assert response.url == reverse("home")
    assert "visitor_id" not in client.session


def test_profile_update_changes_email_and_session(client):
    visitor = make_account()
    client.post(
        reverse("visitors:login"),
        {"email": "maria@example.com", "password": PASSWORD},
    )

    response = client.post(
        reverse("visitors:profile"),
        {
            "name": "Maria S. Santos",
            "email": "maria.santos@example.com",
            "phone_number": "0917 000 0000",
            "identifier": visitor.identifier,
            "student_type": visitor.student_type,
            "course": visitor.course,
            "year_level": visitor.year_level,
            "department": "",
            "organization": "",
            "contact_number": "",
        },
    )

    assert response.status_code == 302
    visitor.refresh_from_db()
    assert visitor.name == "Maria S. Santos"
    assert visitor.email == "maria.santos@example.com"
    assert client.session["visitor_email"] == "maria.santos@example.com"


def test_password_change_updates_login_credentials(client):
    make_account()
    client.post(
        reverse("visitors:login"),
        {"email": "maria@example.com", "password": PASSWORD},
    )

    response = client.post(
        reverse("visitors:password_change"),
        {
            "current_password": PASSWORD,
            "new_password": "BrandNew@12345",
            "confirm_new_password": "BrandNew@12345",
        },
    )

    assert response.status_code == 302
    assert authenticate_visitor("maria@example.com", "BrandNew@12345")[0] is not None
    assert authenticate_visitor("maria@example.com", PASSWORD)[0] is None


def test_visitor_pages_render(client):
    for name in ("visitors:visitor_register", "visitors:login"):
        response = client.get(reverse(name))
        assert response.status_code == 200

    make_account()
    client.post(
        reverse("visitors:login"),
        {"email": "maria@example.com", "password": PASSWORD},
    )
    for name in ("visitors:dashboard", "visitors:profile", "visitors:password_change"):
        response = client.get(reverse(name))
        assert response.status_code == 200


def test_staff_login_page_offers_visitor_tab(client):
    response = client.get(reverse("accounts:login"))

    assert response.status_code == 200
    body = response.content.decode()
    assert reverse("visitors:login") in body
    assert reverse("visitors:visitor_register") in body


def test_staff_registration_still_works(client, admin_user):
    client.force_login(admin_user)

    response = client.post(
        reverse("visitors:register"),
        {
            "visitor_type": Visitor.Type.FACULTY,
            "name": "Dr. Juan Dela Cruz",
            "identifier": "EMP-2024-01",
            "department": "College of Information Technology",
            "consent": True,
        },
    )

    assert response.status_code == 302
    assert Visitor.objects.filter(identifier="EMP-2024-01").exists()


def test_account_service_records_activity(admin_user):
    visitor = register_visitor_account(
        VisitorRegistration(
            visitor_type=Visitor.Type.EXTERNAL,
            name="Walk In",
            organization="Supplier",
        ),
        email="walkin@example.com",
        password=PASSWORD,
        phone_number="0917 111 2222",
    )

    assert visitor.check_password(PASSWORD)
    assert visitor.is_verified is True
