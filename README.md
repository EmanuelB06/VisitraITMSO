# VisitraITMSO — Web Edition

Visitor logging for the **Office of IT Management & Systems (ITMSO)** of
**St. Bridget College Batangas**, rebuilt from the Android app as a Django web
application.

Staff use a browser-based kiosk to register visitors and record time in /
time out, with a dashboard limited to the current day. Administrators get the
full history with counters, filters, search, exports, and soft-delete.

---

## Features

- **Visitor registration** for students, faculty, and external visitors.
- Type-aware fields and rules (student ID, employee ID, generated external reference).
- **Kiosk** with live visitor lookup, purpose selection, custom concern text,
  time in, time out, and an “Inside now” panel.
- **Dashboard** with total / active / completed counters, search by name, ID,
  or purpose, status and visitor-type filters. Staff see today only; admins can
  also filter by date range and browse full history.
- **Exports**: CSV, PDF (print-ready), and XLSX (formatted workbook), admin-only.
- **Roles**: staff can register, log visits, and read today's dashboard; admins
  can also view history, export, delete records, manage purposes/users, read the
  audit trail, and use Django admin.
- **Audit trail** of sign-ins, failed sign-ins, registrations, time in/out,
  deletions, exports, and access/role changes.
- **Login protection**: case-insensitive unique usernames/emails and a
  cache-backed lockout after repeated failed attempts.
- Dark, responsive UI with keyboard-friendly lookup and print styles.

### Roles and capabilities

Capabilities are defined once in `accounts/permissions.py` and exposed to
templates as `caps`.

| Capability | Staff | Admin |
|------------|:-----:|:-----:|
| Register visitors, lookup, time in/out | Yes | Yes |
| Dashboard: today's records | Yes | Yes |
| Dashboard: full history and date filters | No | Yes |
| Export CSV / PDF / XLSX | No | Yes |
| Soft-delete records | No | Yes |
| Manage purposes and users | No | Yes |
| View audit trail | No | Yes |
| Django admin (`is_staff`) | No | Yes |

---

## Quick start (Windows / PowerShell)

```powershell
cd C:\Users\Acer\Desktop\VisitraITMSO

# 1. Create and activate a virtual environment (already present in this copy)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements-dev.txt

# 3. Configure the environment
Copy-Item .env.example .env
# edit .env and set a long random DJANGO_SECRET_KEY

# 4. Create the database
python manage.py migrate

# 5. Seed purposes and demo data
python manage.py seed_purposes
python manage.py seed_demo

# 6. Run
python manage.py runserver
```

Open <http://127.0.0.1:8000/>.

On macOS/Linux use `python3 -m venv .venv`, `source .venv/bin/activate`, and
`cp .env.example .env`.

### Demo accounts

| Role  | Username | Password      | Email                |
|-------|----------|---------------|----------------------|
| Admin | `admin`  | `Admin@12345` | `admin@sbc.edu.ph`   |
| Staff | `staff`  | `Staff@12345` | `staff@sbc.edu.ph`   |

Sign-in accepts either the username or the email address. Change these
passwords before using the app for real data.

### Seed / maintenance commands

```powershell
python manage.py seed_purposes          # create or refresh the six purposes
python manage.py seed_demo              # demo users + sample visitors (DEBUG only)
python manage.py seed_demo --reset-passwords
python manage.py seed_demo --force      # run even when DEBUG is off
python manage.py createsuperuser
python manage.py check_firestore        # verify Firestore config/connectivity
python manage.py sync_firestore --direction=to-firestore   # SQL -> Firestore
python manage.py sync_firestore --direction=to-sql         # Firestore -> SQL backup
```

Visit purposes are ordinary database records: edit them at `/admin/` under
**Visits → Purposes** (name, sort order, active flag, and whether the visitor
must specify a concern).

---

## Screens and URLs

