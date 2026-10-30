from __future__ import annotations

from django.contrib import admin

from core.firestore import is_enabled
from core.records import PurposeRecord

from .models import Purpose, Visit
from .repository import PurposeRepository


@admin.register(Purpose)
class PurposeAdmin(admin.ModelAdmin):
    list_display = ("name", "requires_specification", "is_active", "sort_order")
    list_editable = ("is_active", "sort_order")
    list_filter = ("is_active", "requires_specification")
    search_fields = ("name",)
    ordering = ("sort_order", "name")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # The SQL row is the backup; keep the system of record in step.
        if is_enabled():
            PurposeRepository().save(
                PurposeRecord(
                    id=str(obj.pk),
                    name=obj.name,
                    requires_specification=obj.requires_specification,
                    is_active=obj.is_active,
                    sort_order=obj.sort_order,
                )
            )

    def delete_model(self, request, obj):
        purpose_id = str(obj.pk)
        super().delete_model(request, obj)
        if is_enabled():
            PurposeRepository().delete(purpose_id)

    def delete_queryset(self, request, queryset):
        ids = [str(pk) for pk in queryset.values_list("pk", flat=True)]
        super().delete_queryset(request, queryset)
        if is_enabled():
            repository = PurposeRepository()
            for purpose_id in ids:
                repository.delete(purpose_id)


@admin.register(Visit)
class VisitAdmin(admin.ModelAdmin):
    list_display = ("visitor", "display_purpose", "time_in", "time_out", "logged_by", "deleted_at")
    list_filter = ("purpose", "visitor__visitor_type", "deleted_at")
    search_fields = ("visitor__name", "visitor__identifier", "purpose_text")
    date_hierarchy = "visit_date"
    autocomplete_fields = ("visitor",)
    readonly_fields = ("id", "purpose_text", "visit_date", "created_at", "updated_at")

    @admin.display(description="Purpose")
    def display_purpose(self, obj):
        return obj.display_purpose

    def has_add_permission(self, request):
        # The admin writes SQL directly, which would bypass Firestore.
        return not is_enabled() and super().has_add_permission(request)

    def has_change_permission(self, request, obj=None):
        return not is_enabled() and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Visits are soft-deleted from the dashboard so the audit trail stays
        # intact; permanent deletion is not available in the admin.
        return False
