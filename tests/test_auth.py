"""Tests for the authentication flow: signup, login, logout, session
lifecycle, and the storage guarantees (hashing, revocation, expiry)."""
from datetime import datetime, timedelta

from sqlalchemy import text

from app.auth import SESSION_COOKIE
from app.db import get_engine
from app.models import utcnow
from tests.conftest import signup


def _raw_row(query, params=None):
    with get_engine().connect() as conn:
        return conn.execute(text(query), params or {}).first()


def test_signup_creates_session_and_normalizes_email(client, new_email):
    r = signup(client, f"  {new_email.upper()}  ")
    assert r.status_code == 201
    assert r.json()["email"] == new_email
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == new_email


def test_signup_cookie_security_flags(client, new_email):
    """HttpOnly and SameSite=Lax locally; Secure only in production (VERCEL)."""
    r = signup(client, new_email)
    set_cookie = r.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "secure" not in set_cookie
    assert SESSION_COOKIE in set_cookie
    assert r.cookies.get(SESSION_COOKIE), "signup must set the session cookie"


def test_signup_duplicate_email_returns_409(client, new_email):
    assert signup(client, new_email).status_code == 201
    r = signup(client, new_email.upper())  # same address, different case
    assert r.status_code == 409


def test_signup_rejects_weak_password(client, new_email):
    r = signup(client, new_email, password="short")
    assert r.status_code == 422


def test_signup_rejects_malformed_email(client):
    r = signup(client, "not-an-email", password="correct horse battery staple")
    assert r.status_code == 422


def test_me_rejects_anonymous_request(client):
    assert client.get("/api/auth/me").status_code == 401


def test_login_accepts_mixed_case_email(client, new_email):
    signup(client, new_email)
    r = client.post(
        "/api/auth/login",
        json={"email": new_email.upper(), "password": "correct horse battery staple"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == new_email


def test_login_rejects_wrong_password(client, new_email):
    signup(client, new_email)
    r = client.post("/api/auth/login", json={"email": new_email, "password": "not the right one"})
    assert r.status_code == 401


def test_login_never_validates_password_length(client, new_email):
    """A wrong password is a 401 no matter its length; a login endpoint that
    422s short attempts would lock out accounts with legacy credentials."""
    signup(client, new_email)
    r = client.post("/api/auth/login", json={"email": new_email, "password": "x"})
    assert r.status_code == 401


def test_login_unknown_email_gives_same_error_as_wrong_password(client):
    """No account enumeration: unknown email and bad password must be
    indistinguishable."""
    signup(client, "someone@example.com")
    unknown = client.post("/api/auth/login", json={"email": "ghost@example.com", "password": "x"})
    wrong = client.post("/api/auth/login", json={"email": "someone@example.com", "password": "x"})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]


def test_logout_revokes_session_and_deletes_row(client, new_email):
    signup(client, new_email)
    uid = client.get("/api/auth/me").json()["id"]
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert _raw_row("SELECT count(*) FROM sessions WHERE user_id = :u", {"u": uid})[0] == 0


def test_second_session_survives_first_logout(client, new_email):
    signup(client, new_email)
    token_a = client.cookies.get(SESSION_COOKIE)
    client.cookies.delete(SESSION_COOKIE)

    client.post("/api/auth/login", json={"email": new_email, "password": "correct horse battery staple"})
    token_b = client.cookies.get(SESSION_COOKIE)
    client.cookies.set(SESSION_COOKIE, token_a)
    client.post("/api/auth/logout")
    client.cookies.set(SESSION_COOKIE, token_b)
    assert client.get("/api/auth/me").status_code == 200, "other session must stay valid"


def test_expired_session_is_rejected(client, new_email):
    signup(client, new_email)
    uid = client.get("/api/auth/me").json()["id"]
    expired_token = "expired-token-for-testing-0000000000000"
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sessions (token, user_id, created_at, expires_at) "
                "VALUES (:t, :u, :c, :e)"
            ),
            {
                "t": expired_token[:64],
                "u": uid,
                "c": utcnow() - timedelta(days=31),
                "e": datetime.utcnow() - timedelta(days=1),
            },
        )
    client.cookies.set(SESSION_COOKIE, expired_token[:64])
    assert client.get("/api/auth/me").status_code == 401


def test_passwords_are_stored_hashed_never_plaintext(client, new_email):
    password = "correct horse battery staple"
    signup(client, new_email, password=password)
    row = _raw_row("SELECT password_hash FROM users WHERE email = :e", {"e": new_email})
    stored = row[0]
    assert stored.startswith("scrypt$"), "scrypt hash expected"
    assert password not in stored
    from app.auth import verify_password

    assert verify_password(password, stored)
    assert not verify_password("wrong", stored)


def test_registration_evidence_absent_from_auth(client, new_email):
    """Login for an unregistered address behaves like any other failed login;
    nothing leaks whether the account exists."""
    r = client.post("/api/auth/login", json={"email": new_email, "password": "correct horse battery staple"})
    assert r.status_code == 401
