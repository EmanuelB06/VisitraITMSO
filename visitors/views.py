from __future__ import annotations

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.views.decorators.http import require_GET
from django.views.generic import FormView

from accounts.mixins import StaffRequiredMixin
from core.api import api_login_required

from .exceptions import DomainError
from .forms import VisitorRegistrationForm
from .models import Visitor
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

        messages.success(self.request, f"{visitor.name} was registered successfully.")
        kiosk_url = reverse("visits:kiosk")
        return redirect(f"{kiosk_url}?visitor={visitor.pk}")


@api_login_required
@require_GET
def visitor_lookup(request):
    term = request.GET.get("q", "")
    visitor_type = request.GET.get("type", "")
    if visitor_type not in Visitor.Type.values:
        visitor_type = ""

    results = [visitor_payload(visitor) for visitor in VisitorSelector.lookup(term, visitor_type or None)]
    return JsonResponse({"results": results})
