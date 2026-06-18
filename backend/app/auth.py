"""Lightweight, dependency-free authentication.

Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library). Sessions are
opaque random tokens stored in the database and carried in an HTTP-only cookie.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import Request
from sqlalchemy.orm import Session

from .database import AuthSession, User

COOKIE_NAME = "twin_session"
_PBKDF2_ROUNDS = 200_000


def hash_password(password: str) -> tuple[str, str]:
    """Return (salt_hex, hash_hex) for a new password."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return salt.hex(), digest.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS
    )
    return hmac.compare_digest(digest.hex(), hash_hex)


def create_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(token=token, user_id=user.id))
    db.commit()
    return token


def destroy_session(db: Session, token: str) -> None:
    obj = db.get(AuthSession, token)
    if obj is not None:
        db.delete(obj)
        db.commit()


def user_from_request(request: Request, db: Session) -> Optional[User]:
    """Resolve the authenticated user from the session cookie, if any."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    session = db.get(AuthSession, token)
    if session is None:
        return None
    return db.get(User, session.user_id)
