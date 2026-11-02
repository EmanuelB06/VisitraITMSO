"""Web session authentication for self-registered visitors.

Visitors are *not* Django users: only staff and administrators use
``accounts.User``. A visitor's credentials therefore live on the relational
``Visitor`` row, because Django's auth/session tables cannot move to Firestore.

The visitor profile itself is still created through ``VisitorService.register``
so the audit trail, duplicate checks and the Firestore mirror behave exactly as
they do for staff-assisted registration. The credentials are attached to the
SQL row afterwards and are never written to Firestore.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .exceptions import DuplicateVisitorError, InvalidVisitorError
from .models import Visitor
from .services import VisitorRegistration, VisitorService

SESSION_VISITOR_KEY = "visitor_id"
SESSION_NAME_KEY = "visitor_name"
SESSION_EMAIL_KEY = "visitor_email"

REMEMBER_ME_SECONDS = 14 * 24 * 60 * 60  # two weeks

# ``authenticate_visitor`` failure reasons.
AUTH_INVALID = "invalid"
AUTH_INACTIVE = "inactive"
AUTH_UNVERIFIED = "unverified"


def register_visitor_account(
    registration: VisitorRegistration,
    *,
    email: str,
    password: str,
    phone_number: str = "",
) -> Visitor:
    """Create the visitor profile and attach self-service login credentials.

    Returns the relational row (which holds the hashed password). The profile
    record may have been created in Firestore first, so the relational row is
    fetched by primary key instead of being created twice.
    """
    email = (email or "").strip().lower()
    phone_number = (phone_number or "").strip()

    if not email:
        raise InvalidVisitorError("An email address is required.")
    if not password:
        raise InvalidVisitorError("A password is required.")

    # Checked here as well as in the form so bulk/API callers get a domain
    # error instead of an IntegrityError.
    if Visitor.objects.by_email(email).exists():
        raise DuplicateVisitorError(
            "A visitor account with that email address already exists."
        )

    visitor = VisitorService().register(registration)

    try:
        with transaction.atomic():
            return _attach_credentials(
                visitor,
                email=email,
                password=password,
                phone_number=phone_number,
            )
    except IntegrityError as exc:
        raise DuplicateVisitorError(
            "A visitor account with that email address already exists."
        ) from exc


def _attach_credentials(
    visitor,
    *,
    email: str,
    password: str,
    phone_number: str,
) -> Visitor:
    """Write credentials onto the relational visitor row.

    ``visitor`` is a ``Visitor`` when Firestore is disabled and a
    ``VisitorRecord`` when it is the system of record. Both expose the same
    profile attributes and ``pk``.
    """
    row = Visitor.objects.filter(pk=visitor.pk).first()

    if row is None:
        # The best-effort Firestore mirror did not write a row (for example a
        # locked SQLite file). Create it from the record so the visitor can
        # still sign in.
        row = Visitor(
            id=visitor.pk,
            visitor_type=visitor.visitor_type,
            name=visitor.name,
            identifier=visitor.identifier,
            student_type=visitor.student_type,
            course=visitor.course,
            year_level=visitor.year_level,
            department=visitor.department,
            organization=visitor.organization,
            contact_number=visitor.contact_number,
            is_active=getattr(visitor, "is_active", True),
        )

    row.email = email
    row.phone_number = phone_number or row.contact_number
    # There is no email-delivery flow in this project, so self-registered
    # accounts are usable immediately instead of being locked out forever.
    row.is_verified = True
    row.set_password(password)
    row.save()
    return row


def authenticate_visitor(email: str, password: str) -> tuple[Visitor | None, str]:
    """Return ``(visitor, reason)``; ``reason`` is empty on success."""
    visitor = Visitor.objects.by_email(email).first()

    if visitor is None or not visitor.check_password(password):
        return None, AUTH_INVALID
    if not visitor.is_active:
        return None, AUTH_INACTIVE
    if not visitor.is_verified:
        return None, AUTH_UNVERIFIED
    return visitor, ""


def login_visitor(request, visitor: Visitor, *, remember_me: bool = False) -> None:
    """Start a visitor session, cycling the key to prevent session fixation."""
    request.session.cycle_key()
    request.session[SESSION_VISITOR_KEY] = str(visitor.pk)
    request.session[SESSION_NAME_KEY] = visitor.name
    request.session[SESSION_EMAIL_KEY] = visitor.email
    request.session.set_expiry(REMEMBER_ME_SECONDS if remember_me else 0)
    visitor.record_login()


def clear_visitor_session(request) -> None:
    for key in (SESSION_VISITOR_KEY, SESSION_NAME_KEY, SESSION_EMAIL_KEY):
        request.session.pop(key, None)


def logout_visitor(request) -> None:
    """Drop the whole session (visitor keys, messages and CSRF token)."""
    request.session.flush()


def current_visitor(request) -> Visitor | None:
    """The signed-in visitor for this request, or ``None``.

    Inactive or deleted visitors are signed out lazily so a stale session
    cannot keep using the account.
    """
    visitor_id = request.session.get(SESSION_VISITOR_KEY)
    if not visitor_id:
        return None

    try:
        visitor = Visitor.objects.filter(pk=visitor_id).first()
    except (ValidationError, ValueError, TypeError):
        clear_visitor_session(request)
        return None

    if visitor is None or not visitor.is_active:
        clear_visitor_session(request)
        return None
    return visitor
