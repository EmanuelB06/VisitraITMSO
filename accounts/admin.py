from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from audit.services import record as record_activity

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
        previous = None
        if change and obj.pk:
            previous = (
                User.objects.filter(pk=obj.pk)
                .values("role", "is_staff", "is_superuser")
                .first()
            )

        # Django's admin requires is_staff on top of the business role. Keep it
        # exactly aligned so a demoted administrator cannot keep admin access.
        obj.is_staff = obj.is_admin_role
        super().save_model(request, obj, form, change)

        current = {
            "role": obj.role,
            "is_staff": obj.is_staff,
            "is_superuser": obj.is_superuser,
        }
        if previous != current:
            record_activity(
                actor=getattr(request, "user", None),
                action="ACCESS_CHANGED",
                entity_type="User",
                entity_id=str(obj.pk),
                previous=previous,
                current=current,
            )
