from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.decorators.http import require_GET
from django.views.generic import FormView, TemplateView

from accounts.mixins import StaffRequiredMixin, api_staff_required
from visits.selectors import VisitSelector

from .exceptions import DomainError
from .forms import VisitorRegistrationForm
from .models import Visitor
from .qr import make_qr_payload, qr_svg
from .selectors import VisitorSelector
from .serializers import visitor_payload
from .services import VisitorService


class RegisterVisitorView(StaffRequiredMixin, FormView):
    template_name = "visitors/register.html"
    form_class = VisitorRegistrationForm
    success_url = reverse_lazy("visits:kiosk")
    service_class = VisitorService

    def get_service(self) -> VisitorService:
        return self.service_class()

    def form_valid(self, form):
        try:
            visitor = self.get_service().register(form.to_registration(), actor=self.request.user)
        except DomainError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        messages.success(
            self.request,
            f"{visitor.name} was registered successfully. Ask the visitor to photograph the QR code on the next screen.",
        )
        profile_url = reverse("visitors:detail", kwargs={"pk": visitor.pk})
        return redirect(f"{profile_url}?new=1")


@api_staff_required
@require_GET
def visitor_lookup(request):
    term = request.GET.get("q", "")
    visitor_type = request.GET.get("type", "")
    if visitor_type not in Visitor.Type.values:
        visitor_type = ""

    results = [visitor_payload(visitor) for visitor in VisitorSelector.lookup(term, visitor_type or None)]
    return JsonResponse({"results": results})


class VisitorDetailView(StaffRequiredMixin, TemplateView):
    """Visitor profile with the reusable QR badge and complete visit history."""

    template_name = "visitors/detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visitor = VisitorSelector.get_by_id(self.kwargs["pk"])
        if visitor is None:
            raise Http404("Visitor not found.")

        context.update(
            visitor=visitor,
            visits=VisitSelector.for_visitor(visitor.pk),
            qr_url=reverse("visitors:qr", kwargs={"pk": visitor.pk}),
            kiosk_url=f"{reverse('visits:kiosk')}?visitor={visitor.pk}",
            new_registration=self.request.GET.get("new") == "1",
        )
        return context


class VisitorQrView(StaffRequiredMixin, View):
    """Render the visitor's signed check-in token as an SVG QR code."""

    def get(self, request, pk):
        visitor = VisitorSelector.get_by_id(pk)
        if visitor is None:
            raise Http404("Visitor not found.")

        response = HttpResponse(
            qr_svg(make_qr_payload(visitor)),
            content_type="image/svg+xml",
        )
        response["Cache-Control"] = "private, max-age=3600"
        return response
