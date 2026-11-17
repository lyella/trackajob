"""Rate limiting and account deletion.

Both are launch prerequisites, so the tests focus on the properties that
matter rather than the happy path: that limits actually throttle, that they
are scoped so one actor cannot hurt another, and that deletion leaves no
personal data behind in any table.
"""
import uuid

import pytest
from sqlalchemy import select, text

from app import ratelimit
from app.db import get_engine, get_session_factory
from app.models import RateLimitHit
from tests.conftest import signup


def _reset_limits():
    """Clear limiter rows between tests: they are global state."""
    from app.db import Base

    # The autouse fixture can run before any request has created the schema.
    Base.metadata.create_all(get_engine())
    with get_session_factory()() as db:
        db.execute(text("DELETE FROM rate_limit_hits"))
        db.commit()


@pytest.fixture(autouse=True)
def clean_limits():
    _reset_limits()
    yield
    _reset_limits()


# --------------------------------------------------------------------------
# Rate limiting
# --------------------------------------------------------------------------


def test_login_is_throttled_after_repeated_failures(client, new_email):
    signup(client, new_email)
    client.cookies.clear()

    limit, _ = ratelimit.LIMITS["login"]
    for _ in range(limit):
        r = client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})
        assert r.status_code == 401

    blocked = client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})
    assert blocked.status_code == 429
    assert "retry-after" in {k.lower() for k in blocked.headers}


def test_throttling_blocks_even_the_correct_password(client, new_email):
    """Otherwise an attacker could keep guessing past the limit by eventually
    hitting the right one."""
    signup(client, new_email)
    client.cookies.clear()

    limit, _ = ratelimit.LIMITS["login"]
    for _ in range(limit):
        client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})

    r = client.post(
        "/api/auth/login",
        json={"email": new_email, "password": "correct horse battery staple"},
    )
    assert r.status_code == 429


def test_successful_login_clears_the_counter(client, new_email):
    signup(client, new_email)
    client.cookies.clear()

    for _ in range(3):
        client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})

    ok = client.post(
        "/api/auth/login",
        json={"email": new_email, "password": "correct horse battery staple"},
    )
    assert ok.status_code == 200

    # The slate is clean, so a fresh run of failures starts from zero.
    for _ in range(3):
        r = client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})
        assert r.status_code == 401, "counter should have been cleared by the success"


def test_limit_is_per_account_not_global(client, new_email):
    """One user hammering their own address must not lock out another."""
    other = f"other-{uuid.uuid4().hex[:10]}@example.com"
    signup(client, new_email)
    client.cookies.clear()
    signup(client, other)
    client.cookies.clear()

    limit, _ = ratelimit.LIMITS["login"]
    for _ in range(limit):
        client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})

    # The other account still works: the limit is keyed per address.
    r = client.post(
        "/api/auth/login",
        json={"email": other, "password": "correct horse battery staple"},
    )
    assert r.status_code == 200


def test_signup_is_throttled(client):
    limit, _ = ratelimit.LIMITS["signup"]
    for _ in range(limit):
        signup(client, f"spam-{uuid.uuid4().hex[:10]}@example.com")
    r = signup(client, f"spam-{uuid.uuid4().hex[:10]}@example.com")
    assert r.status_code == 429


def test_forgot_password_is_throttled(client, new_email):
    signup(client, new_email)
    limit, _ = ratelimit.LIMITS["forgot"]
    for _ in range(limit):
        client.post("/api/auth/forgot-password", json={"email": new_email})
    r = client.post("/api/auth/forgot-password", json={"email": new_email})
    assert r.status_code == 429


def test_window_expiry_allows_attempts_again(client, new_email):
    """Rows older than the window stop counting."""
    signup(client, new_email)
    client.cookies.clear()

    limit, seconds = ratelimit.LIMITS["login"]
    for _ in range(limit):
        client.post("/api/auth/login", json={"email": new_email, "password": "wrong"})
    assert client.post(
        "/api/auth/login", json={"email": new_email, "password": "wrong"}
    ).status_code == 429

    # Age the rows out of the window.
    with get_session_factory()() as db:
        db.execute(text("UPDATE rate_limit_hits SET created_at = '2000-01-01 00:00:00'"))
        db.commit()

    r = client.post(
        "/api/auth/login",
        json={"email": new_email, "password": "correct horse battery staple"},
    )
    assert r.status_code == 200, "attempts should be allowed again after the window"


def test_limiter_fails_open_when_the_database_errors(client, new_email, monkeypatch):
    """A limiter bug must not become an outage."""
    signup(client, new_email)
    client.cookies.clear()

    def boom(*args, **kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr(ratelimit, "_count", boom)
    r = client.post(
        "/api/auth/login",
        json={"email": new_email, "password": "correct horse battery staple"},
    )
    assert r.status_code == 200


# --------------------------------------------------------------------------
# Account deletion
# --------------------------------------------------------------------------


def _make_data(client, new_email):
    """Create a resume with versions, a job, and a tailor usage row."""
    signup(client, new_email)
    resume = client.post(
        "/api/resumes",
        json={"name": "Mine", "content": {"name": "A B", "links": [], "skills": [], "experience": [], "education": [], "projects": []}},
    ).json()
    client.post(f"/api/resumes/{resume['id']}/versions", json={"name": "A B v2", "links": [], "skills": [], "experience": [], "education": [], "projects": []})
    job = client.post("/api/jobs", json={"title": "Engineer", "company": "Acme"}).json()
    with get_session_factory()() as db:
        db.execute(
            text("INSERT INTO tailor_usage (user_id, tokens_in, tokens_out, cost_micro_usd, created_at) VALUES (:u, 10, 20, 30, '2026-01-01 00:00:00')"),
            {"u": 1},
        )
        db.commit()
    return resume["id"], job["id"]


def test_delete_account_removes_all_user_data(client, new_email):
    _make_data(client, new_email)

    r = client.request("DELETE", "/api/auth/account", json={"password": "correct horse battery staple"})
    assert r.status_code == 204

    # Nothing of this user remains in any table.
    with get_engine().connect() as conn:
        for table in ("resumes", "resume_versions", "jobs", "tailor_usage", "auth_tokens", "sessions", "users"):
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()
            assert count == 0, f"{table} still has rows after account deletion"


def test_delete_account_requires_the_password(client, new_email):
    signup(client, new_email)
    r = client.request("DELETE", "/api/auth/account", json={"password": "not-the-password"})
    assert r.status_code == 401
    assert client.get("/api/auth/me").status_code == 200, "account must survive a bad password"


def test_delete_account_requires_authentication(client):
    client.cookies.clear()
    r = client.request("DELETE", "/api/auth/account", json={"password": "x"})
    assert r.status_code == 401


def test_delete_account_clears_the_session(client, new_email):
    signup(client, new_email)
    client.request("DELETE", "/api/auth/account", json={"password": "correct horse battery staple"})
    assert client.get("/api/auth/me").status_code == 401


def test_delete_account_does_not_touch_other_users(client, new_email):
    other = f"other-{uuid.uuid4().hex[:10]}@example.com"
    _make_data(client, new_email)

    client.cookies.clear()
    signup(client, other)
    client.post("/api/jobs", json={"title": "Other job"})

    # Delete the first account by signing back in as it.
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": new_email, "password": "correct horse battery staple"})
    client.request("DELETE", "/api/auth/account", json={"password": "correct horse battery staple"})

    client.cookies.clear()
    client.post("/api/auth/login", json={"email": other, "password": "correct horse battery staple"})
    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 1, "the other account's data must survive"
    assert jobs[0]["title"] == "Other job"
