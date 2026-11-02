from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from accounts.api_auth import authenticate_token
from accounts.models import ApiToken


@pytest.mark.django_db
def test_issue_token_stores_only_a_hash(staff_user):
    token, raw = ApiToken.issue(
        name="Directory reader",
        owner=staff_user,
        scopes=[ApiToken.Scope.VISITORS_READ],
    )

    assert raw.startswith("visitra_")
    assert token.secret_hash != raw
    assert token.has_scope(ApiToken.Scope.VISITORS_READ)
    assert authenticate_token(raw).pk == token.pk


@pytest.mark.django_db
def test_invalid_token_value_is_rejected(staff_user):
    token, raw = ApiToken.issue(
        name="Directory reader",
        owner=staff_user,
        scopes=[ApiToken.Scope.VISITORS_READ],
    )

    assert authenticate_token("not-a-token") is None
    assert authenticate_token(f"{raw}x") is None
    assert ApiToken.objects.filter(pk=token.pk).exists()


@pytest.mark.django_db
def test_expired_revoked_and_inactive_owner_tokens_are_rejected(staff_user):
    expired, raw_expired = ApiToken.issue(
        name="Expired",
        owner=staff_user,
        scopes=[ApiToken.Scope.VISITORS_READ],
        expires_at=timezone.now() - timedelta(minutes=1),
    )
    assert authenticate_token(raw_expired) is None

    revoked, raw_revoked = ApiToken.issue(
        name="Revoked",
        owner=staff_user,
        scopes=[ApiToken.Scope.VISITORS_READ],
    )
    revoked.is_active = False
    revoked.save(update_fields=["is_active"])
    assert authenticate_token(raw_revoked) is None

    _, raw_inactive = ApiToken.issue(
        name="Inactive owner",
        owner=staff_user,
        scopes=[ApiToken.Scope.VISITORS_READ],
    )
    staff_user.is_active = False
    staff_user.save(update_fields=["is_active"])
    assert authenticate_token(raw_inactive) is None


@pytest.mark.django_db
def test_create_api_token_command_prints_the_raw_token_once(admin_user):
    stdout = StringIO()
    call_command(
        "create_api_token",
        name="SIS sync",
        owner="admin",
        scopes="visitors:read,visitors:bulk",
        stdout=stdout,
    )

    output = stdout.getvalue()
    assert "visitra_" in output
    assert ApiToken.objects.filter(name="SIS sync", owner=admin_user).exists()


@pytest.mark.django_db
def test_create_api_token_command_requires_an_admin_for_bulk(staff_user):
    with pytest.raises(CommandError):
        call_command(
            "create_api_token",
            name="Staff bulk",
            owner="staff",
            scopes="visitors:bulk",
        )
