"""Visitor registration use case.

Firestore is the system of record when enabled; the SQL row is a backup copy.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, replace

from django.db import IntegrityError, transaction

from audit.services import record as record_activity
from core.clock import Clock
from core.firestore import get_store, is_enabled
from core.mirror import mirror
from core.records import VisitorRecord
from core.store import DocumentExists

from .exceptions import DuplicateVisitorError, InvalidVisitorError
from .models import Visitor
from .policies import get_policy
from .repository import VisitorRepository


@dataclass(frozen=True)
class VisitorRegistration:
    """Input DTO for registering a visitor (validated by the form first)."""

    visitor_type: str
    name: str
    identifier: str = ""
    student_type: str = ""
    course: str = ""
    year_level: str = ""
    department: str = ""
    organization: str = ""
    contact_number: str = ""


@dataclass(frozen=True)
class VisitorSyncResult:
    visitor: object | None
    created: bool = False
    updated: bool = False
    skipped: bool = False
    dry_run: bool = False
    changed_fields: tuple[str, ...] = ()


SYNC_FIELDS = (
    "name",
    "student_type",
    "course",
    "year_level",
    "department",
    "organization",
    "contact_number",
)


class VisitorService:
    def __init__(self, clock: Clock | None = None):
        self.clock = clock or Clock()

    def _validate(self, registration: VisitorRegistration):
        registration = self._normalise(registration)
        policy = get_policy(registration.visitor_type)

        data = asdict(registration)
        missing = policy.missing_fields(data)
        if missing:
            label = "Name" if "name" in missing else policy.identifier_label
            raise InvalidVisitorError(f"{label} is required for a {policy.visitor_type.lower()} visitor.")

        return registration, policy

    def register(self, registration: VisitorRegistration, *, actor=None) -> Visitor:
        registration, policy = self._validate(registration)

        if is_enabled():
            return self._register_firestore(registration, policy, actor)
        return self._register_orm(registration, policy, actor)

    def sync(
        self,
        registration: VisitorRegistration,
        *,
        actor=None,
        mode: str = "upsert",
        source: str = "api",
        require_identifier: bool = False,
        audit: bool = True,
    ) -> VisitorSyncResult:
        if mode not in {"upsert", "create_only", "dry_run"}:
            raise InvalidVisitorError("Unknown sync mode.")
        if require_identifier and not (registration.identifier or "").strip():
            raise InvalidVisitorError("An identifier is required for bulk import.")

        registration, policy = self._validate(registration)

        if is_enabled():
            return self._sync_firestore(
                registration,
                actor=actor,
                mode=mode,
                source=source,
                audit=audit,
            )
        return self._sync_orm(
            registration,
            policy=policy,
            actor=actor,
            mode=mode,
            source=source,
            audit=audit,
        )

    @staticmethod
    def _changed_fields(existing, registration) -> tuple[str, ...]:
        return tuple(
            field
            for field in SYNC_FIELDS
            if getattr(existing, field, "") != getattr(registration, field)
        )

    def _audit_sync(self, *, actor, visitor, action, changed, source):
        record_activity(
            action=action,
            actor=actor,
            entity_type="Visitor",
            entity_id=str(visitor.pk),
            visitor_type=visitor.visitor_type,
            name=visitor.name,
            identifier=visitor.identifier,
            source=source,
            changed_fields=list(changed),
        )

    # -- Firestore (system of record) -------------------------------------

    def _sync_firestore(self, registration, *, actor, mode, source, audit):
        repository = VisitorRepository()

        if mode == "dry_run":
            existing = repository.find_by_identifier(
                registration.visitor_type, registration.identifier
            )
            if existing is None:
                return VisitorSyncResult(visitor=None, created=True, dry_run=True)
            changed = self._changed_fields(existing, registration)
            return VisitorSyncResult(
                visitor=existing,
                updated=bool(changed),
                skipped=not changed,
                dry_run=True,
                changed_fields=changed,
            )

        def write(store):
            store_repository = VisitorRepository(store)
            existing = store_repository.find_by_identifier(
                registration.visitor_type, registration.identifier
            )
            if existing is not None:
                if mode == "create_only":
                    return existing, "skipped", ()
                changed = self._changed_fields(existing, registration)
                if not changed:
                    return existing, "skipped", ()
                updated = replace(
                    existing,
                    **{field: getattr(registration, field) for field in changed},
                    updated_at=self.clock.now(),
                )
                store_repository.save(updated)
                return updated, "updated", changed

            now = self.clock.now()
            record = VisitorRecord(
                id=str(uuid.uuid4()),
                visitor_type=registration.visitor_type,
                name=registration.name,
                identifier=registration.identifier,
                student_type=registration.student_type,
                course=registration.course,
                year_level=registration.year_level,
                department=registration.department,
                organization=registration.organization,
                contact_number=registration.contact_number,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            store_repository.create(record)
            return record, "created", ()

        try:
            visitor, status, changed = get_store().run_transaction(write)
        except DocumentExists as exc:
            raise DuplicateVisitorError(
                f"'{registration.identifier}' is already registered."
            ) from exc

        if status == "skipped":
            return VisitorSyncResult(visitor=visitor, skipped=True)

        mirror("visitor", lambda: self._mirror(visitor))
        if audit:
            action = "VISITOR_REGISTERED" if status == "created" else "VISITOR_UPDATED"
            self._audit_sync(
                actor=actor,
                visitor=visitor,
                action=action,
                changed=changed,
                source=source,
            )

        return VisitorSyncResult(
            visitor=visitor,
            created=status == "created",
            updated=status == "updated",
            changed_fields=changed,
        )

    def _register_firestore(self, registration: VisitorRegistration, policy, actor):
        now = self.clock.now()
        record = VisitorRecord(
            id=str(uuid.uuid4()),
            visitor_type=registration.visitor_type,
            name=registration.name,
            identifier=registration.identifier,
            student_type=registration.student_type,
            course=registration.course,
            year_level=registration.year_level,
            department=registration.department,
            organization=registration.organization,
            contact_number=registration.contact_number,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        def write(store):
            repository = VisitorRepository(store)
            if registration.identifier and repository.exists_identifier(
                registration.visitor_type, registration.identifier
            ):
                raise DuplicateVisitorError(
                    f"A {registration.visitor_type.lower()} with {policy.identifier_label} "
                    f"'{registration.identifier}' is already registered."
                )
            # ``create`` (not ``set``) makes an id collision visible instead of
            # silently replacing another visitor document.
            repository.create(record)

        try:
            get_store().run_transaction(write)
        except DocumentExists as exc:
            raise DuplicateVisitorError(
                f"{policy.identifier_label} '{registration.identifier}' is already registered."
            ) from exc

        mirror("visitor", lambda: self._mirror(record))
        record_activity(
            actor=actor,
            action="VISITOR_REGISTERED",
            entity_type="Visitor",
            entity_id=record.id,
            visitor_type=record.visitor_type,
            name=record.name,
            identifier=record.identifier,
        )
        return record

    @staticmethod
    def _mirror(record: VisitorRecord) -> None:
        Visitor.objects.update_or_create(
            id=record.id,
            defaults={
                "visitor_type": record.visitor_type,
                "name": record.name,
                "identifier": record.identifier,
                "student_type": record.student_type,
                "course": record.course,
                "year_level": record.year_level,
                "department": record.department,
                "organization": record.organization,
                "contact_number": record.contact_number,
                "is_active": record.is_active,
            },
        )

    # -- Relational (default / backup) ------------------------------------

    @transaction.atomic
    def _register_orm(self, registration: VisitorRegistration, policy, actor) -> Visitor:
        if registration.identifier and Visitor.objects.filter(
            visitor_type=registration.visitor_type,
            identifier__iexact=registration.identifier,
        ).exists():
            raise DuplicateVisitorError(
                f"A {registration.visitor_type.lower()} with {policy.identifier_label} "
                f"'{registration.identifier}' is already registered."
            )

        profile = asdict(registration)
        for key in ("visitor_type", "name", "identifier"):
            profile.pop(key, None)

        try:
            visitor = Visitor.objects.create(
                visitor_type=registration.visitor_type,
                name=registration.name,
                identifier=registration.identifier,
                **profile,
            )
        except IntegrityError as exc:
            raise DuplicateVisitorError(
                f"{policy.identifier_label} '{registration.identifier}' is already registered."
            ) from exc

        record_activity(
            actor=actor,
            action="VISITOR_REGISTERED",
            entity_type="Visitor",
            entity_id=str(visitor.pk),
            visitor_type=visitor.visitor_type,
            name=visitor.name,
            identifier=visitor.identifier,
        )
        return visitor

    def _sync_orm(
        self,
        registration: VisitorRegistration,
        *,
        policy,
        actor,
        mode,
        source,
        audit,
    ) -> VisitorSyncResult:
        with transaction.atomic():
            existing = Visitor.objects.filter(
                visitor_type=registration.visitor_type,
                identifier__iexact=registration.identifier,
            ).first()

            if existing is not None:
                if mode == "create_only":
                    return VisitorSyncResult(visitor=existing, skipped=True)

                changed = self._changed_fields(existing, registration)
                if mode == "dry_run":
                    return VisitorSyncResult(
                        visitor=existing,
                        updated=bool(changed),
                        skipped=not changed,
                        dry_run=True,
                        changed_fields=changed,
                    )
                if not changed:
                    return VisitorSyncResult(visitor=existing, skipped=True)

                for field in changed:
                    setattr(existing, field, getattr(registration, field))
                existing.save(update_fields=[*changed, "updated_at"])

                if audit:
                    self._audit_sync(
                        actor=actor,
                        visitor=existing,
                        action="VISITOR_UPDATED",
                        changed=changed,
                        source=source,
                    )
                return VisitorSyncResult(
                    visitor=existing,
                    updated=True,
                    changed_fields=changed,
                )

            if mode == "dry_run":
                return VisitorSyncResult(visitor=None, created=True, dry_run=True)

            profile = asdict(registration)
            for key in ("visitor_type", "name", "identifier"):
                profile.pop(key, None)

            try:
                visitor = Visitor.objects.create(
                    visitor_type=registration.visitor_type,
                    name=registration.name,
                    identifier=registration.identifier,
                    **profile,
                )
            except IntegrityError as exc:
                raise DuplicateVisitorError(
                    f"{policy.identifier_label} '{registration.identifier}' is already registered."
                ) from exc

            if audit:
                self._audit_sync(
                    actor=actor,
                    visitor=visitor,
                    action="VISITOR_REGISTERED",
                    changed=(),
                    source=source,
                )
            return VisitorSyncResult(visitor=visitor, created=True)

    def _normalise(self, registration: VisitorRegistration) -> VisitorRegistration:
        normalised = replace(
            registration,
            visitor_type=(registration.visitor_type or "").strip().upper(),
            name=(registration.name or "").strip(),
            identifier=(registration.identifier or "").strip(),
            student_type=(registration.student_type or "").strip().upper(),
            course=(registration.course or "").strip(),
            year_level=(registration.year_level or "").strip(),
            department=(registration.department or "").strip(),
            organization=(registration.organization or "").strip(),
            contact_number=(registration.contact_number or "").strip(),
        )

        if normalised.visitor_type == Visitor.Type.STUDENT and not normalised.student_type:
            normalised = replace(normalised, student_type=Visitor.StudentType.COLLEGE)

        if normalised.visitor_type == Visitor.Type.EXTERNAL and not normalised.identifier:
            normalised = replace(
                normalised,
                identifier=f"EXT-{uuid.uuid4().hex[:6].upper()}",
            )

        # Fields that do not belong to the selected type are cleared so a tab
        # switch never leaks stale data into the record.
        field_map = {
            Visitor.Type.STUDENT: ("student_type", "course", "year_level"),
            Visitor.Type.FACULTY: ("department",),
            Visitor.Type.EXTERNAL: ("organization", "contact_number"),
        }
        keep = field_map.get(normalised.visitor_type, ())
        for field in ("student_type", "course", "year_level", "department", "organization", "contact_number"):
            if field not in keep:
                normalised = replace(normalised, **{field: ""})

        return normalised
