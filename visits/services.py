"""Visit logging use cases (time in / time out / soft delete).

Firestore is the system of record when enabled; every write is mirrored to the
relational database as a backup.
"""

from __future__ import annotations

import uuid
from dataclasses import replace

from django.db import IntegrityError, transaction

from audit.services import record as record_activity
from core.clock import Clock
from core.exceptions import DomainError
from core.firestore import get_store, is_enabled
from core.mirror import mirror
from core.records import VisitRecord

from .exceptions import (
    DuplicateVisitError,
    InvalidPurposeError,
    OpenVisitError,
    VisitAlreadyClosedError,
)
from .models import Purpose, Visit
from .repository import VisitRepository


class VisitService:
    def __init__(self, clock: Clock | None = None):
        self.clock = clock or Clock()

    def time_in(
        self,
        *,
        visitor,
        purpose,
        custom_purpose: str = "",
        actor=None,
    ):
        if not purpose.is_active:
            raise InvalidPurposeError("That purpose is no longer available.")

        custom_purpose = (custom_purpose or "").strip()
        if purpose.requires_specification:
            if not custom_purpose:
                raise InvalidPurposeError("Please specify the concern.")
            purpose_text = custom_purpose
        else:
            purpose_text = purpose.name

        if is_enabled():
            return self._time_in_firestore(
                visitor=visitor,
                purpose=purpose,
                custom_purpose=custom_purpose,
                purpose_text=purpose_text,
                actor=actor,
            )
        return self._time_in_orm(
            visitor=visitor,
            purpose=purpose,
            custom_purpose=custom_purpose,
            purpose_text=purpose_text,
            actor=actor,
        )

    # -- Firestore (system of record) -------------------------------------

    def _time_in_firestore(
        self,
        *,
        visitor,
        purpose,
        custom_purpose: str,
        purpose_text: str,
        actor,
    ):
        visitor_id = str(visitor.pk)

        now = self.clock.now()
        visit_date = self.clock.local_date(now)

        record = VisitRecord(
            id=str(uuid.uuid4()),
            visitor=visitor,
            purpose_id=str(purpose.pk),
            purpose_text=purpose_text,
            custom_purpose=custom_purpose if purpose.requires_specification else "",
            time_in=now,
            visit_date=visit_date,
            logged_by_id=str(actor.pk) if getattr(actor, "pk", None) else None,
            created_at=now,
            updated_at=now,
        )

        def write(store):
            repository = VisitRepository(store)

            # The checks and the write share one transaction so two operators
            # cannot create conflicting visits from a stale read.
            if repository.find_duplicate(visitor_id, purpose_text, visit_date) is not None:
                raise DuplicateVisitError(
                    "This visitor already logged the same purpose today."
                )

            if repository.find_open(visitor_id) is not None:
                raise OpenVisitError(
                    "This visitor still has an active visit. Time it out before starting a new one."
                )

            repository.save(record)

        get_store().run_transaction(write)

        mirror("visit", lambda: self._mirror(record))
        record_activity(
            actor=actor,
            action="TIME_IN",
            entity_type="Visit",
            entity_id=record.id,
            visitor=visitor_id,
            purpose=record.display_purpose,
        )
        return record

    @staticmethod
    def _mirror(record: VisitRecord) -> None:
        Visit.objects.update_or_create(
            id=record.id,
            defaults={
                "visitor_id": record.visitor.id,
                "purpose_id": record.purpose_id,
                "custom_purpose": record.custom_purpose,
                "purpose_text": record.purpose_text,
                "time_in": record.time_in,
                "time_out": record.time_out,
                "visit_date": record.visit_date,
                "logged_by_id": record.logged_by_id,
                "deleted_at": record.deleted_at,
            },
        )

    # -- Relational (default / backup) ------------------------------------

    @transaction.atomic
    def _time_in_orm(
        self,
        *,
        visitor,
        purpose: Purpose,
        custom_purpose: str,
        purpose_text: str,
        actor,
    ) -> Visit:
        now = self.clock.now()
        visit_date = self.clock.local_date(now)

        if Visit.objects.visible().filter(
            visitor=visitor,
            purpose_text=purpose_text,
            visit_date=visit_date,
        ).exists():
            raise DuplicateVisitError(
                "This visitor already logged the same purpose today."
            )

        if Visit.objects.active().filter(visitor=visitor).exists():
            raise OpenVisitError(
                "This visitor still has an active visit. Time it out before starting a new one."
            )

        try:
            visit = Visit.objects.create(
                visitor=visitor,
                purpose=purpose,
                custom_purpose=custom_purpose if purpose.requires_specification else "",
                purpose_text=purpose_text,
                time_in=now,
                visit_date=visit_date,
                logged_by=actor if getattr(actor, "pk", None) else None,
            )
        except IntegrityError as exc:
            # Covers a race between the checks above and the database
            # constraints (two operators submitting at the same time).
            raise DuplicateVisitError(
                "This visit conflicts with a record that was just created. Refresh and try again."
            ) from exc

        record_activity(
            actor=actor,
            action="TIME_IN",
            entity_type="Visit",
            entity_id=str(visit.pk),
            visitor=str(visitor.pk),
            purpose=visit.display_purpose,
        )
        return visit

    def time_out(self, visit, *, actor=None):
        if is_enabled():
            return self._time_out_firestore(visit, actor=actor)
        return self._time_out_orm(visit, actor=actor)

    def _time_out_firestore(self, visit, *, actor):
        now = self.clock.now()

        def write(store):
            repository = VisitRepository(store)
            current = repository.get(visit.pk)
            if current is None:
                raise DomainError("This visit is no longer available.")
            if current.time_out is not None:
                raise VisitAlreadyClosedError("This visit has already been timed out.")
            if now <= current.time_in:
                raise DomainError("Time out must be later than time in.")

            updated = replace(current, time_out=now, updated_at=now)
            repository.save(updated)
            return updated

        updated = get_store().run_transaction(write)

        mirror("visit", lambda: self._mirror(updated))
        record_activity(
            actor=actor,
            action="TIME_OUT",
            entity_type="Visit",
            entity_id=updated.id,
            visitor=updated.visitor_id,
            purpose=updated.display_purpose,
        )
        return updated

    @transaction.atomic
    def _time_out_orm(self, visit: Visit, *, actor) -> Visit:
        locked = Visit.objects.select_for_update().filter(pk=visit.pk).first()
        if locked is None or locked.deleted_at is not None:
            raise DomainError("This visit is no longer available.")
        if locked.time_out is not None:
            raise VisitAlreadyClosedError("This visit has already been timed out.")

        now = self.clock.now()
        if now <= locked.time_in:
            raise DomainError("Time out must be later than time in.")

        locked.time_out = now
        locked.save(update_fields=["time_out", "updated_at"])

        record_activity(
            actor=actor,
            action="TIME_OUT",
            entity_type="Visit",
            entity_id=str(locked.pk),
            visitor=str(locked.visitor_id),
            purpose=locked.display_purpose,
        )
        return locked

    def soft_delete(self, visit, *, actor=None):
        if is_enabled():
            return self._soft_delete_firestore(visit, actor=actor)
        return self._soft_delete_orm(visit, actor=actor)

    def _soft_delete_firestore(self, visit, *, actor):
        now = self.clock.now()

        def write(store):
            repository = VisitRepository(store)
            current = repository.get(visit.pk)
            if current is None:
                return None, False
            if current.deleted_at is not None:
                return current, False

            updated = replace(current, deleted_at=now)
            repository.save(updated)
            return updated, True

        updated, changed = get_store().run_transaction(write)
        if updated is None:
            return visit
        if not changed:
            return updated

        mirror("visit", lambda: self._mirror(updated))
        record_activity(
            actor=actor,
            action="VISIT_DELETED",
            entity_type="Visit",
            entity_id=updated.id,
            visitor=updated.visitor_id,
            purpose=updated.display_purpose,
        )
        return updated

    @transaction.atomic
    def _soft_delete_orm(self, visit: Visit, *, actor) -> Visit:
        if visit.deleted_at is not None:
            return visit
        visit.deleted_at = self.clock.now()
        visit.save(update_fields=["deleted_at", "updated_at"])
        record_activity(
            actor=actor,
            action="VISIT_DELETED",
            entity_type="Visit",
            entity_id=str(visit.pk),
            visitor=str(visit.visitor_id),
            purpose=visit.display_purpose,
        )
        return visit
