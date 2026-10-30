"""Firestore persistence for visitors."""

from __future__ import annotations

from dataclasses import replace

from django.utils import timezone

from core.firestore import collection_name, get_store
from core.records import VisitorRecord, as_aware
from core.store import DocumentStore

COLLECTION = "visitors"


def _to_doc(record: VisitorRecord) -> dict:
    now = timezone.now()
    return {
        "visitor_type": record.visitor_type,
        "name": record.name,
        "name_lower": record.name.lower(),
        "identifier": record.identifier,
        "identifier_lower": record.identifier.lower(),
        "student_type": record.student_type,
        "course": record.course,
        "year_level": record.year_level,
        "department": record.department,
        "organization": record.organization,
        "contact_number": record.contact_number,
        "is_active": record.is_active,
        "created_at": record.created_at or now,
        "updated_at": record.updated_at or now,
    }


def _from_doc(doc: dict) -> VisitorRecord:
    return VisitorRecord(
        id=str(doc["id"]),
        visitor_type=doc.get("visitor_type", ""),
        name=doc.get("name", ""),
        identifier=doc.get("identifier", ""),
        student_type=doc.get("student_type", ""),
        course=doc.get("course", ""),
        year_level=doc.get("year_level", ""),
        department=doc.get("department", ""),
        organization=doc.get("organization", ""),
        contact_number=doc.get("contact_number", ""),
        is_active=bool(doc.get("is_active", True)),
        created_at=as_aware(doc.get("created_at")),
        updated_at=as_aware(doc.get("updated_at")),
    )


class VisitorRepository:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or get_store()
        self.collection = collection_name(COLLECTION)

    def get(self, visitor_id) -> VisitorRecord | None:
        if not visitor_id:
            return None
        doc = self.store.get(self.collection, str(visitor_id))
        return _from_doc(doc) if doc else None

    def find_by_identifier(self, visitor_type: str, identifier: str) -> VisitorRecord | None:
        identifier = (identifier or "").strip().lower()
        if not identifier:
            return None
        docs = self.store.query(
            self.collection,
            filters=[("identifier_lower", "==", identifier)],
        )
        for doc in docs:
            if doc.get("visitor_type") == visitor_type:
                return _from_doc(doc)
        return None

    def exists_identifier(
        self,
        visitor_type: str,
        identifier: str,
        *,
        exclude_id: str | None = None,
    ) -> bool:
        found = self.find_by_identifier(visitor_type, identifier)
        return found is not None and found.id != str(exclude_id or "")

    def lookup(
        self,
        term: str,
        visitor_type: str | None = None,
        limit: int = 8,
    ) -> list[VisitorRecord]:
        term = (term or "").strip().lower()
        if not term:
            return []

        docs = self.store.query(
            self.collection,
            filters=[("is_active", "==", True)],
        )
        matches = [
            doc
            for doc in docs
            if term in str(doc.get("name", "")).lower()
            or term in str(doc.get("identifier", "")).lower()
        ]
        if visitor_type:
            matches = [doc for doc in matches if doc.get("visitor_type") == visitor_type]
        matches.sort(key=lambda doc: str(doc.get("name", "")).lower())
        records = [_from_doc(doc) for doc in matches[:limit]]

        # The kiosk serializer shows the visitor's open session, if any.
        from visits.repository import VisitRepository

        active = VisitRepository(self.store).active_for_visitors([record.id for record in records])
        return [
            replace(record, active_visits=tuple(active.get(record.id, ())))
            for record in records
        ]

    def save(self, record: VisitorRecord) -> VisitorRecord:
        self.store.set(self.collection, record.id, _to_doc(record))
        return record

    def create(self, record: VisitorRecord) -> VisitorRecord:
        self.store.create(self.collection, record.id, _to_doc(record))
        return record

    def count(self) -> int:
        return len(self.store.query(self.collection))

    def delete(self, visitor_id) -> None:
        self.store.delete(self.collection, str(visitor_id))
