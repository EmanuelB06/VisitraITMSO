"""Admin dashboard, exports, and record deletion."""

from __future__ import annotations

import io

from django.contrib import messages
from django.core.paginator import Paginator
from django.http import FileResponse, Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from accounts.mixins import AdminRequiredMixin, StaffRequiredMixin
from audit.services import record as record_activity
from visits.selectors import VisitFilter, VisitSelector
from visits.services import VisitService

from .exporters.base import UnknownFormatError
from .exporters.factory import get_exporter

PAGE_SIZE = 20


class DashboardView(StaffRequiredMixin, TemplateView):
    template_name = "reports/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        filters = VisitFilter.from_query(self.request.GET)
        queryset = VisitSelector.apply(filters)
        paginator = Paginator(queryset, PAGE_SIZE)
        page_obj = paginator.get_page(self.request.GET.get("page"))

        context.update(
            filters=filters,
            page_obj=page_obj,
            filtered_total=paginator.count,
            summary=VisitSelector.summary(),
            status_choices=VisitFilter.STATUS_CHOICES,
            type_choices=VisitFilter.TYPE_CHOICES,
            export_query=filters.as_query(),
            has_filters=filters.is_filtered,
        )
        return context


class DeleteVisitView(AdminRequiredMixin, View):
    def post(self, request, pk):
        visit = VisitSelector.get_visible(pk)
        if visit is None:
            raise Http404("Visit not found.")
        VisitService().soft_delete(visit, actor=request.user)
        messages.success(request, f"Record for {visit.visitor.name} was deleted.")
        target = reverse("reports:dashboard")
        query = request.POST.get("query", "").strip()
        return redirect(f"{target}?{query}" if query else target)


class ExportView(AdminRequiredMixin, View):
    def get(self, request):
        filters = VisitFilter.from_query(request.GET)
        try:
            exporter = get_exporter(request.GET.get("format"))
        except UnknownFormatError as exc:
            raise Http404("Unknown export format.") from exc

        visits = list(VisitSelector.apply(filters))
        result = exporter.export(visits)

        record_activity(
            actor=request.user,
            action="EXPORT",
            entity_type="Visit",
            format=exporter.key,
            count=len(visits),
            filters=filters.as_query(),
        )

        return FileResponse(
            io.BytesIO(result.content),
            as_attachment=True,
            filename=result.filename,
            content_type=result.content_type,
        )
