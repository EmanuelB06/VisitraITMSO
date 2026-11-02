from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from audit.services import record as record_activity

from .models import ApiToken, User


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "key_prefix", "is_active", "expires_at", "last_used_at", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "owner__username", "key_prefix")
    readonly_fields = ("key_prefix", "secret_hash", "owner", "scopes", "last_used_at", "created_at", "updated_at")
    fields = (
        "name",
        "owner",
        "scopes",
        "key_prefix",
        "secret_hash",
        "is_active",
        "expires_at",
        "last_used_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        previous = None
        if change and obj.pk:
            previous = ApiToken.objects.filter(pk=obj.pk).values_list("is_active", flat=True).first()

        super().save_model(request, obj, form, change)

        if previous and not obj.is_active:
            record_activity(
                actor=getattr(request, "user", None),
                action="API_TOKEN_REVOKED",
                entity_type="ApiToken",
                entity_id=str(obj.pk),
                name=obj.name,
                owner=str(obj.owner_id),
            )


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
