from __future__ import annotations

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import FormView, TemplateView

from accounts.mixins import StaffRequiredMixin, api_staff_required
from visits.selectors import VisitSelector

from .accounts import (
    clear_visitor_session,
    current_visitor,
    login_visitor,
    logout_visitor,
)
from .exceptions import DomainError
from .forms import (
    VisitorLoginForm,
    VisitorPasswordChangeForm,
    VisitorProfileUpdateForm,
    VisitorRegistrationForm,
    VisitorSelfRegistrationForm,
)
from .models import Visitor
from .qr import make_qr_payload, qr_svg
from .selectors import VisitorSelector
from .serializers import visitor_payload
from .services import VisitorService


class RegisterVisitorView(StaffRequiredMixin, FormView):
    """Staff registers a visitor (existing functionality)."""

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


# ============================================================================
# Visitor self-service: registration, login, dashboard, profile
# ============================================================================


def _safe_next(request, fallback: str) -> str:
    """Only follow a ``next`` value that points back to this host."""
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return fallback


class VisitorSessionMixin:
    """Attach the signed-in visitor or send the request to the login page."""

    def dispatch(self, request, *args, **kwargs):
        visitor = current_visitor(request)
        if visitor is None:
            messages.warning(request, "Please sign in to continue.")
            login_url = reverse("visitors:login")
            return redirect(f"{login_url}?next={request.get_full_path()}")
        self.visitor = visitor
        return super().dispatch(request, *args, **kwargs)


class VisitorRegisterView(FormView):
    """Let a visitor create a profile and sign-in credentials."""

    template_name = "visitors/visitor_register.html"
    form_class = VisitorSelfRegistrationForm
    success_url = reverse_lazy("visitors:dashboard")

    def dispatch(self, request, *args, **kwargs):
        if current_visitor(request) is not None:
            messages.info(request, "You are already signed in.")
            return redirect("visitors:dashboard")
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        try:
            visitor = form.save()
        except DomainError as exc:
            form.add_error(None, str(exc))
            return self.form_invalid(form)

        login_visitor(self.request, visitor)
        messages.success(
            self.request,
            f"Welcome, {visitor.name}! Your visitor account is ready.",
        )
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Create visitor account"
        context["page_subtitle"] = (
            "Register once to view your visit history and keep your details up to date."
        )
        return context


class VisitorLoginView(FormView):
    """Visitor login page (email + password)."""

    template_name = "visitors/visitor_login.html"
    form_class = VisitorLoginForm

    def dispatch(self, request, *args, **kwargs):
        if current_visitor(request) is not None:
            return redirect(self.get_success_url())
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        return _safe_next(self.request, reverse("visitors:dashboard"))

    def form_valid(self, form):
        visitor = form.cleaned_data["visitor"]
        login_visitor(
            self.request,
            visitor,
            remember_me=bool(form.cleaned_data.get("remember_me")),
        )
        messages.success(self.request, f"Welcome back, {visitor.name}!")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Visitor sign in"
        context["page_subtitle"] = "Sign in to view your visit history and profile."
        return context


@require_POST
def visitor_logout(request):
    """Sign the visitor out and discard the session."""
    if request.session.get("visitor_id"):
        visitor_name = request.session.get("visitor_name", "Visitor")
        logout_visitor(request)
        messages.info(request, f"Goodbye, {visitor_name}! You have been signed out.")
    else:
        clear_visitor_session(request)
    return redirect("home")


class VisitorDashboardView(VisitorSessionMixin, TemplateView):
    """Visitor dashboard: profile summary plus visit history."""

    template_name = "visitors/visitor_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        visitor = self.visitor
        visits = VisitSelector.for_visitor(visitor.pk)

        context.update(
            visitor=visitor,
            visits=visits,
            recent_visits=visits[:5],
            total_visits=len(visits),
        )
        return context


class VisitorProfileView(VisitorSessionMixin, FormView):
    """Let a signed-in visitor update their own profile."""

    template_name = "visitors/visitor_profile.html"
    form_class = VisitorProfileUpdateForm
    success_url = reverse_lazy("visitors:dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.visitor
        return kwargs

    def form_valid(self, form):
        visitor = form.save()
        self.request.session["visitor_name"] = visitor.name
        self.request.session["visitor_email"] = visitor.email
        messages.success(self.request, "Your profile has been updated successfully.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["visitor"] = self.visitor
        return context


class VisitorPasswordChangeView(VisitorSessionMixin, FormView):
    """Let a signed-in visitor change their password."""

    template_name = "visitors/visitor_password_change.html"
    form_class = VisitorPasswordChangeForm
    success_url = reverse_lazy("visitors:dashboard")

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["visitor"] = self.visitor
        return kwargs

    def form_valid(self, form):
        form.save()
        messages.success(self.request, "Your password has been changed successfully.")
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["visitor"] = self.visitor
        return context
