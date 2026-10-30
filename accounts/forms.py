from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError

from .throttle import is_locked_out, lockout_message


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(
            attrs={
                "class": "input",
                "autofocus": True,
                "autocomplete": "username",
                "placeholder": "you@sbc.edu.ph",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "input",
                "autocomplete": "current-password",
                "placeholder": "Enter your password",
            }
        ),
    )

    def clean(self):
        username = (self.data.get("username") or "").strip()
        if username and is_locked_out(self.request, username):
            raise ValidationError(lockout_message(), code="login_locked")
        return super().clean()
