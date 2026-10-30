from __future__ import annotations

from django.core.management.base import BaseCommand

from core.firestore import is_enabled
from core.records import PurposeRecord
from visits.models import Purpose
from visits.repository import PurposeRepository

PURPOSES = [
    ("MS 365 Assistance", False, 10),
    ("School Automate Assistance", False, 20),
    ("Canva Registration", False, 30),
    ("Request Voucher", False, 40),
    ("ID Printing", False, 50),
    ("Other Concerns", True, 60),
]


class Command(BaseCommand):
    help = "Create or refresh the ITMSO visit purposes."

    def handle(self, *args, **options):
        created = 0
        repository = PurposeRepository() if is_enabled() else None
        for name, requires_specification, sort_order in PURPOSES:
            purpose, was_created = Purpose.objects.update_or_create(
                name=name,
                defaults={
                    "requires_specification": requires_specification,
                    "sort_order": sort_order,
                    "is_active": True,
                },
            )
            created += int(was_created)

            if repository is not None:
                repository.save(
                    PurposeRecord(
                        id=str(purpose.pk),
                        name=purpose.name,
                        requires_specification=purpose.requires_specification,
                        is_active=purpose.is_active,
                        sort_order=purpose.sort_order,
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Purposes ready ({created} created, {len(PURPOSES) - created} updated)."
            )
        )
