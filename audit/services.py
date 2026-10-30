"""Write the activity trail to Firestore (primary) and the SQL mirror."""

from __future__ import annotations

import logging

from audit.models import ActivityLog

from .repository import AuditRepository

logger = logging.getLogger(__name__)


def record(*, action: str, actor=None, entity_type: str = "", entity_id: str = "", **metadata):
    """Append one audit entry.

    Firestore is authoritative when enabled; the SQL row is kept as the backup
    copy. Audit failures never block the business operation that triggered them.
    """
    from core.firestore import is_enabled

    actor_id = str(actor.pk) if getattr(actor, "pk", None) else None
    entry = None

    if is_enabled():
        try:
            entry = AuditRepository().record(
                action=action,
                actor_id=actor_id,
                entity_type=entity_type,
                entity_id=entity_id,
                metadata=metadata,
            )
        except Exception:
            logger.exception("Firestore audit write failed (action=%s)", action)

    try:
        ActivityLog.record(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            **metadata,
        )
    except Exception:
        logger.exception("SQL audit mirror failed (action=%s)", action)

    return entry
