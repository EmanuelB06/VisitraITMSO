from __future__ import annotations

from visitors.forms import VisitorRegistrationForm


class VisitorImportRowForm(VisitorRegistrationForm):
    """Registration form for server-to-server bulk imports.

    Consent is collected once for the import (or covered by the source system),
    not repeated on every row.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop("consent", None)
