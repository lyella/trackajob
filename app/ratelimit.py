"""Rate limiting for the auth endpoints.

Vercel functions are stateless, so a counter in memory would reset on every
cold start and would not be shared between instances. The count therefore
lives in the database: one row per counted attempt, and the limit is "how
many rows for this key in the last N seconds".

Design notes:

- **Sliding window, not fixed.** A fixed window lets an attacker send the
  full allowance at the end of one window and again at the start of the next.
- **Two dimensions.** Limits are applied per client IP *and* per account
  identifier where one exists, so one attacker cannot lock out a legitimate
  user by hammering their email, and one IP cannot spray many accounts.
- **Fail open on infrastructure errors.** If the database is unreachable the
  request is allowed rather than turned into a 500. A rate limiter must not
  become an outage; the captcha and password hashing are still in front.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import RateLimitHit, utcnow


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Too many attempts. Try again in {retry_after} seconds.")


# (limit, window in seconds) per bucket. Chosen to be invisible to a person
# with fat fingers but useless for automation.
LIMITS: dict[str, tuple[int, int]] = {
    # Logging in: 10 tries per 15 minutes per email address. The IP ceiling
    # is deliberately much higher, because people share addresses (offices,
    # households, mobile carriers) and a tight per-IP limit would let one
    # person lock out everyone behind the same NAT.
    "login": (10, 15 * 60),
    "login_ip": (60, 15 * 60),
    # Signing up: 5 per hour per IP. A person needs one.
    "signup": (5, 60 * 60),
    # Password reset requests: 5 per hour per IP, 3 per hour per address.
    "forgot": (5, 60 * 60),
    "forgot_account": (3, 60 * 60),
    # Reset submissions: 10 per hour per IP.
    "reset": (10, 60 * 60),
    # Verification resends: 5 per hour per account.
    "resend": (5, 60 * 60),
}


def _window(bucket: str) -> tuple[int, int]:
    return LIMITS.get(bucket, (20, 60))


def _count(db: Session, key: str, since) -> int:
    return int(
        db.execute(
            select(func.count(RateLimitHit.id)).where(
                RateLimitHit.key == key, RateLimitHit.created_at >= since
            )
        ).scalar_one()
        or 0
    )


def check(db: Session, bucket: str, *subjects: str) -> None:
    """Raise RateLimited if any subject has exhausted this bucket.

    Every subject is checked before anything is recorded, so a blocked
    request does not consume allowance from the others.
    """
    limit, seconds = _window(bucket)
    since = utcnow() - timedelta(seconds=seconds)
    try:
        for subject in subjects:
            if not subject:
                continue
            if _count(db, f"{bucket}:{subject}", since) >= limit:
                raise RateLimited(retry_after=seconds)
    except RateLimited:
        raise
    except Exception:  # noqa: BLE001 - never turn a limiter bug into a 500
        return


def record(db: Session, bucket: str, *subjects: str) -> None:
    """Record one attempt against each subject."""
    try:
        for subject in subjects:
            if not subject:
                continue
            db.add(RateLimitHit(key=f"{bucket}:{subject}"))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def clear(db: Session, bucket: str, *subjects: str) -> None:
    """Forget attempts for a subject. Used after a successful login, so a
    person who mistyped a few times is not punished for the rest of the
    window."""
    try:
        keys = [f"{bucket}:{s}" for s in subjects if s]
        if keys:
            db.execute(delete(RateLimitHit).where(RateLimitHit.key.in_(keys)))
            db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def prune(db: Session, older_than_hours: int = 24) -> None:
    """Drop rows older than the longest window. Called opportunistically."""
    try:
        cutoff = utcnow() - timedelta(hours=older_than_hours)
        db.execute(delete(RateLimitHit).where(RateLimitHit.created_at < cutoff))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def guard(db: Session, bucket: str, *subjects: str) -> None:
    """Check, then record. The common path for a failed or neutral attempt."""
    check(db, bucket, *subjects)
    record(db, bucket, *subjects)
