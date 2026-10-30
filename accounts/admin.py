from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff", "is_active")
    list_filter = BaseUserAdmin.list_filter + ("role",)
    fieldsets = BaseUserAdmin.fieldsets + (
        (_("Visitra access"), {"fields": ("role",)}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        (_("Visitra access"), {"fields": ("email", "first_name", "last_name", "role")}),
    )

    def save_model(self, request, obj, form, change):
        # Django's admin requires is_staff on top of the business role. Grant it
        # automatically so a role="ADMIN" account is not silently locked out.
        if obj.is_admin_role:
            obj.is_staff = True
        super().save_model(request, obj, form, change)
