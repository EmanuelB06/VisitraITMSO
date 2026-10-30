"""Domain exceptions for the visitors app."""

from core.exceptions import DomainError


class DuplicateVisitorError(DomainError):
    """A visitor with the same identifier already exists."""


class InvalidVisitorError(DomainError):
    """The supplied visitor data is incomplete or malformed."""
