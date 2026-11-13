"""Password hashing and session helpers. scrypt comes from the standard
library, so no new binary dependency rides into the serverless bundle.
Opaque DB-backed tokens, not JWTs: logout actually revokes a session."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthToken, SessionToken, User, utcnow
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


# --------------------------------------------------------------------------
# Verification and reset tokens
# --------------------------------------------------------------------------

VERIFY = "verify"
RESET = "reset"


def _hash_token(raw: str) -> str:
    """Only the hash is stored. A leaked database therefore does not contain
    working reset links."""
    return hashlib.sha256(raw.encode()).hexdigest()


def issue_token(db: Session, user_id: int, purpose: str, ttl: timedelta) -> str:
    """Create a single-use token and return the raw value for the email.

    Any earlier unused token of the same purpose is invalidated first, so a
    user who clicks "resend" cannot end up with two live reset links.
    """
    stale = db.execute(
        select(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    ).scalars()
    for row in stale:
        row.used_at = utcnow()

    raw = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=_hash_token(raw),
            expires_at=utcnow() + ttl,
        )
    )
    db.commit()
    return raw


def consume_token(db: Session, raw: str, purpose: str) -> User | None:
    """Validate and burn a token. Returns the user, or None if the token is
    unknown, already used, expired, or for a different purpose."""
    if not raw:
        return None
    row = db.execute(
        select(AuthToken).where(
            AuthToken.token_hash == _hash_token(raw),
            AuthToken.purpose == purpose,
        )
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    row.used_at = utcnow()
    db.commit()
    return db.get(User, row.user_id)


def revoke_all_sessions(db: Session, user_id: int) -> None:
    """Used after a password reset: every other session is signed out, so an
    attacker who already had a session loses it."""
    for row in db.execute(
        select(SessionToken).where(SessionToken.user_id == user_id)
    ).scalars():
        db.delete(row)
    db.commit()
