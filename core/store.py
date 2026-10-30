"""Document-store abstraction for the Firestore data layer.

Business data (purposes, visitors, visits, activity) is stored as documents.
Repositories talk to this narrow interface instead of the Google SDK directly so
that:

* the same repository code runs against Firestore in production, and
* tests and offline development can use an in-memory store.

Filters use the ``(field, operator, value)`` shape and support the subset of
operators the repositories actually need.
"""

from __future__ import annotations

import copy
import threading
from typing import Any, Callable, Iterable, Protocol, Sequence

Filter = tuple[str, str, Any]
Order = tuple[str, str]  # (field, "ASCENDING" | "DESCENDING")


class StoreError(Exception):
    """Base class for document-store failures."""


class StoreUnavailable(StoreError):
    """The configured store cannot be reached (missing credentials, network...)."""


class DocumentExists(StoreError):
    """A document with that id already exists."""


class DocumentStore(Protocol):
    def get(self, collection: str, doc_id: str) -> dict | None: ...

    def set(self, collection: str, doc_id: str, data: dict) -> None: ...

    def create(self, collection: str, doc_id: str, data: dict) -> None: ...

    def update(self, collection: str, doc_id: str, data: dict) -> None: ...

    def delete(self, collection: str, doc_id: str) -> None: ...

    def query(
        self,
        collection: str,
        *,
        filters: Sequence[Filter] = (),
        order: Order | None = None,
        limit: int | None = None,
    ) -> list[dict]: ...

    def run_transaction(self, callback: Callable[["DocumentStore"], Any]) -> Any: ...


def _matches(value: Any, operator: str, expected: Any) -> bool:
    if operator == "==":
        return value == expected
    if operator == "!=":
        return value != expected
    if operator == "in":
        return value in expected
    if operator == "not-in":
        return value not in expected
    if operator == "<":
        return value is not None and value < expected
    if operator == "<=":
        return value is not None and value <= expected
    if operator == ">":
        return value is not None and value > expected
    if operator == ">=":
        return value is not None and value >= expected
    if operator == "array_contains":
        return isinstance(value, (list, tuple, set)) and expected in value
    raise StoreError(f"Unsupported filter operator: {operator}")


