"""Verify that the Firestore connection is usable."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.firestore import health


class Command(BaseCommand):
    help = "Check Firestore configuration and connectivity."

    def handle(self, *args, **options):
        report = health()

        self.stdout.write(f"enabled:  {report['enabled']}")
        self.stdout.write(f"backend:  {report['backend']}")
        self.stdout.write(f"project:  {report['project'] or '(from credentials)'}")
        self.stdout.write(f"database: {report['database']}")
        self.stdout.write(f"prefix:   {report['prefix'] or '(none)'}")

        if report["ok"]:
            self.stdout.write(self.style.SUCCESS(f"OK. {report['error']}".rstrip()))
            return

        raise CommandError(f"Firestore is not reachable. {report['error']}")
