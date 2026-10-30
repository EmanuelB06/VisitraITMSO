from __future__ import annotations

from django.contrib import admin

from core.firestore import is_enabled
from core.records import VisitorRecord

from .models import Visitor
from .repository import VisitorRepository


def _record_from(obj: Visitor) -> VisitorRecord:
    return VisitorRecord(
        id=str(obj.pk),
        visitor_type=obj.visitor_type,
        name=obj.name,
        identifier=obj.identifier,
        student_type=obj.student_type,
        course=obj.course,
        year_level=obj.year_level,
        department=obj.department,
        organization=obj.organization,
        contact_number=obj.contact_number,
        is_active=obj.is_active,
        created_at=obj.created_at,
        updated_at=obj.updated_at,
    )


@admin.register(Visitor)
class VisitorAdmin(admin.ModelAdmin):
    list_display = ("name", "visitor_type", "identifier", "detail", "is_active", "created_at")
    list_filter = ("visitor_type", "student_type", "is_active")
    search_fields = ("name", "identifier", "organization", "department")
    readonly_fields = ("id", "created_at", "updated_at")
    fieldsets = (
        (None, {"fields": ("visitor_type", "name", "identifier", "is_active")}),
        ("Student", {"fields": ("student_type", "course", "year_level")}),
        ("Faculty", {"fields": ("department",)}),
        ("External", {"fields": ("organization", "contact_number")}),
        ("Meta", {"fields": ("id", "created_at", "updated_at")}),
    )

    @admin.display(description="Detail")
    def detail(self, obj):
        return obj.detail_line

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Keep the system of record in step with edits made in the admin.
        if is_enabled():
            VisitorRepository().save(_record_from(obj))

    def delete_model(self, request, obj):
        visitor_id = str(obj.pk)
        super().delete_model(request, obj)
        if is_enabled():
            VisitorRepository().delete(visitor_id)

    def delete_queryset(self, request, queryset):
        visitor_ids = [str(pk) for pk in queryset.values_list("pk", flat=True)]
        super().delete_queryset(request, queryset)
        if is_enabled():
            repository = VisitorRepository()
            for visitor_id in visitor_ids:
                repository.delete(visitor_id)