class MemoryStore:
    """In-process store used by tests and offline development.

    Documents are deep-copied on every boundary so callers can never mutate the
    stored state by accident. ``run_transaction`` rolls the whole store back if
    the callback raises, which mirrors Firestore's all-or-nothing behaviour
    closely enough for the uniqueness rules in this app.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[str, dict]] = {}
        self._lock = threading.RLock()

    def _bucket(self, collection: str) -> dict[str, dict]:
        return self._data.setdefault(collection, {})

    @staticmethod
    def _copy(doc: dict) -> dict:
        return copy.deepcopy(doc)

    def get(self, collection: str, doc_id: str) -> dict | None:
        with self._lock:
            doc = self._bucket(collection).get(str(doc_id))
            if doc is None:
                return None
            return {**self._copy(doc), "id": str(doc_id)}

    def set(self, collection: str, doc_id: str, data: dict) -> None:
        with self._lock:
            self._bucket(collection)[str(doc_id)] = self._copy(data)

    def create(self, collection: str, doc_id: str, data: dict) -> None:
        with self._lock:
            bucket = self._bucket(collection)
            if str(doc_id) in bucket:
                raise DocumentExists(f"{collection}/{doc_id} already exists.")
            bucket[str(doc_id)] = self._copy(data)

    def update(self, collection: str, doc_id: str, data: dict) -> None:
        with self._lock:
            bucket = self._bucket(collection)
            current = bucket.get(str(doc_id))
            if current is None:
                raise StoreError(f"{collection}/{doc_id} does not exist.")
            bucket[str(doc_id)] = {**self._copy(current), **self._copy(data)}

    def delete(self, collection: str, doc_id: str) -> None:
        with self._lock:
            self._bucket(collection).pop(str(doc_id), None)

    def query(
        self,
        collection: str,
        *,
        filters: Sequence[Filter] = (),
        order: Order | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        with self._lock:
            docs = [
                {**self._copy(doc), "id": doc_id}
                for doc_id, doc in self._bucket(collection).items()
            ]

        for field, operator, expected in filters:
            docs = [doc for doc in docs if _matches(doc.get(field), operator, expected)]

        if order:
            field, direction = order
            docs.sort(
                key=lambda doc: (doc.get(field) is None, doc.get(field)),
                reverse=direction.upper().startswith("DESC"),
            )

        if limit is not None:
            docs = docs[:limit]
        return docs

    def run_transaction(self, callback: Callable[[DocumentStore], Any]) -> Any:
        with self._lock:
            snapshot = copy.deepcopy(self._data)
            try:
                return callback(self)
            except Exception:
                self._data = snapshot
                raise

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class _FirestoreTransaction:
    """Transaction-scoped view of :class:`FirestoreStore`."""

    def __init__(self, client, transaction) -> None:
        self._client = client
        self._transaction = transaction

    def _ref(self, collection: str, doc_id: str):
        return self._client.collection(collection).document(str(doc_id))

    def get(self, collection: str, doc_id: str) -> dict | None:
        snapshot = self._transaction.get(self._ref(collection, doc_id))
        if not snapshot.exists:
            return None
        return {**snapshot.to_dict(), "id": snapshot.id}

    def set(self, collection: str, doc_id: str, data: dict) -> None:
        self._transaction.set(self._ref(collection, doc_id), data)

    def create(self, collection: str, doc_id: str, data: dict) -> None:
        if self.get(collection, doc_id) is not None:
            raise DocumentExists(f"{collection}/{doc_id} already exists.")
        self.set(collection, doc_id, data)

    def update(self, collection: str, doc_id: str, data: dict) -> None:
        self._transaction.update(self._ref(collection, doc_id), data)

    def delete(self, collection: str, doc_id: str) -> None:
        self._transaction.delete(self._ref(collection, doc_id))

    def query(
        self,
        collection: str,
        *,
        filters: Sequence[Filter] = (),
        order: Order | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        query = _build_query(self._client.collection(collection), filters, order, limit)
        return [
            {**snapshot.to_dict(), "id": snapshot.id}
            for snapshot in self._transaction.get(query)
        ]


def _field_filter(field: str, operator: str, value):
    """Build a Firestore filter, preferring the modern ``FieldFilter`` API.

    Positional ``where(field, op, value)`` is deprecated and emits a
    ``UserWarning`` on current SDK releases. Returns ``None`` when the installed
    SDK predates ``FieldFilter`` so the caller can fall back.
    """
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
    except ImportError:  # pragma: no cover - depends on SDK version
        return None
    return FieldFilter(field, operator, value)


def _build_query(collection_ref, filters, order, limit):
    query = collection_ref
    for field, operator, value in filters:
        field_filter = _field_filter(field, operator, value)
        if field_filter is None:  # pragma: no cover - legacy SDK
            query = query.where(field, operator, value)
        else:
            query = query.where(filter=field_filter)
    if order:
        field, direction = order
        query = query.order_by(
            field,
            direction="DESCENDING" if direction.upper().startswith("DESC") else "ASCENDING",
        )
    if limit is not None:
        query = query.limit(limit)
    return query


class FirestoreStore:
    """Thin adapter over ``google-cloud-firestore``.

    Credentials come from ``GOOGLE_APPLICATION_CREDENTIALS`` or Application
    Default Credentials. ``FIRESTORE_EMULATOR_HOST`` is honoured automatically
    by the Google client.
    """

    def __init__(self, project: str | None, database: str = "(default)") -> None:
        try:
            from google.cloud import firestore
        except ImportError as exc:  # pragma: no cover - depends on install
            raise StoreUnavailable(
                "google-cloud-firestore is not installed. Run "
                "`pip install -r requirements.txt`."
            ) from exc

        try:
            self._client = firestore.Client(project=project or None, database=database)
        except TypeError:
            # Older google-cloud-firestore releases do not accept ``database``.
            self._client = firestore.Client(project=project or None)

    def _ref(self, collection: str, doc_id: str):
        return self._client.collection(collection).document(str(doc_id))

    def get(self, collection: str, doc_id: str) -> dict | None:
        snapshot = self._ref(collection, doc_id).get()
        if not snapshot.exists:
            return None
        return {**snapshot.to_dict(), "id": snapshot.id}

    def set(self, collection: str, doc_id: str, data: dict) -> None:
        self._ref(collection, doc_id).set(data)

    def create(self, collection: str, doc_id: str, data: dict) -> None:
        try:
            self._ref(collection, doc_id).create(data)
        except Exception as exc:  # google.api_core.exceptions.AlreadyExists
            if exc.__class__.__name__ == "AlreadyExists":
                raise DocumentExists(f"{collection}/{doc_id} already exists.") from exc
            raise

    def update(self, collection: str, doc_id: str, data: dict) -> None:
        self._ref(collection, doc_id).update(data)

    def delete(self, collection: str, doc_id: str) -> None:
        self._ref(collection, doc_id).delete()

    def query(
        self,
        collection: str,
        *,
        filters: Sequence[Filter] = (),
        order: Order | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        query = _build_query(self._client.collection(collection), filters, order, limit)
        return [{**snapshot.to_dict(), "id": snapshot.id} for snapshot in query.stream()]

    def run_transaction(self, callback: Callable[[DocumentStore], Any]) -> Any:
        from google.cloud import firestore

        transaction = self._client.transaction()

        @firestore.transactional
        def _run(tx):
            return callback(_FirestoreTransaction(self._client, tx))

        return _run(transaction)

    def health(self) -> None:
        self._client.collection("_healthcheck").limit(1).get()
