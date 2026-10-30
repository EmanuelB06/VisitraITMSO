from __future__ import annotations

from django import forms


class VisitTimeInForm(forms.Form):
    visitor_id = forms.UUIDField()
    purpose_id = forms.UUIDField()
    custom_purpose = forms.CharField(required=False, max_length=200)
