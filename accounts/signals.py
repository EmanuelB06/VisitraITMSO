"""Record authentication events in the activity trail."""

from __future__ import annotations

from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver

from audit.services import record as record_activity


def _client_address(request) -> str:
    if request is None:
        return ""
    return request.META.get("REMOTE_ADDR", "")


@receiver(user_logged_in)
def record_successful_login(sender, request, user, **kwargs):
    record_activity(
        actor=user,
        action="LOGIN",
        entity_type="User",
        entity_id=str(user.pk),
        ip=_client_address(request),
    )


@receiver(user_login_failed)
def record_failed_login(sender, credentials, request=None, **kwargs):
    identifier = str(
        credentials.get("username") or credentials.get("email") or ""
    ).strip()[:150]
    record_activity(
        action="LOGIN_FAILED",
        entity_type="User",
        identifier=identifier,
        ip=_client_address(request),
    )
