"""Exporter registry / factory.

The view asks for a format by key; adding a format means adding one class and
one entry here.
"""

from __future__ import annotations

from .base import BaseExporter, ExportFile, UnknownFormatError
from .csv_exporter import CsvExporter
from .pdf_exporter import PdfExporter
from .xlsx_exporter import XlsxExporter

EXPORTERS: dict[str, BaseExporter] = {
    exporter.key: exporter
    for exporter in (CsvExporter(), PdfExporter(), XlsxExporter())
}

DEFAULT_FORMAT = "csv"


def get_exporter(key: str | None) -> BaseExporter:
    try:
        return EXPORTERS[(key or DEFAULT_FORMAT).lower()]
    except KeyError as exc:
        raise UnknownFormatError(key or DEFAULT_FORMAT) from exc


__all__ = [
    "EXPORTERS",
    "DEFAULT_FORMAT",
    "BaseExporter",
    "ExportFile",
    "UnknownFormatError",
    "get_exporter",
]
