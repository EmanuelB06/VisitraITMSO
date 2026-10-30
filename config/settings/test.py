"""Settings for the test suite.

The suite must never reach a real Firestore project: tests run against the
in-memory store, and the Firestore-specific tests opt in with the ``firestore``
fixture in ``tests/test_firestore_backend.py``. Without this module, enabling
``FIRESTORE_ENABLED`` in ``.env`` would silently point every test at production.
"""

from __future__ import annotations

from .dev import *  # noqa: F401,F403

FIRESTORE_ENABLED = False
FIRESTORE_BACKEND = "memory"
FIRESTORE_PROJECT = "demo-visitra"
