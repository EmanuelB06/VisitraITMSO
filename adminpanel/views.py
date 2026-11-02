"""Custom admin panel (replaces ``django.contrib.admin``).

Reads go through the Firestore repositories (or the SQL mirror when Firestore
is off) and writes go through the services so both stores stay consistent.
"""

from __future__ import annotations

import uuid

from django.contrib import messages
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from accounts import firestore_users
from accounts.mixins import AdminRequiredMixin
from audit.repository import AuditRepository
from core.firestore import is_enabled
from core.records import PurposeRecord


def _purpose_records(include_inactive: bool = True) -> list:
    """All purposes as records/dicts, from Firestore or the SQL mirror."""
    if is_enabled():
        try:
            from visits.repository import PurposeRepository

            repo = PurposeRepository()
            records = repo.list_all() if include_inactive else repo.list_active()
            return list(records)
        except Exception:
            return []
    from visits.models import Purpose

    queryset = Purpose.objects.all()
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return list(queryset)


def _activity_logs(limit: int = 100) -> list:
    if is_enabled():
        try:
            return AuditRepository().list(limit=limit)
        except Exception:
            return []
    from audit.models import ActivityLog

    return list(ActivityLog.objects.all()[:limit])


class DashboardView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/dashboard.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        users = firestore_users.list_users()
        users.sort(key=lambda x: (x.get("username") or "").lower())
        ctx["users"] = users
        ctx["visit_count"] = _count_visits()
        ctx["visitor_count"] = _count_visitors()
        ctx["audit_count"] = len(_activity_logs(limit=200))
        return ctx


def _count_visits() -> int:
    if is_enabled():
        try:
            from visits.repository import VisitRepository

            return len(VisitRepository().list_all(limit=1000))
        except Exception:
            return 0
    from visits.models import Visit

    return Visit.objects.visible().count()


def _count_visitors() -> int:
    if is_enabled():
        try:
            from visitors.repository import VisitorRepository

            return len(VisitorRepository().list_all(limit=1000))
        except Exception:
            return 0
    from visitors.models import Visitor

    return Visitor.objects.count()


class UsersListView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/users.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        users = firestore_users.list_users()
        users.sort(key=lambda x: (x.get("username") or "").lower())
        ctx["users"] = users
        return ctx


class UserCreateView(AdminRequiredMixin, View):
    template_name = "adminpanel/user_form.html"

    def get(self, request):
        return render(request, self.template_name, {"action": "Create", "form_user": {}})

    def post(self, request):
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        role = request.POST.get("role", "STAFF")
        is_active = request.POST.get("is_active") == "on"
        is_superuser = request.POST.get("is_superuser") == "on"
        try:
            firestore_users.create_user(
                username=username,
                password=password,
                email=email,
                first_name=first_name,
                last_name=last_name,
                role=role,
                is_active=is_active,
                is_superuser=is_superuser,
                is_staff=is_superuser or role == "ADMIN",
            )
            messages.success(request, "User created.")
            return redirect("adminpanel:users")
        except Exception as exc:
            messages.error(request, str(exc))
            return render(
                request, self.template_name, {"action": "Create", "form_user": request.POST}
            )


class UserEditView(AdminRequiredMixin, View):
    template_name = "adminpanel/user_form.html"

    def get(self, request, uid):
        user = firestore_users.get_by_uid(uid)
        if not user:
            messages.error(request, "User not found.")
            return redirect("adminpanel:users")
        return render(
            request, self.template_name, {"action": "Edit", "form_user": user, "uid": uid}
        )

    def post(self, request, uid):
        user = firestore_users.get_by_uid(uid)
        if not user:
            messages.error(request, "User not found.")
            return redirect("adminpanel:users")
        updates = {
            "first_name": request.POST.get("first_name", "").strip(),
            "last_name": request.POST.get("last_name", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "role": request.POST.get("role", "STAFF"),
            "is_active": request.POST.get("is_active") == "on",
            "is_superuser": request.POST.get("is_superuser") == "on",
        }
        password = request.POST.get("password", "")
        if password:
            updates["password"] = password
        try:
            firestore_users.update_user(uid, updates)
            messages.success(request, "User updated.")
            return redirect("adminpanel:users")
        except Exception as exc:
            messages.error(request, str(exc))
            return render(
                request,
                self.template_name,
                {"action": "Edit", "form_user": user, "uid": uid},
            )


class UserDeleteView(AdminRequiredMixin, View):
    def post(self, request, uid):
        if uid == getattr(request.user, "uid", None):
            messages.error(request, "You cannot delete your own account.")
            return redirect("adminpanel:users")
        try:
            firestore_users.delete_user(uid)
            messages.success(request, "User deleted.")
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect("adminpanel:users")


class PurposesView(AdminRequiredMixin, View):
    template_name = "adminpanel/purposes.html"

    def get(self, request):
        return render(request, self.template_name, {"purposes": _purpose_records()})

    def post(self, request):
        action = request.POST.get("action")
        try:
            if action == "create":
                name = request.POST.get("name", "").strip()
                is_active = request.POST.get("is_active") == "on"
                if not name:
                    messages.error(request, "Purpose name is required.")
                else:
                    self._create(name, is_active)
                    messages.success(request, "Purpose created.")
            elif action == "toggle":
                purpose_id = request.POST.get("purpose_id")
                if purpose_id:
                    self._toggle(purpose_id)
                    messages.success(request, "Purpose updated.")
        except Exception as exc:
            messages.error(request, str(exc))
        return redirect("adminpanel:purposes")

    @staticmethod
    def _create(name: str, is_active: bool) -> None:
        if is_enabled():
            from visits.repository import PurposeRepository

            now = timezone.now()
            PurposeRepository().save(
                PurposeRecord(
                    id=uuid.uuid4().hex,
                    name=name,
                    requires_specification=False,
                    is_active=is_active,
                    sort_order=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            return

        from visits.models import Purpose

        Purpose.objects.create(name=name, is_active=is_active)

    @staticmethod
    def _toggle(purpose_id) -> None:
        if is_enabled():
            from visits.repository import PurposeRepository

            repo = PurposeRepository()
            record = repo.get(purpose_id)
            if not record:
                raise ValueError("Purpose not found.")
            repo.save(
                PurposeRecord(
                    id=record.id,
                    name=record.name,
                    requires_specification=record.requires_specification,
                    is_active=not record.is_active,
                    sort_order=record.sort_order,
                    created_at=record.created_at,
                    updated_at=timezone.now(),
                )
            )
            return

        from visits.models import Purpose

        purpose = Purpose.objects.get(pk=purpose_id)
        purpose.is_active = not purpose.is_active
        purpose.save(update_fields=["is_active"])


class VisitorsView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/visitors.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if is_enabled():
            try:
                from visitors.repository import VisitorRepository

                ctx["visitors"] = VisitorRepository().list_all(limit=200)
            except Exception:
                ctx["visitors"] = []
        else:
            from visitors.models import Visitor

            ctx["visitors"] = list(Visitor.objects.all()[:200])
        return ctx


class VisitsView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/visits.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        if is_enabled():
            try:
                from visits.repository import VisitRepository

                ctx["visits"] = VisitRepository().list_all(limit=200)
            except Exception:
                ctx["visits"] = []
        else:
            from visits.models import Visit

            ctx["visits"] = list(Visit.objects.visible()[:200])
        return ctx


class AuditView(AdminRequiredMixin, TemplateView):
    template_name = "adminpanel/audit.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["logs"] = _activity_logs(limit=200)
        return ctx
