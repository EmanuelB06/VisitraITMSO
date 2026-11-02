"""Firestore-backed session store.

Sessions are documents in the ``sessions`` collection while Firestore is the
system of record. With ``FIRESTORE_ENABLED`` off (tests, offline development)
every override delegates to the stock database-backed store, so behaviour is
identical to a vanilla Django install.
"""

from __future__ import annotations

import logging
from datetime import datetime

from django.contrib.sessions.backends.db import SessionStore as DbSessionStore
from django.utils import timezone

from core.firestore import collection_name, get_store, is_enabled

logger = logging.getLogger(__name__)

SESSIONS_COLLECTION = "sessions"


class SessionStore(DbSessionStore):
    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _using_firestore() -> bool:
        try:
            return is_enabled()
        except Exception:
            return False

    @staticmethod
    def _collection() -> str:
        return collection_name(SESSIONS_COLLECTION)

    @staticmethod
    def _parse_expire(value) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _expired(self, expire_date) -> bool:
        exp = self._parse_expire(expire_date)
        if exp is None:
            return False
        now = timezone.now()
        if timezone.is_aware(exp):
            return exp < now
        return exp < now.replace(tzinfo=None)

    # ------------------------------------------------------------------- API
    def load(self):
        if not self._using_firestore():
            return super().load()

        if not self.session_key:
            self.create()
            return {}
        try:
            store = get_store()
            doc = store.get(self._collection(), self.session_key)
            if not doc:
                self.create()
                return {}
            if self._expired(doc.get("expire_date")):
                self.delete(self.session_key)
                self.create()
                return {}
            data = doc.get("session_data")
            return self.decode(data) if isinstance(data, str) else {}
        except Exception:
            logger.exception("Failed to load session from Firestore")
            self.create()
            return {}

    def exists(self, session_key):
        if not self._using_firestore():
            return super().exists(session_key)
        if not session_key:
            return False
        try:
            store = get_store()
            return store.get(self._collection(), session_key) is not None
        except Exception:
            logger.exception("Failed to check session existence in Firestore")
            return False

    def save(self, must_create=False):
        if not self._using_firestore():
            return super().save(must_create=must_create)

        session_key = self._get_or_create_session_key()
        session_data = self.encode(self._get_session(no_load=must_create))
        try:
            store = get_store()
            store.set(
                self._collection(),
                session_key,
                {
                    "session_key": session_key,
                    "session_data": session_data,
                    "expire_date": self.get_expiry_date().isoformat(),
                    "updated_at": timezone.now().isoformat(),
                },
            )
        except Exception:
            logger.exception("Failed to save session to Firestore")

    def delete(self, session_key=None):
        if not self._using_firestore():
            return super().delete(session_key)

        if session_key is None:
            if self.session_key is None:
                return
            session_key = self.session_key
        try:
            store = get_store()
            store.delete(self._collection(), session_key)
        except Exception:
            logger.exception("Failed to delete session from Firestore")

    @classmethod
    def clear_expired(cls):
        if not cls._using_firestore():
            return super().clear_expired()
        try:
            store = get_store()
            collection = cls._collection()
            now = timezone.now()
            for doc in store.query(collection) or []:
                expire = doc.get("expire_date")
                exp = cls._parse_expire(expire) if expire else None
                if exp is None:
                    continue
                stale = (
                    exp < now
                    if timezone.is_aware(exp)
                    else exp < now.replace(tzinfo=None)
                )
                if stale:
                    store.delete(collection, doc.get("session_key") or doc.get("id"))
        except Exception:
            logger.exception("Failed to clear expired sessions from Firestore")
