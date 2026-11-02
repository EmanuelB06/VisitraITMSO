from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .accounts import AUTH_INACTIVE, AUTH_UNVERIFIED, authenticate_visitor, register_visitor_account
from .models import Visitor
from .policies import get_policy
from .services import VisitorRegistration

TEXT = {"class": "input"}
SELECT = {"class": "select"}


class VisitorRegistrationForm(forms.Form):
    """Form for staff to register visitors (existing functionality)"""
    
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


class VisitorSelfRegistrationForm(forms.Form):
    """Form for visitors to create their own accounts with login credentials"""
    
    visitor_type = forms.ChoiceField(
        choices=Visitor.Type.choices,
        label="Visitor Type",
        initial=Visitor.Type.STUDENT,
        widget=forms.RadioSelect(attrs={"class": "segmented-input"}),
    )
    name = forms.CharField(
        max_length=120,
        label="Full Name",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. Maria Santos", "autocomplete": "name"}),
    )
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={**TEXT, "placeholder": "you@example.com", "autocomplete": "email"}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={**TEXT, "placeholder": "Create a password", "autocomplete": "new-password"}),
        min_length=8,
        help_text="Must be at least 8 characters long.",
    )
    confirm_password = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={**TEXT, "placeholder": "Confirm your password", "autocomplete": "new-password"}),
    )
    
    # Conditional fields based on visitor type
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
        label="Student Level",
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
        label="Year / Grade Level",
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
        label="Contact Number",
        widget=forms.TextInput(attrs={**TEXT, "placeholder": "e.g. 0917 000 0000", "inputmode": "tel"}),
    )
    
    consent = forms.BooleanField(
        required=True,
        label="I agree to the data privacy policy and terms of service.",
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
    )

    def clean_email(self):
        """Normalise the email and ensure it is not already in use."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email and Visitor.objects.by_email(email).exists():
            raise ValidationError(
                "A visitor with this email already exists. "
                "Please use a different email or try logging in."
            )
        return email

    def clean(self):
        cleaned = super().clean()
        
        # Validate password match
        password = cleaned.get("password")
        confirm_password = cleaned.get("confirm_password")
        
        if password and confirm_password:
            if password != confirm_password:
                self.add_error("confirm_password", "Passwords do not match.")
        
        # Validate visitor type specific fields
        visitor_type = cleaned.get("visitor_type")
        if visitor_type:
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

    def save(self) -> Visitor:
        """Create the visitor profile through the service and add credentials."""
        data = self.cleaned_data
        return register_visitor_account(
            self.to_registration(),
            email=data["email"],
            password=data["password"],
            phone_number=data.get("contact_number", ""),
        )


class VisitorLoginForm(forms.Form):
    """Login form for visitors"""
    
    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(attrs={
            **TEXT,
            "placeholder": "your@email.com",
            "autocomplete": "email",
            "autofocus": True,
        }),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            **TEXT,
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
        }),
    )
    remember_me = forms.BooleanField(
        required=False,
        label="Remember me",
        widget=forms.CheckboxInput(attrs={"class": "checkbox"}),
    )

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get("email")
        password = cleaned_data.get("password")

        if not email or not password:
            return cleaned_data

        visitor, reason = authenticate_visitor(email, password)

        if reason == AUTH_INACTIVE:
            raise ValidationError(
                "Your account has been deactivated. Please contact ITMSO.",
                code="inactive",
            )
        if reason == AUTH_UNVERIFIED:
            raise ValidationError(
                "Your account is not verified yet. Please contact ITMSO.",
                code="unverified",
            )
        if visitor is None:
            raise ValidationError(
                "Invalid email or password.",
                code="invalid_login",
            )

        cleaned_data["visitor"] = visitor
        return cleaned_data


class VisitorProfileUpdateForm(forms.ModelForm):
    """Form for visitors to update their profile"""
    
    class Meta:
        model = Visitor
        fields = [
            'name',
            'email',
            'phone_number',
            'identifier',
            'student_type',
            'course',
            'year_level',
            'department',
            'organization',
            'contact_number',
        ]
        widgets = {
            'name': forms.TextInput(attrs={**TEXT, "autocomplete": "name"}),
            'email': forms.EmailInput(attrs={**TEXT, "autocomplete": "email"}),
            'phone_number': forms.TextInput(attrs={**TEXT, "inputmode": "tel"}),
            'identifier': forms.TextInput(attrs=TEXT),
            'student_type': forms.Select(attrs=SELECT),
            'course': forms.TextInput(attrs=TEXT),
            'year_level': forms.TextInput(attrs=TEXT),
            'department': forms.TextInput(attrs=TEXT),
            'organization': forms.TextInput(attrs=TEXT),
            'contact_number': forms.TextInput(attrs={**TEXT, "inputmode": "tel"}),
        }

    def clean_email(self):
        """Ensure the email stays unique when updating the profile."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if email:
            queryset = Visitor.objects.by_email(email)
            if self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            if queryset.exists():
                raise ValidationError("This email is already in use by another visitor.")
        return email


class VisitorPasswordChangeForm(forms.Form):
    """Form for visitors to change their password"""
    
    current_password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(attrs={**TEXT, "autocomplete": "current-password"}),
    )
    new_password = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={**TEXT, "autocomplete": "new-password"}),
        min_length=8,
        help_text="Must be at least 8 characters long.",
    )
    confirm_new_password = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={**TEXT, "autocomplete": "new-password"}),
    )

    def __init__(self, *args, **kwargs):
        self.visitor = kwargs.pop('visitor', None)
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        """Verify current password"""
        current_password = self.cleaned_data.get('current_password')
        if self.visitor and not self.visitor.check_password(current_password):
            raise ValidationError("Current password is incorrect.")
        return current_password

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm_new_password = cleaned_data.get("confirm_new_password")
        
        if new_password and confirm_new_password:
            if new_password != confirm_new_password:
                self.add_error("confirm_new_password", "New passwords do not match.")
        
        return cleaned_data

    def save(self):
        """Update the visitor's password."""
        new_password = self.cleaned_data["new_password"]
        self.visitor.set_password(new_password)
        self.visitor.save(update_fields=["password_hash", "updated_at"])
        return self.visitor