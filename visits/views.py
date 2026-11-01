"""Kiosk screens and JSON endpoints for time in / time out."""

from __future__ import annotations

from django.http import JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.mixins import StaffRequiredMixin, api_staff_required
from core.api import first_form_error, json_error, parse_json_body
from core.exceptions import DomainError
from visitors.selectors import VisitorSelector
from visitors.serializers import visitor_payload

from .forms import VisitTimeInForm
from .selectors import PurposeSelector, VisitSelector
from .serializers import visit_payload
from .services import VisitService


@method_decorator(ensure_csrf_cookie, name="dispatch")
class KioskView(StaffRequiredMixin, TemplateView):
    template_name = "visits/kiosk.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        purposes = PurposeSelector.list_active()
        prefill = VisitorSelector.get_by_id(self.request.GET.get("visitor"))

        context["purposes"] = purposes
        context["prefill"] = prefill
        context["bootstrap"] = {
            "purposes": [
                {
                    "id": str(purpose.pk),
                    "name": purpose.name,
                    "requires_specification": purpose.requires_specification,
                }
                for purpose in purposes
            ],
            "visitor": visitor_payload(prefill) if prefill else None,
            "urls": {
                "lookup": reverse("visitors:lookup"),
                "time_in": reverse("visits:time-in"),
                "active": reverse("visits:active"),
            },
        }
        return context


@api_staff_required
@require_POST
def time_in(request):
    payload = parse_json_body(request)
    if payload is None:
        return json_error("Invalid JSON body.")

    form = VisitTimeInForm(payload)
    if not form.is_valid():
        return json_error(first_form_error(form))

    visitor = VisitorSelector.get_by_id(form.cleaned_data["visitor_id"])
    if visitor is None:
        return json_error("Visitor not found.", status=404)

    purpose = PurposeSelector.get_active(form.cleaned_data["purpose_id"])
    if purpose is None:
        return json_error("Purpose not found.", status=404)

    try:
        visit = VisitService().time_in(
            visitor=visitor,
            purpose=purpose,
            custom_purpose=form.cleaned_data["custom_purpose"],
            actor=request.user,
        )
    except DomainError as exc:
        return json_error(str(exc), status=409)

    return JsonResponse({"visit": visit_payload(visit)}, status=201)


@api_staff_required
@require_POST
def time_out(request, pk):
    visit = VisitSelector.get_visible(pk)
    if visit is None:
        return json_error("Visit not found.", status=404)
    try:
        visit = VisitService().time_out(visit, actor=request.user)
    except DomainError as exc:
        return json_error(str(exc), status=409)
    return JsonResponse({"visit": visit_payload(visit)})


@api_staff_required
def active_visits(request):
    """Used by the kiosk to show who is currently inside (optional refresh)."""
    visits = VisitSelector.active(limit=50)
    return JsonResponse({"visits": [visit_payload(visit) for visit in visits]})
