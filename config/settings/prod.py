"""Production settings.

Set DJANGO_SETTINGS_MODULE=config.settings.prod and provide real environment
variables before serving traffic. This module fails closed: it refuses to start
with the development secret key or with SQLite unless the operator explicitly
opts in.
"""

from __future__ import annotations

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env_bool

DEBUG = False

# Never fall back to the insecure development key in production.
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "").strip()
if not SECRET_KEY or SECRET_KEY == "insecure-development-key-change-me":
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be set to a long random value in production."
    )

if os.getenv("POSTGRES_DB"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["POSTGRES_DB"],
            "USER": os.getenv("POSTGRES_USER", "postgres"),
            "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
            "HOST": os.getenv("POSTGRES_HOST", "127.0.0.1"),
            "PORT": os.getenv("POSTGRES_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
elif not env_bool("DJANGO_ALLOW_SQLITE_PROD", False):
    raise ImproperlyConfigured(
        "Production requires PostgreSQL (set POSTGRES_DB). Set "
        "DJANGO_ALLOW_SQLITE_PROD=True only for a deliberate single-machine "
        "SQLite deployment."
    )

# HTTPS hardening. Disable SSL redirect only when intentionally serving plain
# HTTP on a trusted LAN.
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365 if SECURE_SSL_REDIRECT else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_SSL_REDIRECT
SECURE_HSTS_PRELOAD = SECURE_SSL_REDIRECT
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
