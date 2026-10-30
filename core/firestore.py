"""Firestore configuration and client factory.

Firestore is the system of record for business data when ``FIRESTORE_ENABLED``
is on. The relational database is still required for Django auth, sessions and
the admin, and is written as a mirror/backup by the repositories.

Configuration (environment variables):

``FIRESTORE_ENABLED``
    Turn the Firestore data path on. Default: off (pure Django ORM).
``GOOGLE_CLOUD_PROJECT`` / ``FIRESTORE_PROJECT``
    Google Cloud project id.
``FIRESTORE_DATABASE``
    Firestore database id. Default: ``(default)``.
``FIRESTORE_COLLECTION_PREFIX``
    Prefix for every collection, e.g. ``visitra`` -> ``visitra_visits``.
``FIRESTORE_BACKEND``
    ``firestore`` (default) or ``memory`` (tests / offline).
``GOOGLE_APPLICATION_CREDENTIALS``
    Path to a service-account JSON file. Application Default Credentials are
    used when unset. ``FIRESTORE_EMULATOR_HOST`` is honoured by the SDK.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.conf import settings

from .store import DocumentStore, FirestoreStore, MemoryStore, StoreUnavailable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FirestoreConfig:
    enabled: bool
    backend: str
    project: str
    database: str
    collection_prefix: str


def config() -> FirestoreConfig:
    """Read the configuration from Django settings on every call.

    Reading lazily (instead of at import time) keeps ``override_settings``
    working in tests and lets a running process be reconfigured by a deploy.
    """
    backend = str(getattr(settings, "FIRESTORE_BACKEND", "firestore") or "firestore").lower()
    return FirestoreConfig(
        enabled=bool(getattr(settings, "FIRESTORE_ENABLED", False)),
        backend=backend,
        project=str(getattr(settings, "FIRESTORE_PROJECT", "") or ""),
        database=str(getattr(settings, "FIRESTORE_DATABASE", "(default)") or "(default)"),
        collection_prefix=str(getattr(settings, "FIRESTORE_COLLECTION_PREFIX", "") or "").strip("_"),
    )


def is_enabled() -> bool:
    """True when business data must be read from and written to Firestore."""
    return config().enabled


def collection_name(name: str) -> str:
    prefix = config().collection_prefix
    return f"{prefix}_{name}" if prefix else name


_STORES: dict[tuple[str, str, str], DocumentStore] = {}


def get_store() -> DocumentStore:
    """Return the process-wide document store for the current configuration."""
    cfg = config()
    if not cfg.enabled:
        raise StoreUnavailable("Firestore is disabled (FIRESTORE_ENABLED is off).")

    key = (cfg.backend, cfg.project, cfg.database)
    store = _STORES.get(key)
    if store is not None:
        return store

    if cfg.backend == "memory":
        store = MemoryStore()
    elif cfg.backend == "firestore":
        store = FirestoreStore(project=cfg.project, database=cfg.database)
    else:
        raise StoreUnavailable(f"Unknown FIRESTORE_BACKEND: {cfg.backend!r}")

    _STORES[key] = store
    return store


def reset_store() -> None:
    """Drop cached clients (tests, credential rotation, reconnect after failure)."""
    _STORES.clear()


def health() -> dict:
    """Best-effort connectivity report used by ``manage.py check_firestore``."""
    cfg = config()
    report = {
        "enabled": cfg.enabled,
        "backend": cfg.backend,
        "project": cfg.project,
        "database": cfg.database,
        "prefix": cfg.collection_prefix,
        "ok": False,
        "error": "",
    }
    if not cfg.enabled:
        report["error"] = "FIRESTORE_ENABLED is off."
        return report

    try:
        store = get_store()
        if isinstance(store, MemoryStore):
            report["ok"] = True
            report["error"] = "In-memory backend (no network call)."
        else:
            store.health()  # type: ignore[attr-defined]
            report["ok"] = True
    except Exception as exc:  # pragma: no cover - depends on real credentials
        # Configuration problems (missing key file, wrong project) are expected
        # operator errors: report them without a traceback.
        logger.warning("Firestore health check failed: %s: %s", exc.__class__.__name__, exc)
        report["error"] = f"{exc.__class__.__name__}: {exc}"
    return report
