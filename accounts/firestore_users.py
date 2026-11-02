"""Firestore-backed user storage for auth and admin.

All user data lives in the ``users`` Firestore collection when using the
Firestore auth backend. Password hashes are stored using Django's password
hashers so existing login logic continues to work.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from django.contrib.auth.hashers import check_password as django_check_password
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from core.firestore import collection_name, get_store, is_enabled

logger = logging.getLogger(__name__)

USERS_COLLECTION = "users"
META_COLLECTION = "meta"
USER_ID_SEQ_DOC = "user_id_seq"


def _users_collection():
    return collection_name(USERS_COLLECTION)


def _next_sql_id() -> int:
    """Allocate the next integer user id from a Firestore counter document.

    The id doubles as the SQL mirror row id (``logged_by``/``actor`` foreign
    keys), so it must never collide with an existing ``accounts.User`` row.
    """
    store = get_store()
    coll = collection_name(META_COLLECTION)
    doc = store.get(coll, USER_ID_SEQ_DOC) or {}
    value = int(doc.get("value") or 0)
    try:
        from django.contrib.auth import get_user_model
        from django.db.models import Max

        sql_max = get_user_model().objects.aggregate(Max("id"))["id__max"] or 0
        value = max(value, int(sql_max))
    except Exception:
        pass
    value += 1
    store.set(coll, USER_ID_SEQ_DOC, {"value": value})
    return value


def get_by_sql_id(sql_id) -> dict[str, Any] | None:
    """Look a user up by its integer mirror id (used by the auth backend)."""
    if not sql_id:
        return None
    try:
        sql_id = int(sql_id)
    except (TypeError, ValueError):
        return None
    try:
        store = get_store()
        docs = store.query(
            collection_name(USERS_COLLECTION),
            filters=[("sql_id", "==", sql_id)],
            limit=2,
        )
        if not docs:
            return None
        return _doc_to_user(docs[0])
    except Exception:
        logger.exception("Failed to load user from Firestore by sql_id")
        return None


def _doc_to_user(doc: dict[str, Any]) -> dict[str, Any]:
    if not doc:
        return {}
    data = dict(doc)
    # Ensure uid/id present
    if "uid" not in data and "id" in data:
        data["uid"] = data["id"]
    if "sql_id" in data:
        try:
            data["sql_id"] = int(data["sql_id"])
        except (TypeError, ValueError):
            data["sql_id"] = None
    return data


def get_by_uid(uid: str) -> dict[str, Any] | None:
    if not uid:
        return None
    try:
        store = get_store()
        doc = store.get(collection_name(USERS_COLLECTION), uid)
        if not doc:
            return None
        return _doc_to_user(doc)
    except Exception:
        logger.exception("Failed to load user from Firestore uid=%s", uid)
        return None


def get_by_username(username: str) -> dict[str, Any] | None:
    if not username:
        return None
    try:
        store = get_store()
        col = _users_collection()
        # Case-insensitive search
        docs = store.query(
            col,
            filters=[("username_lower", "==", username.lower())],
            limit=2,
        )
        if not docs:
            # Fallback to exact match
            docs = store.query(
                col,
                filters=[("username", "==", username)],
                limit=2,
            )
        if len(docs) != 1:
            return None
        return _doc_to_user(docs[0])
    except Exception:
        logger.exception("Failed to load user from Firestore by username")
        return None


def get_by_email(email: str) -> dict[str, Any] | None:
    if not email:
        return None
    try:
        store = get_store()
        docs = store.query(
            collection_name(USERS_COLLECTION),
            filters=[("email_lower", "==", email.lower())],
            limit=2,
        )
        if not docs:
            docs = store.query(
                collection_name(USERS_COLLECTION),
                filters=[("email", "==", email)],
                limit=2,
            )
        if len(docs) != 1:
            return None
        return _doc_to_user(docs[0])
    except Exception:
        logger.exception("Failed to load user from Firestore by email")
        return None


def get_by_login(identifier: str) -> dict[str, Any] | None:
    """Get user by username or email. Returns None if ambiguous or not found."""
    if not identifier:
        return None
    users = []
    try:
        store = get_store()
        # Try username
        docs = store.query(
            collection_name(USERS_COLLECTION),
            filters=[("username_lower", "==", identifier.lower())],
            limit=2,
        )
        if len(docs) == 1:
            users.append(_doc_to_user(docs[0]))
        elif len(docs) == 0:
            docs = store.query(
                collection_name(USERS_COLLECTION),
                filters=[("username", "==", identifier)],
                limit=2,
            )
            if len(docs) == 1:
                users.append(_doc_to_user(docs[0]))
        # Try email if no username match
        if not users:
            docs = store.query(
                collection_name(USERS_COLLECTION),
                filters=[("email_lower", "==", identifier.lower())],
                limit=2,
            )
            if len(docs) == 1:
                users.append(_doc_to_user(docs[0]))
            elif len(docs) == 0 and "@" in identifier:
                docs = store.query(
                    collection_name(USERS_COLLECTION),
                    filters=[("email", "==", identifier)],
                    limit=2,
                )
                if len(docs) == 1:
                    users.append(_doc_to_user(docs[0]))
        if len(users) != 1:
            return None
        return users[0]
    except Exception:
        logger.exception("Failed to load user from Firestore by login")
        return None


def create_user(
    username: str,
    password: str,
    email: str = "",
    first_name: str = "",
    last_name: str = "",
    role: str = "STAFF",
    is_active: bool = True,
    is_superuser: bool = False,
    is_staff: bool = False,
) -> dict[str, Any]:
    username = (username or "").strip()
    email = (email or "").strip()
    if not username:
        raise ValueError("username required")
    # Check uniqueness
    if get_by_username(username):
        raise ValueError("username already exists")
    if email and get_by_email(email):
        raise ValueError("email already exists")
    
    now = timezone.now()
    uid = username.lower().replace(" ", "_")
    # Ensure unique uid
    base_uid = uid
    counter = 1
    while get_by_uid(uid):
        uid = f"{base_uid}_{counter}"
        counter += 1

    user_data = {
        "uid": uid,
        "username": username,
        "username_lower": username.lower(),
        "email": email,
        "email_lower": email.lower() if email else "",
        "first_name": first_name or "",
        "last_name": last_name or "",
        "password": make_password(password),
        "role": role if role in ("ADMIN", "STAFF") else "STAFF",
        "is_active": bool(is_active),
        "is_superuser": bool(is_superuser),
        "is_staff": bool(is_staff) or bool(is_superuser) or role == "ADMIN",
        "sql_id": _next_sql_id(),
        "date_joined": now.isoformat(),
        "last_login": None,
    }
    try:
        store = get_store()
        store.set(collection_name(USERS_COLLECTION), uid, user_data)
        return user_data
    except Exception:
        logger.exception("Failed to create user in Firestore")
        raise


def update_user(uid: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if not uid:
        return None
    user = get_by_uid(uid)
    if not user:
        return None
    user = dict(user)
    # Handle password
    if "password" in updates and updates["password"]:
        user["password"] = make_password(updates["password"])
        updates = dict(updates)
        updates.pop("password")
    # Handle username change
    if "username" in updates:
        new_username = updates["username"].strip()
        if new_username and new_username.lower() != user.get("username_lower"):
            existing = get_by_username(new_username)
            if existing and existing.get("uid") != uid:
                raise ValueError("username already exists")
            user["username"] = new_username
            user["username_lower"] = new_username.lower()
        updates.pop("username")
    # Handle email change
    if "email" in updates:
        new_email = updates["email"].strip()
        if new_email.lower() != user.get("email_lower"):
            existing = get_by_email(new_email)
            if existing and existing.get("uid") != uid:
                raise ValueError("email already exists")
            user["email"] = new_email
            user["email_lower"] = new_email.lower() if new_email else ""
        updates.pop("email")
    # Apply other updates
    for key, value in updates.items():
        if key in ("uid", "date_joined"):
            continue
        user[key] = value
    # Sync is_staff with admin role
    if user.get("is_superuser") or user.get("role") == "ADMIN":
        user["is_staff"] = True
    elif user.get("role") == "STAFF":
        user["is_staff"] = False
    try:
        store = get_store()
        store.set(collection_name(USERS_COLLECTION), uid, user)
        return user
    except Exception:
        logger.exception("Failed to update user in Firestore uid=%s", uid)
        return None


def delete_user(uid: str) -> bool:
    if not uid:
        return False
    try:
        store = get_store()
        store.delete(collection_name(USERS_COLLECTION), uid)
        return True
    except Exception:
        logger.exception("Failed to delete user from Firestore uid=%s", uid)
        return False


def list_users() -> list[dict[str, Any]]:
    try:
        store = get_store()
        docs = store.query(collection_name(USERS_COLLECTION))
        return [_doc_to_user(d) for d in docs]
    except Exception:
        logger.exception("Failed to list users from Firestore")
        return []


def check_password(user_data: dict[str, Any], password: str) -> bool:
    if not user_data or not password:
        return False
    try:
        return django_check_password(password, user_data.get("password", ""))
    except Exception:
        return False


def set_password(uid: str, password: str) -> bool:
    user = update_user(uid, {"password": password})
    return user is not None