| URL | Access | Purpose |
|-----|--------|---------|
| `/` | Public | Landing page and staff sign-in link |
| `/accounts/login/` | Public | Staff authentication |
| `/visitors/register/` | Staff | Create a visitor record |
| `/visits/` | Staff | Kiosk: lookup, time in, time out |
| `/dashboard/` | Staff | Today's counters, filters, and records (admins see all history) |
| `/dashboard/export/?format=csv\|pdf\|xlsx` | Admin | Download a filtered report |
| `/dashboard/<uuid>/delete/` | Admin | Soft-delete a visit |
| `/admin/` | Admin | Django admin (users, visitors, purposes, audit log) |
| `/healthz/` | Public | JSON health probe |

---

## Architecture

```
config/          settings (base/dev/prod), root URLs, WSGI/ASGI
core/            UUID/timestamp models, Clock, Firestore store/client, API helpers
accounts/        custom User, email-or-username backend, role mixins, login views
visitors/        Visitor model, policies, repository (Firestore), selectors, service
visits/          Purpose + Visit models, repositories, VisitService, filters, kiosk/API
reports/         dashboard and delete views, CSV/PDF/XLSX exporters, factory
audit/           append-only ActivityLog + Firestore audit repository
templates/       server-rendered pages and shared partials
static/          CSS design system, ES-module JavaScript, logo
tests/           pytest suite (102 tests)
```

Requests flow in one direction:

```
URL → view (HTTP) → form/serializer (input) → service (business rules)
    → repository (Firestore, system of record)
    → model mirror (SQL backup) / selector (reads) → template or JSON
```

With `FIRESTORE_ENABLED` off (the default), the model/selector path is used
exactly as before; repositories are bypassed.

### SOLID mapping

- **Single responsibility** — views handle HTTP; forms validate input;
  services own use cases; selectors own queries; serializers shape JSON;
  exporters turn data into files.
- **Open/closed** — a new visitor type is a new `VisitorPolicy`; a new export
  format is a new `BaseExporter` subclass registered in the factory.
- **Liskov substitution** — all policies and exporters honour the same small
  contracts and are interchangeable.
- **Interface segregation** — thin mixins (`StaffRequiredMixin`,
  `AdminRequiredMixin`) and narrow helper modules instead of one god object.
- **Dependency inversion** — services accept a `Clock` abstraction, so time
  rules are deterministic in tests; views depend on services, not ORM details.

### Data model

- **Visitor** — one table for all types; nullable type-specific columns.
  `identifier` is unique per visitor type when present.
- **Purpose** — seeded visit reasons; `requires_specification` adds the
  “Specify concern” field.
- **Visit** — visitor, purpose, effective `purpose_text` snapshot, time in/out,
  visit date, operator, optional soft-delete timestamp.
- **ActivityLog** — actor, action, entity, and JSON metadata; read-only in admin.

### Business rules

- A visitor can have only **one active visit** at a time.
- The same visitor cannot log the **same effective purpose twice on one day**
  (excluding deleted records). “Other Concerns” entries are compared by their
  specified text.
- A purpose marked *requires specification* rejects blank text.
- Time out must be later than time in.
- Deleting a record is a **soft delete**; it disappears from lists and exports
  but stays in the database and audit log.
- Timestamps are stored in UTC and displayed in **Asia/Manila**.

---

## Exports

The dashboard shows export links only to administrators. The currently applied
filters are passed to the exporter, so the downloaded file matches the screen.

| Format | Details |
|--------|---------|
| CSV | UTF-8 with BOM so Excel opens non-ASCII names correctly |
| PDF | A4 report with branded header, repeated table header, page footer |
| XLSX | Styled header, frozen top row, auto-filter, sensible column widths |

Add a format by subclassing `BaseExporter` and adding one entry to
`reports/exporters/factory.py`.

---

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Coverage areas:

- visitor registration, normalization, duplicates, per-type field clearing
- visit time in/out, duplicate/open-visit rules, custom concerns, auditing
- fixed-clock date boundaries and duration formatting
- CSV/PDF/XLSX exporters and factory behaviour
- authentication (username and email), role permissions, login throttling and
  auditing, kiosk/lookup APIs, registration, dashboard filters, exports, and
  soft delete
