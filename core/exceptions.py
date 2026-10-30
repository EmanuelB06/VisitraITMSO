"""Base exception for business-rule violations.

Views translate these into user-facing messages, keeping HTTP concerns out of
the domain layer.
"""


class DomainError(Exception):
    """A request cannot be completed because a business rule was violated."""
