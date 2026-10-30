from __future__ import annotations

from django import forms

from .models import Visitor
from .policies import get_policy
from .services import VisitorRegistration

TEXT = {"class": "input"}
SELECT = {"class": "select"}


class VisitorRegistrationForm(forms.Form):
    visitor_type = forms.ChoiceField(
        choices=Visitor.Type.choices,
        initial=Visitor.Type.STUDENT,
        widget=forms.RadioSelect(attrs={"class": "segmented-input"}),
    )
    name = forms.CharField(
        max_length=120,
        label="Full name",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Maria Santos", "autocomplete": "name"}),
    )
    identifier = forms.CharField(
        max_length=40,
        required=False,
        label="Student / Employee ID",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. 2024-00123"}),
    )

    student_type = forms.ChoiceField(
        choices=Visitor.StudentType.choices,
        required=False,
        initial=Visitor.StudentType.COLLEGE,
        label="Student level",
        widget=forms.Select(attrs=SELECT),
    )
    course = forms.CharField(
        max_length=80,
        required=False,
        label="Course",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. BS Information Technology"}),
    )
    year_level = forms.CharField(
        max_length=40,
        required=False,
        label="Year / grade level",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. 2nd Year or Grade 10"}),
    )
    department = forms.CharField(
        max_length=120,
        required=False,
        label="Department",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. College of Information Technology"}),
    )
    organization = forms.CharField(
        max_length=120,
        required=False,
        label="Organization",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. DepEd, Parent, Supplier"}),
    )
    contact_number = forms.CharField(
        max_length=30,
        required=False,
        label="Contact number",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. 0917 000 0000", "inputmode": "tel"}),
    )
    consent = forms.BooleanField(
        required=True,
        label="The visitor has read and agreed to the SBC data privacy policy.",
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
    )

    def clean(self):
        cleaned = super().clean()
        visitor_type = cleaned.get("visitor_type")
        if not visitor_type:
            return cleaned

        policy = get_policy(visitor_type)
        missing = policy.missing_fields(cleaned)
        if "name" in missing:
            self.add_error("name", "Full name is required.")
        if "identifier" in missing:
            self.add_error("identifier", f"{policy.identifier_label} is required.")

        if visitor_type == Visitor.Type.EXTERNAL:
            cleaned["identifier"] = (cleaned.get("identifier") or "").strip()

        return cleaned

    def to_registration(self) -> VisitorRegistration:
        data = self.cleaned_data
        return VisitorRegistration(
            visitor_type=data["visitor_type"],
            name=data["name"],
            identifier=data.get("identifier", ""),
            student_type=data.get("student_type", ""),
            course=data.get("course", ""),
            year_level=data.get("year_level", ""),
            department=data.get("department", ""),
            organization=data.get("organization", ""),
            contact_number=data.get("contact_number", ""),
        )