- production settings fail-closed checks and the demo-seeding guard

The suite uses a separate test database; it never touches `db.sqlite3`.

---

## Configuration

`.env` is loaded by `config/settings/base.py`.

| Variable | Default | Notes |
|----------|---------|-------|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | Use `config.settings.prod` in production |
| `DJANGO_SECRET_KEY` | insecure dev key | **Required** in production |
| `DJANGO_DEBUG` | `False` | `True` locally |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated, e.g. `https://visitra.sbc.edu.ph` |
| `POSTGRES_DB` / `_USER` / `_PASSWORD` / `_HOST` / `_PORT` | — | Setting `POSTGRES_DB` switches production to PostgreSQL |
| `DJANGO_SECURE_SSL_REDIRECT` | `True` in prod | Set `False` only for plain-HTTP LAN use |
| `DJANGO_ALLOW_SQLITE_PROD` | `False` | Production refuses SQLite unless this is `True` |
| `LOGIN_MAX_ATTEMPTS` | `5` | Failed sign-ins allowed before a temporary lockout |
| `LOGIN_LOCKOUT_SECONDS` | `900` | Lockout duration in seconds |
| `FIRESTORE_ENABLED` | `False` | `True` makes Firestore the system of record |
| `FIRESTORE_PROJECT` | `GOOGLE_CLOUD_PROJECT` | Google Cloud project id |
| `FIRESTORE_DATABASE` | `(default)` | Firestore database id |
| `FIRESTORE_COLLECTION_PREFIX` | `visitra` | Prefix for every collection |
| `FIRESTORE_BACKEND` | `firestore` | `memory` for offline/tests, `firestore` for real |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | Service-account JSON path; ADC is used when unset |
| `FIRESTORE_EMULATOR_HOST` | — | e.g. `127.0.0.1:8080` for the local emulator |

---

## Firestore (system of record)

Business data — purposes, visitors, visits, and the activity trail — lives in
Firestore when `FIRESTORE_ENABLED=True`. The SQL database is kept as a mirror /
backup, and **stays required** for Django auth, sessions, and the admin: Django
cannot run those on a document store.

```
Firestore (authoritative)  ──write──►  SQL mirror (backup, admin, fallback data)
        ▲                                        │
        └──────── sync_firestore ◄───────────────┘
```

### What is stored where

| Data | Firestore collection | SQL mirror |
|------|----------------------|------------|
| Purposes | `visitra_purposes` | `visits_purpose` |
| Visitors | `visitra_visitors` | `visitors_visitor` |
| Visits | `visitra_visits` | `visits_visit` |
| Activity trail | `visitra_activity` | `audit_activitylog` |
| Users, sessions, admin | — | `accounts_user`, `django_session`, ... |

Documents are self-contained: a visit stores the visitor's name, identifier and
type so dashboard/export reads never need a join. Datetimes are stored as UTC
and `visit_date` as an ISO date string.

### Enable it

1. Create a Google Cloud project, enable Firestore (Native mode), and create a
   service account with **Cloud Datastore User**.
2. Download the JSON key and point `GOOGLE_APPLICATION_CREDENTIALS` at it.
3. Set the variables in `.env`:

   ```dotenv
   FIRESTORE_ENABLED=True
   FIRESTORE_PROJECT=my-gcp-project
   FIRESTORE_DATABASE=(default)
   FIRESTORE_COLLECTION_PREFIX=visitra
   GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
   ```

4. Verify the connection, then backfill existing rows:

   ```powershell
   python manage.py check_firestore
   python manage.py sync_firestore --direction=to-firestore
   ```

5. Restart the app. New writes go to Firestore first, then to SQL.

Keep the service-account JSON out of version control: `firebase_credentials.json`,
`*credentials*.json` and `service-account*.json` are gitignored.

