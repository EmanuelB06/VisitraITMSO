from __future__ import annotations

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse

from accounts.admin import UserAdmin
from audit.models import ActivityLog

User = get_user_model()


@pytest.mark.django_db
def test_username_uniqueness_is_case_insensitive():
    User.objects.create_user(
        username="staff",
        email="staff@example.com",
        password="Staff@12345",
    )

    with pytest.raises(IntegrityError):
        User.objects.create_user(
            username="STAFF",
            email="other@example.com",
            password="Staff@12345",
        )


@pytest.mark.django_db
def test_email_uniqueness_is_case_insensitive():
    User.objects.create_user(
        username="staff",
        email="staff@example.com",
        password="Staff@12345",
    )

    with pytest.raises(IntegrityError):
        User.objects.create_user(
            username="other",
            email="STAFF@EXAMPLE.COM",
            password="Staff@12345",
        )


@pytest.mark.django_db
def test_ambiguous_username_or_email_login_is_rejected(client):
    User.objects.create_user(
        username="shared",
        email="first@example.com",
        password="First@12345",
    )
    User.objects.create_user(
        username="second",
        email="shared",
        password="Second@12345",
    )

    response = client.post(
        reverse("accounts:login"),
        {"username": "shared", "password": "First@12345"},
    )

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


@pytest.mark.django_db
def test_repeated_failures_lock_out_even_a_correct_password(client, staff_user, settings):
    settings.LOGIN_MAX_ATTEMPTS = 3
    settings.LOGIN_LOCKOUT_SECONDS = 300
    url = reverse("accounts:login")

    for _ in range(3):
        response = client.post(url, {"username": "staff", "password": "wrong"})
        assert response.status_code == 200

    response = client.post(url, {"username": "staff", "password": "Staff@12345"})

    assert response.status_code == 200
    assert "_auth_user_id" not in client.session
    assert b"Too many failed sign-in attempts" in response.content


@pytest.mark.django_db
def test_successful_and_failed_logins_are_audited(client, staff_user):
    url = reverse("accounts:login")

    client.post(url, {"username": "staff", "password": "wrong"})
    assert ActivityLog.objects.filter(action=ActivityLog.Action.LOGIN_FAILED).exists()

    client.post(url, {"username": "staff", "password": "Staff@12345"})
    assert ActivityLog.objects.filter(action=ActivityLog.Action.LOGIN).exists()


@pytest.mark.django_db
def test_admin_nav_requires_staff_status(client):
    user = User.objects.create_user(
        username="roleadmin",
        email="roleadmin@example.com",
        password="Admin@12345",
        role=User.Role.ADMIN,
        is_staff=False,
    )

    client.force_login(user)
    response = client.get(reverse("home"))
    assert reverse("admin:index").encode() not in response.content

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    response = client.get(reverse("home"))
    assert reverse("admin:index").encode() in response.content


@pytest.mark.django_db
def test_user_admin_grants_staff_status_to_an_admin_role():
    model_admin = UserAdmin(User, django_admin.site)
    user = User(username="newadmin", email="newadmin@example.com", role=User.Role.ADMIN)

    model_admin.save_model(None, user, None, False)
    user.refresh_from_db()

    assert user.is_staff is True
