"""Authentication backend that accepts either a username or an email address."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        # If a username happens to equal another account's email address the
        # match is ambiguous. Refuse it rather than silently choosing one.
        users = list(
            UserModel._default_manager.filter(
                Q(username__iexact=username) | Q(email__iexact=username)
            ).order_by("id")[:2]
        )
        if len(users) != 1:
            # Run the hasher once to reduce timing differences between an
            # unknown/ambiguous account and a wrong password.
            UserModel().set_password(password)
            return None

        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
