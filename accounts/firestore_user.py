"""Lightweight user object for Firestore-backed authentication."""

from __future__ import annotations


class FirestoreUser:
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []
    is_anonymous = False
    is_authenticated = True

    def __init__(self, user_data: dict):
        self._data = user_data or {}
        self.uid = self._data.get("uid") or self._data.get("id") or ""
        self.username = self._data.get("username") or ""
        self.email = self._data.get("email") or ""
        self.first_name = self._data.get("first_name") or ""
        self.last_name = self._data.get("last_name") or ""
        self.role = self._data.get("role") or "STAFF"
        self.is_active = bool(self._data.get("is_active", True))
        self.is_superuser = bool(self._data.get("is_superuser", False))
        self.password = self._data.get("password") or ""
        # The session stores ``_meta.pk.value_to_string(user)`` and Django
        # parses it back through ``User._meta.pk.to_python()``, so the pk MUST
        # be an integer id (the SQL mirror row id).
        try:
            self.pk = int(self._data.get("sql_id") or 0)
        except (TypeError, ValueError):
            self.pk = 0
        self.id = self.pk
        # Compute is_staff
        self._is_staff = bool(self._data.get("is_staff", False)) or self.is_superuser or self.role == "ADMIN"
        self._meta = self._build_meta()

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_admin_role(self) -> bool:
        return self.is_superuser or self.role == "ADMIN"

    @property
    def is_staff(self):
        return bool(self._is_staff) or self.is_superuser or self.role == "ADMIN"

    @is_staff.setter
    def is_staff(self, value):
        self._is_staff = bool(value)

    def _build_meta(self):
        owner = self

        class FakePKField:
            name = "pk"
            attname = "pk"
            column = "pk"
            db_column = None
            primary_key = True
            auto_created = False
            concrete = True
            is_relation = False
            related_model = None
            remote_field = None
            default = None
            null = False
            blank = False

            def value_to_string(self, obj):
                return str(obj.pk)

            def get_prep_value(self, value):
                return value

            def to_python(self, value):
                return value

        class FakeMeta:
            app_label = "accounts"
            model_name = "firestoreuser"
            object_name = "FirestoreUser"
            label = "accounts.FirestoreUser"
            label_lower = "accounts.firestoreuser"
            db_table = "accounts_firestoreuser"
            abstract = False
            swapped = False
            auto_created = False
            managed = False
            pk = FakePKField()
            _fields = [FakePKField()]

            def __init__(self, model):
                self.model = model
                self.concrete_model = model

            def get_field(self, name):
                if name in ("pk", "id"):
                    return FakePKField()
                raise Exception("no field %s" % name)

            def get_fields(self, *args, **kwargs):
                return list(self._fields)

            def get_fields(self):  # noqa: F811
                return list(self._fields)

            @property
            def fields(self):
                return list(self._fields)

            def default_manager(self):
                return None

            @property
            def base_manager(self):
                return None

            def get_field_name(self, field):
                return field.name

            def __str__(self):
                return self.label

        return FakeMeta(owner)

    def get_session_auth_hash(self):
        # Mirrors django.contrib.auth.models.AbstractBaseUser.
        from django.utils.crypto import salted_hmac

        key_salt = "django.contrib.auth.models.AbstractBaseUser.get_session_auth_hash"
        return salted_hmac(key_salt, self.password, algorithm="sha256").hexdigest()

    def get_session_auth_fallback_hash(self):
        # Mirrors django.contrib.auth.models.AbstractBaseUser so that
        # django.contrib.auth.get_user() can fall back gracefully.
        from django.utils.crypto import salted_hmac

        key_salt = (
            "django.contrib.auth.models.AbstractBaseUser.get_session_auth_fallback_hash"
        )
        return salted_hmac(key_salt, self.password, algorithm="sha256").hexdigest()

    def get_session_auth_hash_salt(self):
        from django.conf import settings
        from django.contrib.auth import SESSION_AUTH_SALT

        return getattr(settings, "SESSION_AUTH_SALT", SESSION_AUTH_SALT)

    @property
    def display_name(self) -> str:
        full = f"{self.first_name} {self.last_name}".strip()
        return full or self.username or self.email

    def get_username(self) -> str:
        return self.username

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        return self.first_name or self.username

    def get_role_display(self) -> str:
        if self.role == "ADMIN":
            return "Administrator"
        return "Front Desk Staff"

    def has_perm(self, perm, obj=None) -> bool:
        if self.is_superuser:
            return True
        if self.is_admin_role:
            return True
        return False

    def has_perms(self, perm_list, obj=None) -> bool:
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def has_module_perms(self, app_label) -> bool:
        if self.is_superuser or self.is_admin_role:
            return True
        return False

    def check_password(self, raw_password: str) -> bool:
        from accounts.firestore_users import check_password

        return check_password(self._data, raw_password)

    def set_password(self, raw_password: str) -> None:
        from accounts.firestore_users import set_password

        set_password(self.uid, raw_password)
        self._data["password"] = "set"  # placeholder

    def save(self, *args, **kwargs):
        from accounts.firestore_users import update_user

        update_user(
            self.uid,
            {
                "first_name": self.first_name,
                "last_name": self.last_name,
                "email": self.email,
                "role": self.role,
                "is_active": self.is_active,
                "is_superuser": self.is_superuser,
                "is_staff": self.is_staff,
            },
        )

    def __str__(self):
        return self.username