For local work without credentials use the emulator
(`FIRESTORE_EMULATOR_HOST=127.0.0.1:8080`) or the in-memory backend
(`FIRESTORE_BACKEND=memory`).

### Tests never touch the live project

`pytest.ini` uses `config/settings/test.py`, which forces
`FIRESTORE_ENABLED=False` and the in-memory backend. Without it, enabling
Firestore in `.env` would point the whole suite at production.

The Firestore-specific tests opt in through the `firestore` fixture. To run the
same tests against a real server, start the emulator and override the backend:

```powershell
$env:FIRESTORE_TEST_BACKEND = "firestore"
$env:FIRESTORE_EMULATOR_HOST = "127.0.0.1:8080"
$env:FIRESTORE_TEST_PROJECT = "demo-visitra"
python -m pytest tests/test_firestore_backend.py -q
```

Each test uses a unique collection prefix, so emulator runs stay isolated.

### Behaviour and limits

- **Write order:** Firestore first; the SQL mirror is best-effort. A mirror
  failure is logged and never loses the visit — run
  `sync_firestore --direction=to-sql` to repair the backup.
- **Reads** (kiosk lookup, dashboard, exports, summary counters) come from
  Firestore when enabled.
- **No silent fallback:** if Firestore is unreachable the request fails rather
  than reading stale backup data. Set `FIRESTORE_ENABLED=False` to deliberately
  run on SQL only.
- **Health probe:** `/healthz/` includes a `firestore` block and returns `503`
  when the system of record is unreachable, so uptime monitoring catches an
  outage that would otherwise look healthy.
- **Uniqueness:** duplicate-purpose and one-active-visit rules are enforced in
  the service layer before writing. Firestore has no partial unique indexes, so
  these checks are application-level; keep a single writer process (or accept
  the small race window that the SQL constraints still catch on the mirror).
- **Queries:** only single-field indexes are required. Filters and text search
  run in Python over the candidate documents, matching the old `icontains`
  behaviour. If the visits collection grows large, add composite indexes and
  push predicates into `visits/repository.py`.
- **Admin:** purposes and visitors edited in `/admin/` are mirrored to
  Firestore on save and delete. Visits are read-only there while Firestore is
  enabled, because the admin writes SQL directly and would bypass the system of
  record.
- **Security rules:** the server uses a service account (Admin SDK), so
  Firestore security rules do not apply to it. Lock the client SDK down
  separately if you add a web/mobile client later.

---

## Production notes

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings.prod"
python manage.py migrate
python manage.py collectstatic --no-input
waitress-serve --listen=0.0.0.0:8000 config.wsgi:application
```

- Put Nginx or IIS in front for TLS; keep `DJANGO_SECURE_SSL_REDIRECT=True`
  when HTTPS is terminated at the proxy.
- `DJANGO_SECRET_KEY` is mandatory: production refuses to start without it.
- Use PostgreSQL for multi-user deployments. Production refuses SQLite unless
  `DJANGO_ALLOW_SQLITE_PROD=True` is set deliberately for a single-machine
  deployment.
- Serve behind a trusted network and give each operator their own account so
  the audit trail is meaningful.
- Back up the database and media/static volumes; `db.sqlite3` and `.env` are
  intentionally git-ignored.

### Security defaults

CSRF protection, clickjacking protection, content-type sniffing protection,
same-site cookies, an 8-hour session for a kiosk shift, and role checks on every
staff/admin view and JSON endpoint. Usernames and email addresses are unique
case-insensitively, ambiguous username/email sign-ins are rejected, failed
attempts trigger a temporary lockout, and every successful or failed sign-in is
written to the audit trail. Visitor records never contain passwords.

---

## Known limitations (v1)

- Staff-operated kiosk only; no visitor self-service or public registration.
- No charts or analytics beyond the three dashboard counters.
- Deletions are soft deletes and are not restored from the UI (use the Django
  shell/admin database tools if needed).
- No photo capture, SMS/email notifications, or offline mode.
