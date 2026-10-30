"""Exporter abstraction.

Every format implements the same tiny contract, so the export view never needs
to know which library produces the bytes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.utils import timezone


@dataclass(frozen=True)
class ExportFile:
    filename: str
    content_type: str
    content: bytes


class BaseExporter(ABC):
    key: str
    label: str
    extension: str
    content_type: str

    def export(self, visits, generated_at=None) -> ExportFile:
        generated_at = generated_at or timezone.localtime()
        visits = list(visits)
        content = self.build(visits, generated_at)
        filename = f"visitra_{generated_at:%Y%m%d_%H%M}.{self.extension}"
        return ExportFile(filename=filename, content_type=self.content_type, content=content)

    @abstractmethod
    def build(self, visits, generated_at) -> bytes:
        """Return the complete file as bytes."""


class UnknownFormatError(KeyError):
    """The requested export format is not registered."""
