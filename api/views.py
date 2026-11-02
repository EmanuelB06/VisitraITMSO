"""Versioned JSON API for the visitor directory."""

from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from accounts.api_auth import api_auth_required
from accounts.models import ApiToken
from audit.services import record as record_activity
from core.api import first_form_error, json_error, parse_json_body
from core.exceptions import DomainError
from visitors.exceptions import DuplicateVisitorError
from visitors.forms import VisitorRegistrationForm
from visitors.models import Visitor
from visitors.selectors import VisitorSelector
from visitors.serializers import visitor_directory_payload
from visitors.services import VisitorService
from visits.selectors import PurposeSelector
from visits.serializers import purpose_payload

from .forms import VisitorImportRowForm

BULK_LIMIT = 500
BULK_MODES = {"upsert", "create_only", "dry_run"}


@api_auth_required(ApiToken.Scope.PURPOSES_READ)
@require_GET
def purposes(request):
    return JsonResponse(
        {"purposes": [purpose_payload(purpose) for purpose in PurposeSelector.list_active()]}
    )


@api_auth_required(ApiToken.Scope.VISITORS_READ)
@require_GET
def visitors_search(request):
    term = (request.GET.get("q") or "").strip()
    if not term:
        return json_error("Query parameter 'q' is required.")

    visitor_type = (request.GET.get("type") or "").strip().upper()
    if visitor_type and visitor_type not in Visitor.Type.values:
        return json_error("Unknown visitor type.")

    raw_limit = request.GET.get("limit", "8")
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return json_error("limit must be an integer.")
    if not 1 <= limit <= 50:
        return json_error("limit must be between 1 and 50.")

    results = VisitorSelector.lookup(term, visitor_type or None, limit=limit)
    return JsonResponse({"results": [visitor_directory_payload(visitor) for visitor in results]})


@api_auth_required(ApiToken.Scope.VISITORS_READ)
@require_GET
def visitor_detail(request, visitor_id):
    visitor = VisitorSelector.get_by_id(visitor_id)
    if visitor is None:
        return json_error("Visitor not found.", status=404)
    return JsonResponse({"visitor": visitor_directory_payload(visitor)})


@api_auth_required(ApiToken.Scope.VISITORS_WRITE)
@require_POST
def visitors_register(request):
    payload = parse_json_body(request)
    if payload is None:
        return json_error("Invalid JSON body.")

    form = VisitorRegistrationForm(payload)
    if not form.is_valid():
        return json_error(first_form_error(form))

    try:
        visitor = VisitorService().register(form.to_registration(), actor=request.user)
    except DuplicateVisitorError as exc:
        return json_error(str(exc), status=409)
    except DomainError as exc:
        return json_error(str(exc))

    return JsonResponse({"visitor": visitor_directory_payload(visitor)}, status=201)


def visitors(request):
    if request.method == "POST":
        return visitors_register(request)
    return visitors_search(request)


@api_auth_required(ApiToken.Scope.VISITORS_BULK, require_admin=True)
@require_POST
def visitors_bulk(request):
    payload = parse_json_body(request)
    if payload is None:
        return json_error("Invalid JSON body.")

    rows = payload.get("visitors")
    if not isinstance(rows, list) or not rows:
        return json_error("'visitors' must be a non-empty list.")
    if len(rows) > BULK_LIMIT:
        return json_error(f"A bulk import is limited to {BULK_LIMIT} visitors.")

    mode = payload.get("mode", "upsert")
    if mode not in BULK_MODES:
        return json_error("mode must be upsert, create_only, or dry_run.")

    source = payload.get("source", "api")
    if not isinstance(source, str) or not source.strip():
        return json_error("source must be a non-empty string.")
    source = source.strip()[:80]

    service = VisitorService()
    created = updated = skipped = 0
    failed = []

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            failed.append({"index": index, "identifier": "", "error": "Row must be an object."})
            continue

        form = VisitorImportRowForm(row)
        if not form.is_valid():
            failed.append(
                {
                    "index": index,
                    "identifier": str(row.get("identifier", ""))[:40],
                    "error": first_form_error(form),
                }
            )
            continue

        try:
            result = service.sync(
                form.to_registration(),
                actor=request.user,
                mode=mode,
                source=source,
                require_identifier=True,
                audit=False,
            )
        except DomainError as exc:
            failed.append(
                {
                    "index": index,
                    "identifier": str(row.get("identifier", ""))[:40],
                    "error": str(exc),
                }
            )
            continue

        created += int(result.created)
        updated += int(result.updated)
        skipped += int(result.skipped)

    if mode != "dry_run":
        record_activity(
            actor=request.user,
            action="VISITOR_IMPORTED",
            entity_type="Visitor",
            source=source,
            mode=mode,
            received=len(rows),
            created=created,
            updated=updated,
            skipped=skipped,
            failed=len(failed),
        )

    response = {
        "source": source,
        "mode": mode,
        "received": len(rows),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": failed,
    }
    return JsonResponse(response, status=207 if failed else 200)
