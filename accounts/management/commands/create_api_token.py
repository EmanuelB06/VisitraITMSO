"""Issue a scoped API token and print the raw value exactly once."""

from __future__ import annotations

from datetime import datetime, time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from accounts.models import ApiToken
from accounts.permissions import is_admin, is_staff_member
from audit.services import record as record_activity

User = get_user_model()


def _parse_expires(value: str | None):
    if not value:
        return None

    moment = parse_datetime(value)
    if moment is None:
        day = parse_date(value)
        if day is None:
            raise CommandError("--expires must be an ISO date or datetime.")
        moment = datetime.combine(day, time.max)

    if timezone.is_naive(moment):
        moment = timezone.make_aware(moment)
    return moment


class Command(BaseCommand):
    help = "Create a scoped Bearer token for an external API client."

    def add_arguments(self, parser):
        parser.add_argument("--name", required=True, help="Human-readable token name.")
        parser.add_argument("--owner", required=True, help="Username the token acts as.")
        parser.add_argument(
            "--scopes",
            required=True,
            help=f"Comma-separated scopes: {', '.join(ApiToken.Scope.values)}",
        )
        parser.add_argument(
            "--expires",
            default=None,
            help="Optional ISO date/datetime after which the token stops working.",
        )

    def handle(self, *args, **options):
        owner = User.objects.filter(username__iexact=options["owner"].strip()).first()
        if owner is None:
            raise CommandError(f"User '{options['owner']}' was not found.")
        if not owner.is_active or not is_staff_member(owner):
            raise CommandError("The token owner must be an active staff or admin account.")

        scopes = [scope.strip() for scope in options["scopes"].split(",") if scope.strip()]
        if not scopes:
            raise CommandError("At least one scope is required.")
        unknown = sorted(set(scopes) - set(ApiToken.Scope.values))
        if unknown:
            raise CommandError(f"Unknown scope(s): {', '.join(unknown)}")
        if ApiToken.Scope.VISITORS_BULK in scopes and not is_admin(owner):
            raise CommandError("visitors:bulk requires an administrator owner.")

        token, raw = ApiToken.issue(
            name=options["name"].strip(),
            owner=owner,
            scopes=scopes,
            expires_at=_parse_expires(options["expires"]),
        )

        record_activity(
            action="API_TOKEN_CREATED",
            entity_type="ApiToken",
            entity_id=str(token.pk),
            name=token.name,
            owner=str(owner.pk),
            scopes=token.scopes,
        )

        self.stdout.write(self.style.SUCCESS(f"Created API token '{token.name}'."))
        self.stdout.write(f"Owner: {owner.username}")
        self.stdout.write(f"Scopes: {', '.join(token.scopes)}")
        self.stdout.write(self.style.WARNING("Store this token now; it cannot be shown again."))
        self.stdout.write(raw)
