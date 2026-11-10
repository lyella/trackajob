"""Password hashing and session helpers. scrypt comes from the standard
library, so no new binary dependency rides into the serverless bundle.
Opaque DB-backed tokens, not JWTs: logout actually revokes a session."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SessionToken, User, utcnow
SESSION_COOKIE = "tj_session"
SESSION_DAYS = 30
_SCRYPT_N = 2**14


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=_SCRYPT_N, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(
            password.encode(), salt=bytes.fromhex(salt_hex), n=_SCRYPT_N, r=8, p=1, dklen=32
        )
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def create_session(db: Session, user_id: int) -> str:
    token = secrets.token_urlsafe(32)[:64]
    db.add(
        SessionToken(
            token=token,
            user_id=user_id,
            expires_at=utcnow() + timedelta(days=SESSION_DAYS),
        )
    )
    db.commit()
    return token


def user_for_session(db: Session, token: str) -> User | None:
    row = db.execute(
        select(SessionToken).where(SessionToken.token == token)
    ).scalar_one_or_none()
    if row is None or row.expires_at <= utcnow():
        return None
    return db.get(User, row.user_id)


def delete_session(db: Session, token: str) -> None:
    row = db.execute(
        select(SessionToken).where(SessionToken.token == token)
    ).scalar_one_or_none()
    if row is not None:
        db.delete(row)
        db.commit()
