"""Firestore persistence for purposes and visits.

Query strategy
--------------
Firestore only serves single-field indexes out of the box; composite indexes
must be created per query shape. To keep deployment simple this module pushes
down only single-field equality filters (``visitor_id``, ``is_active``) and does
the remaining filtering/sorting in Python. At the scale of one school office
that is well within Firestore's per-query document limits, and it keeps the
dashboard filters behaviour identical to the ORM version. If the collection
grows, add composite indexes and move the predicates into ``store.query``.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone

from core.firestore import collection_name, get_store
from core.records import (
    PurposeRecord,
    VisitorRecord,
    VisitRecord,
    as_aware,
    as_date,
)
from core.store import DocumentStore

PURPOSES = "purposes"
VISITS = "visits"


def _purpose_doc(record: PurposeRecord) -> dict:
    now = timezone.now()
    return {
        "name": record.name,
        "requires_specification": record.requires_specification,
        "is_active": record.is_active,
        "sort_order": record.sort_order,
        "created_at": record.created_at or now,
        "updated_at": record.updated_at or now,
    }


def _purpose_from_doc(doc: dict) -> PurposeRecord:
    return PurposeRecord(
        id=str(doc["id"]),
        name=doc.get("name", ""),
        requires_specification=bool(doc.get("requires_specification", False)),
        is_active=bool(doc.get("is_active", True)),
        sort_order=int(doc.get("sort_order", 0) or 0),
        created_at=as_aware(doc.get("created_at")),
        updated_at=as_aware(doc.get("updated_at")),
    )


def _visit_doc(record: VisitRecord) -> dict:
    now = timezone.now()
    return {
        "visitor_id": record.visitor.id,
        "visitor_name": record.visitor.name,
        "visitor_identifier": record.visitor.identifier,
        "visitor_type": record.visitor.visitor_type,
        "purpose_id": record.purpose_id,
        "custom_purpose": record.custom_purpose,
        "purpose_text": record.purpose_text,
        "time_in": record.time_in,
        "time_out": record.time_out,
        "visit_date": record.visit_date.isoformat(),
        "logged_by_id": record.logged_by_id,
        "deleted_at": record.deleted_at,
        "is_open": record.time_out is None,
        "is_visible": record.deleted_at is None,
        "created_at": record.created_at or now,
        "updated_at": record.updated_at or now,
    }


def _visit_from_doc(doc: dict) -> VisitRecord:
    visitor = VisitorRecord(
        id=str(doc.get("visitor_id", "")),
        visitor_type=doc.get("visitor_type", ""),
        name=doc.get("visitor_name", ""),
        identifier=doc.get("visitor_identifier", ""),
    )
    return VisitRecord(
        id=str(doc["id"]),
        visitor=visitor,
        purpose_id=str(doc.get("purpose_id", "")),
        custom_purpose=doc.get("custom_purpose", ""),
        purpose_text=doc.get("purpose_text", ""),
        time_in=as_aware(doc["time_in"]),
        time_out=as_aware(doc.get("time_out")),
        visit_date=as_date(doc.get("visit_date")),
        logged_by_id=str(doc["logged_by_id"]) if doc.get("logged_by_id") else None,
        deleted_at=as_aware(doc.get("deleted_at")),
        created_at=as_aware(doc.get("created_at")),
        updated_at=as_aware(doc.get("updated_at")),
    )


class PurposeRepository:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or get_store()
        self.collection = collection_name(PURPOSES)

    def list_active(self) -> list[PurposeRecord]:
        docs = self.store.query(self.collection, filters=[("is_active", "==", True)])
        records = [_purpose_from_doc(doc) for doc in docs]
        records.sort(key=lambda record: (record.sort_order, record.name))
        return records

    def get(self, purpose_id) -> PurposeRecord | None:
        if not purpose_id:
            return None
        doc = self.store.get(self.collection, str(purpose_id))
        return _purpose_from_doc(doc) if doc else None

    def get_active(self, purpose_id) -> PurposeRecord | None:
        purpose = self.get(purpose_id)
        return purpose if purpose and purpose.is_active else None

    def save(self, record: PurposeRecord) -> PurposeRecord:
        self.store.set(self.collection, record.id, _purpose_doc(record))
        return record

    def delete(self, purpose_id) -> None:
        self.store.delete(self.collection, str(purpose_id))


class VisitRepository:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or get_store()
        self.collection = collection_name(VISITS)

    def get(self, visit_id, *, include_deleted: bool = False) -> VisitRecord | None:
        if not visit_id:
            return None
        doc = self.store.get(self.collection, str(visit_id))
        if doc is None:
            return None
        if doc.get("deleted_at") and not include_deleted:
            return None
        return _visit_from_doc(doc)

    def save(self, record: VisitRecord) -> VisitRecord:
        self.store.set(self.collection, record.id, _visit_doc(record))
        return record

    def delete(self, visit_id) -> None:
        self.store.delete(self.collection, str(visit_id))

    def _for_visitor(self, visitor_id) -> list[dict]:
        return self.store.query(self.collection, filters=[("visitor_id", "==", str(visitor_id))])

    def find_duplicate(self, visitor_id, purpose_text: str, visit_date: date) -> VisitRecord | None:
        wanted_date = visit_date.isoformat()
        for doc in self._for_visitor(visitor_id):
            if doc.get("deleted_at"):
                continue
            if doc.get("purpose_text") != purpose_text:
                continue
            if doc.get("visit_date") != wanted_date:
                continue
            return _visit_from_doc(doc)
        return None

    def find_open(self, visitor_id) -> VisitRecord | None:
        for doc in self._for_visitor(visitor_id):
            if doc.get("deleted_at") or doc.get("time_out"):
                continue
            return _visit_from_doc(doc)
        return None

    def active_for_visitor(self, visitor_id) -> list[VisitRecord]:
        return [
            _visit_from_doc(doc)
            for doc in self._for_visitor(visitor_id)
            if not doc.get("deleted_at") and not doc.get("time_out")
        ]

    def active_for_visitors(self, visitor_ids) -> dict[str, list[VisitRecord]]:
        grouped: dict[str, list[VisitRecord]] = {}
        ids = [str(visitor_id) for visitor_id in visitor_ids]
        # Firestore allows at most 30 values in an ``in`` filter.
        for start in range(0, len(ids), 30):
            chunk = ids[start : start + 30]
            for doc in self.store.query(
                self.collection,
                filters=[("visitor_id", "in", chunk)],
            ):
                if doc.get("deleted_at") or doc.get("time_out"):
                    continue
                grouped.setdefault(str(doc["visitor_id"]), []).append(_visit_from_doc(doc))
        return grouped

    def active(self, limit: int = 50) -> list[VisitRecord]:
        docs = self.store.query(self.collection, order=("time_in", "DESCENDING"))
        records = [
            _visit_from_doc(doc)
            for doc in docs
            if not doc.get("deleted_at") and not doc.get("time_out")
        ]
        return records[:limit]

    def query(self, filters) -> list[VisitRecord]:
        """Mirror ``VisitSelector.apply`` semantics for the dashboard/exports."""
        docs = self.store.query(self.collection, order=("time_in", "DESCENDING"))
        search = (filters.search or "").lower()
        records: list[VisitRecord] = []

        for doc in docs:
            if doc.get("deleted_at"):
                continue

            visit_date = str(doc.get("visit_date", ""))
            if filters.date_from and visit_date < filters.date_from.isoformat():
                continue
            if filters.date_to and visit_date > filters.date_to.isoformat():
                continue

            if filters.status == "ACTIVE" and doc.get("time_out"):
                continue
            if filters.status == "DONE" and not doc.get("time_out"):
                continue
            if filters.visitor_type != "ALL" and doc.get("visitor_type") != filters.visitor_type:
                continue

            if search:
                haystack = " ".join(
                    str(doc.get(field, "")).lower()
                    for field in ("visitor_name", "visitor_identifier", "purpose_text")
                )
                if search not in haystack:
                    continue

            records.append(_visit_from_doc(doc))

        return records

    def summary(self, *, date_from: date | None = None, date_to: date | None = None) -> dict:
        docs = [
            doc
            for doc in self.store.query(self.collection)
            if not doc.get("deleted_at")
        ]

        if date_from or date_to:
            start = date_from.isoformat() if date_from else ""
            end = date_to.isoformat() if date_to else ""
            docs = [
                doc
                for doc in docs
                if (not start or str(doc.get("visit_date", "")) >= start)
                and (not end or str(doc.get("visit_date", "")) <= end)
            ]

        active = sum(1 for doc in docs if not doc.get("time_out"))
        return {"total": len(docs), "active": active, "done": len(docs) - active}
