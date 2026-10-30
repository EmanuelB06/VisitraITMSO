"""Domain exceptions for visit logging."""

from core.exceptions import DomainError


class OpenVisitError(DomainError):
    """The visitor already has a visit in progress."""


class DuplicateVisitError(DomainError):
    """The same purpose was already recorded for this visitor today."""


class VisitAlreadyClosedError(DomainError):
    """The visit has already been timed out."""


class InvalidPurposeError(DomainError):
    """The selected purpose is not usable for this visit."""
