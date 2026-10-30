from __future__ import annotations

import runpy

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.core.management.base import CommandError

User = get_user_model()

VALID_SECRET = "x" * 64


def load_prod_settings():
    return runpy.run_module("config.settings.prod", run_name="config.settings.prod")


def test_prod_refuses_the_development_secret(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", "")
    monkeypatch.setenv("DJANGO_ALLOW_SQLITE_PROD", "true")

    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        load_prod_settings()


def test_prod_refuses_sqlite_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", VALID_SECRET)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.delenv("DJANGO_ALLOW_SQLITE_PROD", raising=False)

    with pytest.raises(ImproperlyConfigured, match="POSTGRES_DB"):
        load_prod_settings()


def test_prod_allows_sqlite_when_explicitly_opted_in(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", VALID_SECRET)
    monkeypatch.delenv("POSTGRES_DB", raising=False)
    monkeypatch.setenv("DJANGO_ALLOW_SQLITE_PROD", "true")

    module = load_prod_settings()

    assert module["DEBUG"] is False
    assert module["DATABASES"]["default"]["ENGINE"] == "django.db.backends.sqlite3"


def test_prod_uses_postgres_when_configured(monkeypatch):
    monkeypatch.setenv("DJANGO_SECRET_KEY", VALID_SECRET)
    monkeypatch.setenv("POSTGRES_DB", "visitra")
    monkeypatch.setenv("POSTGRES_USER", "visitra")
    monkeypatch.setenv("POSTGRES_PASSWORD", "secret")

    module = load_prod_settings()

    assert module["DATABASES"]["default"]["ENGINE"] == "django.db.backends.postgresql"
    assert module["DATABASES"]["default"]["NAME"] == "visitra"


@pytest.mark.django_db
def test_seed_demo_refuses_when_debug_is_off(settings):
    settings.DEBUG = False

    with pytest.raises(CommandError, match="--force"):
        call_command("seed_demo", verbosity=0)

    assert not User.objects.filter(username="admin").exists()


@pytest.mark.django_db
def test_seed_demo_can_be_forced(settings):
    settings.DEBUG = False

    call_command("seed_demo", force=True, verbosity=0)

    assert User.objects.filter(username="admin", role=User.Role.ADMIN).exists()
