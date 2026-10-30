"""Copy business data between the relational database and Firestore.

Use this once after enabling Firestore (SQL -> Firestore) and to rebuild the
backup copy after restoring or migrating (Firestore -> SQL).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from audit.models import ActivityLog
from audit.repository import AuditRepository, _from_doc as audit_from_doc
from core.firestore import collection_name, get_store, is_enabled
from core.records import ActivityLogRecord, PurposeRecord, VisitorRecord, VisitRecord
from visits.models import Purpose, Visit
from visits.repository import (
    PurposeRepository,
    VisitRepository,
    _purpose_from_doc,
    _visit_from_doc,
)
from visitors.models import Visitor
from visitors.repository import VisitorRepository, _from_doc as visitor_from_doc

DIRECTIONS = ("to-firestore", "to-sql")


class Command(BaseCommand):
    help = "Backfill Firestore from SQL, or rebuild the SQL backup from Firestore."

    def add_arguments(self, parser):
        parser.add_argument(
            "--direction",
            choices=DIRECTIONS,
            default="to-firestore",
            help="to-firestore: SQL -> Firestore (initial migration). "
            "to-sql: Firestore -> SQL (rebuild the backup).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report how many documents would be written without writing.",
        )

    def handle(self, *args, **options):
        if not is_enabled():
            raise CommandError("Set FIRESTORE_ENABLED=True before syncing.")

        direction = options["direction"]
        dry_run = options["dry_run"]

        if direction == "to-firestore":
            counts = self._to_firestore(dry_run)
        else:
            counts = self._to_sql(dry_run)

        prefix = "Would write" if dry_run else "Wrote"
        for label, count in counts.items():
            self.stdout.write(f"{prefix} {count} {label}.")

        self.stdout.write(self.style.SUCCESS(f"Sync finished ({direction})."))

    # -- SQL -> Firestore -------------------------------------------------

    def _to_firestore(self, dry_run: bool) -> dict[str, int]:
        purposes = PurposeRepository()
        visitors = VisitorRepository()
        visits = VisitRepository()
        audit = AuditRepository()

        counts = {"purposes": 0, "visitors": 0, "visits": 0, "activity": 0}

        for purpose in Purpose.objects.all():
            counts["purposes"] += 1
            if not dry_run:
                purposes.save(
                    PurposeRecord(
                        id=str(purpose.pk),
                        name=purpose.name,
                        requires_specification=purpose.requires_specification,
                        is_active=purpose.is_active,
                        sort_order=purpose.sort_order,
                        created_at=purpose.created_at,
                        updated_at=purpose.updated_at,
                    )
                )

        for visitor in Visitor.objects.all():
            counts["visitors"] += 1
            if not dry_run:
                visitors.save(
                    VisitorRecord(
                        id=str(visitor.pk),
                        visitor_type=visitor.visitor_type,
                        name=visitor.name,
                        identifier=visitor.identifier,
                        student_type=visitor.student_type,
                        course=visitor.course,
                        year_level=visitor.year_level,
                        department=visitor.department,
                        organization=visitor.organization,
                        contact_number=visitor.contact_number,
                        is_active=visitor.is_active,
                        created_at=visitor.created_at,
                        updated_at=visitor.updated_at,
                    )
                )

        for visit in Visit.objects.visible().select_related("visitor"):
            counts["visits"] += 1
            if not dry_run:
                visits.save(
                    VisitRecord(
                        id=str(visit.pk),
                        visitor=VisitorRecord(
                            id=str(visit.visitor_id),
                            visitor_type=visit.visitor.visitor_type,
                            name=visit.visitor.name,
                            identifier=visit.visitor.identifier,
                        ),
                        purpose_id=str(visit.purpose_id),
                        custom_purpose=visit.custom_purpose,
                        purpose_text=visit.purpose_text,
                        time_in=visit.time_in,
                        time_out=visit.time_out,
                        visit_date=visit.visit_date,
                        logged_by_id=str(visit.logged_by_id) if visit.logged_by_id else None,
                        deleted_at=visit.deleted_at,
                        created_at=visit.created_at,
                        updated_at=visit.updated_at,
                    )
                )

        for entry in ActivityLog.objects.all():
            counts["activity"] += 1
            if not dry_run:
                audit.save(
                    ActivityLogRecord(
                        id=str(entry.pk),
                        action=entry.action,
                        actor_id=str(entry.actor_id) if entry.actor_id else None,
                        entity_type=entry.entity_type,
                        entity_id=entry.entity_id,
                        metadata=entry.metadata,
                        created_at=entry.created_at,
                    )
                )

        return counts

    # -- Firestore -> SQL -------------------------------------------------

    @transaction.atomic
    def _to_sql(self, dry_run: bool) -> dict[str, int]:
        store = get_store()
        counts = {"purposes": 0, "visitors": 0, "visits": 0, "activity": 0}

        for doc in store.query(collection_name("purposes")):
            record = _purpose_from_doc(doc)
            counts["purposes"] += 1
            if dry_run:
                continue
            Purpose.objects.update_or_create(
                id=record.id,
                defaults={
                    "name": record.name,
                    "requires_specification": record.requires_specification,
                    "is_active": record.is_active,
                    "sort_order": record.sort_order,
                },
            )

        for doc in store.query(collection_name("visitors")):
            record = visitor_from_doc(doc)
            counts["visitors"] += 1
            if dry_run:
                continue
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

        for doc in store.query(collection_name("visits")):
            record = _visit_from_doc(doc)
            counts["visits"] += 1
            if dry_run:
                continue
            if not Visitor.objects.filter(pk=record.visitor.id).exists():
                self.stderr.write(
                    f"  skipped visit {record.id}: visitor {record.visitor.id} is missing."
                )
                continue
            Visit.objects.update_or_create(
                id=record.id,
                defaults={
                    "visitor_id": record.visitor.id,
                    "purpose_id": record.purpose_id or None,
                    "custom_purpose": record.custom_purpose,
                    "purpose_text": record.purpose_text,
                    "time_in": record.time_in,
                    "time_out": record.time_out,
                    "visit_date": record.visit_date,
                    "logged_by_id": record.logged_by_id,
                    "deleted_at": record.deleted_at,
                },
            )

        for doc in store.query(collection_name("activity")):
            record = audit_from_doc(doc)
            counts["activity"] += 1
            if dry_run:
                continue
            ActivityLog.objects.update_or_create(
                id=record.id,
                defaults={
                    "actor_id": record.actor_id,
                    "action": record.action,
                    "entity_type": record.entity_type,
                    "entity_id": record.entity_id,
                    "metadata": record.metadata,
                },
            )

        return counts
