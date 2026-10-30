from __future__ import annotations

import io

import pytest
from openpyxl import load_workbook

from reports.exporters.base import UnknownFormatError
from reports.exporters.csv_exporter import CsvExporter
from reports.exporters.factory import DEFAULT_FORMAT, EXPORTERS, get_exporter
from reports.exporters.pdf_exporter import PdfExporter
from reports.exporters.xlsx_exporter import XlsxExporter
from visits.services import VisitService
from visitors.models import Visitor
from visitors.services import VisitorRegistration, VisitorService

from .conftest import FixedClock, manila


@pytest.fixture
def visits(db):
    clock = FixedClock(manila(2026, 3, 10, 9, 0))
    service = VisitService(clock=clock)
    visitor = VisitorService().register(
        VisitorRegistration(
            visitor_type=Visitor.Type.STUDENT,
            name="Maria Santos",
            identifier="2024-00123",
            course="BS Information Technology",
            year_level="2nd Year",
        )
    )
    from visits.models import Purpose

    purpose = Purpose.objects.create(name="MS 365 Assistance")
    visit = service.time_in(visitor=visitor, purpose=purpose)
    clock.set(manila(2026, 3, 10, 10, 30))
    return [service.time_out(visit)]


def test_registry_contains_every_format():
    assert set(EXPORTERS) == {"csv", "pdf", "xlsx"}
    assert get_exporter("csv") is EXPORTERS["csv"]
    assert get_exporter(None) is EXPORTERS[DEFAULT_FORMAT]
    assert get_exporter("PDF") is EXPORTERS["pdf"]


def test_unknown_format_raises():
    with pytest.raises(UnknownFormatError):
        get_exporter("docx")


@pytest.mark.django_db
def test_csv_export(visits):
    result = CsvExporter().export(visits)

    assert result.filename.endswith(".csv")
    assert result.content_type.startswith("text/csv")
    text = result.content.decode("utf-8-sig")
    assert text.startswith("Name,Identifier,Type,Purpose,Date,Time In,Time Out,Duration")
    assert "Maria Santos" in text
    assert "2024-00123" in text
    assert "MS 365 Assistance" in text
    assert "1h 30m" in text


@pytest.mark.django_db
def test_pdf_export(visits):
    result = PdfExporter().export(visits)

    assert result.filename.endswith(".pdf")
    assert result.content_type == "application/pdf"
    assert result.content.startswith(b"%PDF")
    assert b"VisitraITMSO" in result.content


@pytest.mark.django_db
def test_xlsx_export(visits):
    result = XlsxExporter().export(visits)

    assert result.filename.endswith(".xlsx")
    assert result.content_type.startswith("application/vnd.openxmlformats")
    assert result.content.startswith(b"PK")

    workbook = load_workbook(io.BytesIO(result.content))
    sheet = workbook.active
    assert sheet.title == "Visits"
    assert [cell.value for cell in sheet[1]] == [
        "Name",
        "Identifier",
        "Type",
        "Purpose",
        "Date",
        "Time In",
        "Time Out",
        "Duration",
    ]
    assert sheet["A2"].value == "Maria Santos"
    assert sheet.freeze_panes == "A2"


@pytest.mark.django_db
def test_empty_exports_still_produce_valid_files():
    assert CsvExporter().export([]).content.startswith(b"\xef\xbb\xbf")
    assert PdfExporter().export([]).content.startswith(b"%PDF")
    assert XlsxExporter().export([]).content.startswith(b"PK")
