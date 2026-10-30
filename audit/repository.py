"""Firestore persistence for the append-only activity trail."""

from __future__ import annotations

import uuid

from django.utils import timezone

from core.firestore import collection_name, get_store
from core.records import ActivityLogRecord, as_aware
from core.store import DocumentStore

COLLECTION = "activity"


def _to_doc(record: ActivityLogRecord) -> dict:
    return {
        "action": record.action,
        "actor_id": record.actor_id,
        "entity_type": record.entity_type,
        "entity_id": record.entity_id,
        "metadata": record.metadata,
        "created_at": record.created_at or timezone.now(),
    }


def _from_doc(doc: dict) -> ActivityLogRecord:
    return ActivityLogRecord(
        id=str(doc["id"]),
        action=doc.get("action", ""),
        actor_id=str(doc["actor_id"]) if doc.get("actor_id") else None,
        entity_type=doc.get("entity_type", ""),
        entity_id=doc.get("entity_id", ""),
        metadata=dict(doc.get("metadata") or {}),
        created_at=as_aware(doc.get("created_at")),
    )


class AuditRepository:
    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or get_store()
        self.collection = collection_name(COLLECTION)

    def record(
        self,
        *,
        action: str,
        actor_id: str | None = None,
        entity_type: str = "",
        entity_id: str = "",
        metadata: dict | None = None,
    ) -> ActivityLogRecord:
        record = ActivityLogRecord(
            id=uuid.uuid4().hex,
            action=action,
            actor_id=str(actor_id) if actor_id else None,
            entity_type=entity_type,
            entity_id=str(entity_id),
            metadata=dict(metadata or {}),
            created_at=timezone.now(),
        )
        self.store.set(self.collection, record.id, _to_doc(record))
        return record

    def save(self, record: ActivityLogRecord) -> ActivityLogRecord:
        self.store.set(self.collection, record.id, _to_doc(record))
        return record

    def list(self, *, action: str | None = None, limit: int = 50) -> list[ActivityLogRecord]:
        docs = self.store.query(self.collection, order=("created_at", "DESCENDING"))
        records = [_from_doc(doc) for doc in docs]
        if action:
            records = [record for record in records if record.action == action]
        return records[:limit]
