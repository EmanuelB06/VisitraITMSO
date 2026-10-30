"""Views for the public landing page and health probe."""

from __future__ import annotations

from django.http import JsonResponse
from django.utils import timezone
from django.views.generic import TemplateView

from core.firestore import health as firestore_health
from core.firestore import is_enabled


def greeting_for_hour(hour: int) -> str:
    if 5 <= hour <= 11:
        return "Good morning"
    if 12 <= hour <= 17:
        return "Good afternoon"
    return "Good evening"


class HomeView(TemplateView):
    template_name = "home/index.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        now = timezone.localtime()
        context["greeting"] = greeting_for_hour(now.hour)
        context["current_year"] = now.year
        return context


def health(request):
    """Liveness probe.

    When Firestore is the system of record, a process that cannot reach it
    cannot serve business pages, so report ``503`` instead of a misleading
    ``ok``. With Firestore disabled this stays a plain liveness check.
    """
    payload = {"status": "ok", "time": timezone.now().isoformat()}
    if not is_enabled():
        return JsonResponse(payload)

    report = firestore_health()
    payload["firestore"] = {
        "ok": report["ok"],
        "backend": report["backend"],
        "project": report["project"],
        "error": report["error"],
    }
    if not report["ok"]:
        payload["status"] = "degraded"
        return JsonResponse(payload, status=503)
    return JsonResponse(payload)
