"""Best-effort writes to the relational mirror/backup."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def mirror(label: str, callback: Callable[[], Any]) -> Any:
    """Run a backup write without letting it break the Firestore write.

    The relational copy is a backup: if it is temporarily unavailable (locked
    SQLite file, missing FK from a partial backfill) the visit is still
    recorded in the system of record and the failure is logged for follow-up.
    """
    try:
        return callback()
    except Exception:
        logger.exception("Relational mirror write failed for %s", label)
        return None
