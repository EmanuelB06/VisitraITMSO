"""Migrate Django users to Firestore.

Copies every ``accounts.User`` row into the Firestore ``users`` collection,
preserving the SQL row id as ``sql_id`` (session keys and mirror foreign keys
resolve through that integer id), and stamps any existing Firestore doc that
was created without one.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts import firestore_users
from core.firestore import collection_name, get_store, is_enabled


class Command(BaseCommand):
    help = "Copy accounts.User records to the Firestore users collection."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        if not is_enabled():
            self.stderr.write(
                self.style.ERROR(
                    "FIRESTORE_ENABLED is off. Set FIRESTORE_ENABLED=True first."
                )
            )
            return

        dry_run = options["dry_run"]
        User = get_user_model()
        store = get_store()
        users_collection = collection_name(firestore_users.USERS_COLLECTION)
        created = updated = skipped = 0

        for user in User.objects.all().order_by("id"):
            try:
                existing = (
                    firestore_users.get_by_username(user.username)
                    or (firestore_users.get_by_email(user.email) if user.email else None)
                )
                sql_id = int(user.pk)
                if existing:
                    if existing.get("sql_id") == sql_id:
                        skipped += 1
                        self.stdout.write(f"Unchanged {user.username}")
                        continue
                    if dry_run:
                        self.stdout.write(
                            f"Would stamp sql_id={sql_id} on {user.username}"
                        )
                        updated += 1
                        continue
                    # Keep the Firestore password/role; only add the id link.
                    existing["sql_id"] = sql_id
                    uid = existing.get("uid") or str(existing.get("id"))
                    store.set(users_collection, uid, existing, merge=True) \
                        if _supports_merge(store) else store.set(
                            users_collection, uid, existing
                        )
                    updated += 1
                    self.stdout.write(f"Stamped sql_id={sql_id} on {user.username}")
                    continue

                # New to Firestore: create the full document.
                if dry_run:
                    self.stdout.write(
                        f"Would create {user.username} with sql_id={sql_id}"
                    )
                    created += 1
                    continue

                uid = user.username.lower().replace(" ", "_")
                base_uid = uid
                counter = 1
                while firestore_users.get_by_uid(uid):
                    uid = f"{base_uid}_{counter}"
                    counter += 1

                role = getattr(user, "role", "")
                if role not in ("ADMIN", "STAFF"):
                    role = "ADMIN" if user.is_superuser else "STAFF"

                data = {
                    "uid": uid,
                    "username": user.username,
                    "username_lower": user.username.lower(),
                    "email": user.email or "",
                    "email_lower": (user.email or "").lower(),
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    # Already a Django password hash; copied verbatim.
                    "password": user.password,
                    "role": role,
                    "is_active": bool(user.is_active),
                    "is_superuser": bool(user.is_superuser),
                    "is_staff": bool(getattr(user, "is_staff", False))
                    or bool(user.is_superuser)
                    or role == "ADMIN",
                    "sql_id": sql_id,
                    "date_joined": user.date_joined.isoformat()
                    if user.date_joined
                    else None,
                    "last_login": user.last_login.isoformat()
                    if user.last_login
                    else None,
                    "migrated_from_sql": True,
                }
                store.set(users_collection, uid, data)
                created += 1
                self.stdout.write(f"Created {user.username} (sql_id={sql_id})")
            except Exception as exc:
                self.stderr.write(f"Failed to migrate {user.username}: {exc}")

        # Firestore-only users (created in the admin panel) still need an
        # integer id for sessions, so allocate one for any doc missing it.
        try:
            max_sql_id = int(
                User.objects.order_by("-id").values_list("id", flat=True).first() or 0
            )
            for doc in store.query(users_collection) or []:
                if doc.get("sql_id"):
                    continue
                uid = doc.get("uid") or doc.get("id")
                if not uid:
                    continue
                max_sql_id += 1
                if dry_run:
                    self.stdout.write(
                        f"Would allocate sql_id={max_sql_id} for {uid}"
                    )
                    continue
                doc["sql_id"] = max_sql_id
                store.set(users_collection, uid, doc)
                self.stdout.write(f"Allocated sql_id={max_sql_id} for {uid}")
        except Exception as exc:
            self.stderr.write(f"sql_id backfill failed: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Migrated {created}, updated {updated}, unchanged {skipped} users"
            )
        )


def _supports_merge(store) -> bool:
    import inspect

    return "merge" in inspect.signature(store.set).parameters
