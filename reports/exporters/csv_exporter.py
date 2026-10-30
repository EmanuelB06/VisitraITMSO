from __future__ import annotations

import csv
import io

from django.utils import timezone

from .base import BaseExporter

HEADERS = ("Name", "Identifier", "Type", "Purpose", "Date", "Time In", "Time Out", "Duration")


class CsvExporter(BaseExporter):
    key = "csv"
    label = "CSV"
    extension = "csv"
    content_type = "text/csv; charset=utf-8"

    def build(self, visits, generated_at) -> bytes:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(HEADERS)
        for visit in visits:
            writer.writerow(
                (
                    visit.visitor.name,
                    visit.visitor.identifier,
                    visit.visitor.type_label,
                    visit.display_purpose,
                    visit.visit_date.isoformat(),
                    timezone.localtime(visit.time_in).strftime("%Y-%m-%d %I:%M %p"),
                    timezone.localtime(visit.time_out).strftime("%Y-%m-%d %I:%M %p")
                    if visit.time_out
                    else "",
                    visit.duration_label,
                )
            )
        # UTF-8 BOM keeps Excel happy with non-ASCII names.
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")
