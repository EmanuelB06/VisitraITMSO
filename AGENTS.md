# AGENTS.md

Django 5.2 visitor-logging app with server-rendered templates and small JSON APIs. `README.md` is the authoritative setup, URL, business-rule, and production reference; this file records the non-obvious working rules.

## Commands (Windows, repository venv)

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # full suite: currently 102 tests, ~85 s
.\.venv\Scripts\python.exe -m pytest tests/test_views.py::test_admin_exports -q
.\.venv\Scripts\python.exe -m pytest tests/test_visit_service.py -k time_out -q
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py check_firestore
.\.venv\Scripts\python.exe manage.py sync_firestore --direction=to-firestore
.\.venv\Scripts\python.exe manage.py runserver
```

- `pytest.ini` hard-wires `config.settings.test`, which forces Firestore off and the in-memory backend; tests create their own database and never touch `db.sqlite3` or a live Firestore project. Set `FIRESTORE_TEST_BACKEND=firestore` plus `FIRESTORE_EMULATOR_HOST` to run `tests/test_firestore_backend.py` against the emulator.
- There is no lint/format/typecheck config and no JS toolchain or CI. Pytest is the quality gate; do not invent npm/build/lint steps.
- Setup: `pip install -r requirements-dev.txt`, copy `.env.example` to `.env`, run `migrate`, then `seed_purposes`. Purposes are database rows; the kiosk has no selectable purposes without them.
- `seed_demo` adds demo users and sample visitors. It skips sample visitors when any `Visitor` already exists; use `--reset-passwords` to restore the documented demo logins.
- `manage.py` defaults to `config.settings.dev`; `wsgi.py`/`asgi.py` default to `config.settings.prod`. For production, set `DJANGO_SETTINGS_MODULE` in the shell before launching — `.env` is loaded too late to select the settings module.

## Code boundaries and invariants

- Request path: URL → view → form/serializer → service → model/selector → template/JSON. Views handle HTTP; services own business rules; selectors own read queries; exporters own file formats.
- **Firestore is the system of record** when `FIRESTORE_ENABLED=True`: business data lives in `core/records.py` dataclasses persisted by `visitors/repository.py`, `visits/repository.py` and `audit/repository.py`. The SQL models are a best-effort backup mirror written by the services via `core/mirror.py`; auth, sessions and the admin stay relational and cannot move to Firestore.
- Do not query or write `Visitor`/`Visit`/`Purpose` models directly on a request path: go through services (writes) and selectors (reads) so both stores stay consistent. `sync_firestore` is the only sanctioned bulk SQL↔Firestore copy.
- Firestore has no partial unique indexes. The duplicate-purpose, one-active-visit and duplicate-visitor rules are enforced in the service layer before the write; keep a single writer process and treat the SQL constraints as a second line of defence.
- Use `VisitorService.register()` and `VisitService.time_in()` / `time_out()` / `soft_delete()` instead of creating or updating those models directly. Services write activity entries and raise `DomainError` subclasses; JSON APIs translate domain errors to HTTP 409.
- Duplicate-purpose, one-active-visit, and time-out-after-time-in rules also exist as `Visit` DB constraints. Direct ORM writes can bypass audit logging or raise `IntegrityError`.
- Deletes are soft (`Visit.deleted_at`). Query through `Visit.objects.visible()` / `active()` / `completed()`; never hard-delete visits. `ActivityLog` is append-only.
- Dashboard and exports share `VisitFilter` / `VisitSelector` in `visits/selectors.py`; filter changes affect both. Add export formats by subclassing `BaseExporter` and registering it in `reports/exporters/factory.py`.
- Visitor type rules live in `visitors/policies.py`. Adding a visitor type is not policy-only: also update `Visitor.Type`, the field-clearing map in `VisitorService._normalise`, `VisitorRegistrationForm`, and the `COPY` map plus type tabs in `static/js/kiosk.js`.
- Authentication uses `accounts.User`; login accepts either username or email. "Admin" means `User.role == ADMIN` or `is_superuser` (`user.is_admin_role`). Capability decisions belong in `accounts/permissions.py`; templates read them as `caps` from `accounts/context_processors.py`. `StaffRequiredMixin`/`api_staff_required` accept active staff or admins, and `AdminRequiredMixin` accepts active admins only.
- Staff see only the current local day on the dashboard; date filters are ignored for them. Admins keep full history and date filters. Exports, deletes, purpose/user management, the audit trail, and Django admin are admin-only.
- `is_staff` is kept equal to `is_admin_role` by `UserAdmin` (granted and revoked on save), and access changes are written to the audit trail as `ACCESS_CHANGED`.
- Usernames and emails are unique case-insensitively; an ambiguous username/email match is rejected. Failed logins are throttled through Django's cache (`LOGIN_MAX_ATTEMPTS`, `LOGIN_LOCKOUT_SECONDS`) and auth signals write `LOGIN` / `LOGIN_FAILED` to the audit trail.
- `config.settings.prod` refuses to start without `DJANGO_SECRET_KEY` and refuses SQLite unless `DJANGO_ALLOW_SQLITE_PROD=True`. `seed_demo` is disabled when `DEBUG` is off unless run with `--force`.
- Timestamps are stored in UTC with `TIME_ZONE = "Asia/Manila"`. Services accept an injectable `Clock`; date-sensitive tests use `FixedClock` and `manila(...)` from `tests/conftest.py` instead of patching `timezone.now()`.
- Templates are rendered server-side. `static/` holds source CSS and plain ES modules; `staticfiles/` is generated by `collectstatic` and is gitignored. Edit `static/`, never `staticfiles/`.

## Tests

- All tests live in `tests/` (none per-app). Shared fixtures in `tests/conftest.py`: `admin_user`, `staff_user`, `purpose`, `detailed_purpose`, `student`, `faculty`.
- Mark database tests with `@pytest.mark.django_db`. Service tests use `FixedClock`; advance it with `clock.set(manila(2026, 3, 10, 9, 45))`.
- Export views return `FileResponse`; tests join `response.streaming_content` and assert raw signatures: CSV BOM (`\xef\xbb\xbf`), `%PDF`, and `PK`.
