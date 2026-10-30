from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        # Register auth signal receivers (login / failed login auditing).
        from . import signals  # noqa: F401
