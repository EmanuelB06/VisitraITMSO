from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.firestore import is_enabled
from visitors.models import Visitor
from visitors.repository import VisitorRepository
from visitors.services import VisitorRegistration, VisitorService

User = get_user_model()

DEMO_USERS = (
    {
        "username": "admin",
        "email": "admin@sbc.edu.ph",
        "password": "Admin@12345",
        "first_name": "ITMSO",
        "last_name": "Administrator",
        "role": "ADMIN",
        "is_superuser": True,
        "is_staff": True,
    },
    {
        "username": "staff",
        "email": "staff@sbc.edu.ph",
        "password": "Staff@12345",
        "first_name": "Front Desk",
        "last_name": "Staff",
        "role": "STAFF",
        "is_superuser": False,
        "is_staff": False,
    },
)

DEMO_VISITORS = (
    VisitorRegistration(
        visitor_type="STUDENT",
        name="Maria Santos",
        identifier="2024-00123",
        student_type="COLLEGE",
        course="BS Information Technology",
        year_level="2nd Year",
    ),
    VisitorRegistration(
        visitor_type="STUDENT",
        name="Jose Rizal",
        identifier="2023-00456",
        student_type="COLLEGE",
        course="BS Computer Science",
        year_level="3rd Year",
    ),
    VisitorRegistration(
        visitor_type="FACULTY",
        name="Dr. Juan Dela Cruz",
        identifier="EMP-2024-01",
        department="College of Information Technology",
    ),
    VisitorRegistration(
        visitor_type="EXTERNAL",
        name="Peter Parker",
        organization="DepEd Batangas",
        contact_number="0917 000 0000",
    ),
)


class Command(BaseCommand):
    help = "Create demo accounts and sample visitors for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Reset the demo account passwords even if the users already exist.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Run even when DEBUG is off (creates accounts with known passwords).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError(
                "seed_demo creates demo accounts with known passwords. "
                "It is disabled when DEBUG is off; pass --force only for a "
                "throwaway environment."
            )

        self.stdout.write("Seeding demo data...")

        for spec in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={
                    "email": spec["email"],
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                    "role": spec["role"],
                    "is_superuser": spec["is_superuser"],
                    "is_staff": spec["is_staff"],
                },
            )
            if created or options["reset_passwords"]:
                user.set_password(spec["password"])
                user.save(update_fields=["password"])
            self.stdout.write(
                f"  {'created' if created else 'exists '} {spec['role']:<6} {spec['username']} / {spec['password']}"
            )

        has_visitors = VisitorRepository().count() > 0 if is_enabled() else Visitor.objects.exists()
        if has_visitors:
            self.stdout.write("Visitors already present; skipping sample visitors.")
        else:
            service = VisitorService()
            for registration in DEMO_VISITORS:
                visitor = service.register(registration)
                self.stdout.write(f"  added   visitor {visitor.name} ({visitor.identifier})")

        self.stdout.write(self.style.SUCCESS("Demo data ready."))
        self.stdout.write("Sign in at /accounts/login/ with either demo account above.")
