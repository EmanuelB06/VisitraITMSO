"""Infrastructure abstractions.

The ``Clock`` seam keeps business rules testable: services accept any object
with ``now()`` / ``local_date()``, so date-boundary scenarios are deterministic.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone


class Clock:
    """Default wall clock backed by Django's timezone utilities."""

    def now(self):
        return timezone.now()

    def local_date(self, moment) -> date:
        return timezone.localdate(moment)

    def local(self, moment):
        return timezone.localtime(moment)
