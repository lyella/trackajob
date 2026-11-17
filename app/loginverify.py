"""Login verification for unfamiliar locations and devices.

The rule: a correct password is enough from a device and country the account
has used before. From anywhere else, a 6-digit code is emailed first.

Why this shape:

- **It catches a stolen password.** An attacker with the password but not
  the inbox cannot finish the login, and the owner gets an email telling them
  someone tried.
- **It does not enable lockout.** A failed or unverified attempt never blocks
  the real owner; their familiar device still signs in normally. Anything
  that let a stranger lock the account would be worse than the risk.
- **It is quiet.** Travel and VPNs prompt once, then the device/country pair
  is remembered.

The country comes from the hosting platform's geo header, because a
serverless function cannot do a GeoIP lookup without shipping a database.
When the header is absent (local development, most self-hosting), the check
is skipped rather than treated as suspicious: an unknown country is not
evidence of an attack, and guessing would prompt on every login.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import emailer
from app.config import get_settings
from app.models import KnownDevice, LoginChallenge, User, utcnow

# Headers Vercel and Cloudflare set with the visitor's country.
COUNTRY_HEADERS = ("x-vercel-ip-country", "cf-ipcountry", "x-country-code")
CODE_LENGTH = 6
MAX_ATTEMPTS = 5


def country_for(headers) -> str:
    """The visitor's ISO country code, or "" when the platform does not say."""
    for name in COUNTRY_HEADERS:
        value = headers.get(name)
        if value and len(value) == 2 and value.isalpha():
            return value.upper()
    return ""


def fingerprint_for(user_agent: str, accept_language: str) -> str:
    """A stable, coarse device identifier.

    Deliberately not a full user-agent hash: browsers change the version
    string constantly, which would make every update look like a new device.
    Platform and a language hint are stable enough to recognise the same
    browser without storing anything identifying.
    """
    ua = (user_agent or "").lower()
    platform = "unknown"
    for token in ("iphone", "ipad", "android", "windows", "macintosh", "linux"):
        if token in ua:
            platform = token
            break
    browser = "other"
    for token in ("edg", "chrome", "firefox", "safari"):
        if token in ua:
            browser = token
            break
    language = (accept_language or "").split(",")[0].strip().lower()[:12]
    raw = f"{platform}|{browser}|{language}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def is_known(db: Session, user: User, fingerprint: str, country: str) -> bool:
    """True when this device has signed in before, in this country."""
    row = db.execute(
        select(KnownDevice).where(
            KnownDevice.user_id == user.id,
            KnownDevice.fingerprint == fingerprint,
            KnownDevice.country == country,
        )
    ).scalar_one_or_none()
    return row is not None


def remember(db: Session, user: User, fingerprint: str, country: str) -> None:
    """Record a device/country pair after a successful verification."""
    row = db.execute(
        select(KnownDevice).where(
            KnownDevice.user_id == user.id,
            KnownDevice.fingerprint == fingerprint,
            KnownDevice.country == country,
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(KnownDevice(user_id=user.id, fingerprint=fingerprint, country=country))
    else:
        row.last_seen = utcnow()
    db.commit()


def needs_verification(db: Session, user: User, fingerprint: str, country: str) -> bool:
    """Whether this login must be confirmed by email code.

    Returns False when the feature is off, when the platform gave no country
    (so we cannot judge), or when the device and country are already known.
    """
    settings = get_settings()
    if not settings.login_code_enabled:
        return False
    if not country:
        return False
    return not is_known(db, user, fingerprint, country)


def start_challenge(
    db: Session, user: User, fingerprint: str, country: str, ip: str
) -> tuple[str, str]:
    """Create a pending challenge and email the code.

    Returns (challenge_token, code). The caller must not leak the code; it is
    returned only so tests and the console driver can use it.
    """
    settings = get_settings()
    code = f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"
    token = secrets.token_urlsafe(24)

    # Any earlier pending challenge for this user is retired, so a resend
    # cannot leave two codes valid at once.
    for row in db.execute(
        select(LoginChallenge).where(
            LoginChallenge.user_id == user.id, LoginChallenge.used_at.is_(None)
        )
    ).scalars():
        row.used_at = utcnow()

    db.add(
        LoginChallenge(
            user_id=user.id,
            challenge=token,
            code_hash=_hash_code(code),
            fingerprint=fingerprint,
            country=country,
            ip=ip,
            expires_at=utcnow() + timedelta(minutes=settings.login_code_minutes),
        )
    )
    db.commit()

    emailer.send(
        emailer.login_code_email(
            user.email,
            code,
            settings.login_code_minutes,
            country=country,
        )
    )
    return token, code


def verify_challenge(db: Session, token: str, code: str) -> tuple[User, LoginChallenge] | None:
    """Check a code. Returns the user and challenge on success.

    The attempt counter is incremented on every try, so a 6-digit code cannot
    be brute-forced: five wrong guesses retire the challenge and the user
    must start again.
    """
    row = db.execute(
        select(LoginChallenge).where(LoginChallenge.challenge == token)
    ).scalar_one_or_none()
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None

    if row.attempts >= MAX_ATTEMPTS:
        row.used_at = utcnow()
        db.commit()
        return None

    if not secrets.compare_digest(row.code_hash, _hash_code((code or "").strip())):
        row.attempts += 1
        if row.attempts >= MAX_ATTEMPTS:
            row.used_at = utcnow()
        db.commit()
        return None

    row.used_at = utcnow()
    db.commit()
    user = db.get(User, row.user_id)
    if user is None:
        return None
    return user, row
