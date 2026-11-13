"""Email verification, password reset, and captcha.

These tests are about the failure modes, not the happy path. Auth bugs are
expensive, so each one here encodes a specific way the feature could be
abused: token replay, token expiry, cross-purpose token use, account
enumeration, and a captcha that fails open.
"""
import re

import pytest

from app import captcha, emailer
from app.config import get_settings
from tests.conftest import signup


@pytest.fixture
def sent(monkeypatch):
    """Capture outbound email instead of printing it."""
    outbox: list[emailer.Message] = []

    def fake_send(message):
        outbox.append(message)
        return "test"

    monkeypatch.setattr(emailer, "send", fake_send)
    return outbox


def _token_from(message: emailer.Message) -> str:
    match = re.search(r"token=([A-Za-z0-9_\-]+)", message.text)
    assert match, f"no token in email body: {message.text}"
    return match.group(1)


def _user_row(email):
    from sqlalchemy import select

    from app.db import get_session_factory
    from app.models import User

    with get_session_factory()() as db:
        return db.execute(select(User).where(User.email == email)).scalar_one()


# --------------------------------------------------------------------------
# Signup and verification
# --------------------------------------------------------------------------


def test_signup_sends_a_verification_email(client, new_email, sent):
    r = signup(client, new_email)
    assert r.status_code == 201
    assert r.json()["email_verified"] is False
    assert len(sent) == 1
    assert sent[0].to == new_email
    assert "verify" in sent[0].subject.lower()


def test_signup_signs_the_user_in_immediately(client, new_email, sent):
    """Verification must not lock a new user out of their own account."""
    signup(client, new_email)
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/resumes").status_code == 200


def test_verify_link_marks_the_account_verified(client, new_email, sent):
    signup(client, new_email)
    token = _token_from(sent[0])
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["email_verified"] is True


def test_verification_token_is_single_use(client, new_email, sent):
    signup(client, new_email)
    token = _token_from(sent[0])
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200
    replay = client.post("/api/auth/verify-email", json={"token": token})
    assert replay.status_code == 400, "a verification token must not work twice"


def test_verification_token_expires(client, new_email, sent):
    from app.db import get_session_factory
    from app.models import AuthToken
    from app.models import utcnow
    from datetime import timedelta
    from sqlalchemy import select

    signup(client, new_email)
    token = _token_from(sent[0])
    with get_session_factory()() as db:
        row = db.execute(select(AuthToken).where(AuthToken.purpose == "verify")).scalars().first()
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()

    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 400


def test_unknown_verification_token_is_rejected(client, new_email, sent):
    signup(client, new_email)
    r = client.post("/api/auth/verify-email", json={"token": "not-a-real-token"})
    assert r.status_code == 400


def test_resend_verification_issues_a_new_token(client, new_email, sent):
    signup(client, new_email)
    first = _token_from(sent[0])
    r = client.post("/api/auth/resend-verification", json={})
    assert r.status_code == 200
    second = _token_from(sent[1])
    assert first != second
    # The old token is invalidated when a new one is issued.
    assert client.post("/api/auth/verify-email", json={"token": first}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": second}).status_code == 200


def test_resend_refuses_when_already_verified(client, new_email, sent):
    signup(client, new_email)
    client.post("/api/auth/verify-email", json={"token": _token_from(sent[0])})
    assert client.post("/api/auth/resend-verification", json={}).status_code == 409


# --------------------------------------------------------------------------
# Password reset
# --------------------------------------------------------------------------


def test_forgot_password_sends_a_reset_link(client, new_email, sent):
    signup(client, new_email)
    sent.clear()
    r = client.post("/api/auth/forgot-password", json={"email": new_email})
    assert r.status_code == 200
    assert len(sent) == 1
    assert "reset" in sent[0].subject.lower()


def test_forgot_password_does_not_reveal_whether_an_account_exists(client, new_email, sent):
    """The response must be identical for known and unknown addresses."""
    signup(client, new_email)
    sent.clear()
    known = client.post("/api/auth/forgot-password", json={"email": new_email})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody-here@example.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(sent) == 1, "email is sent only for the real account"


def test_reset_password_changes_the_password(client, new_email, sent):
    signup(client, new_email)
    sent.clear()
    client.post("/api/auth/forgot-password", json={"email": new_email})
    token = _token_from(sent[0])

    r = client.post("/api/auth/reset-password", json={"token": token, "password": "a-brand-new-password"})
    assert r.status_code == 200

    client.cookies.clear()
    old = client.post("/api/auth/login", json={"email": new_email, "password": "correct horse battery staple"})
    assert old.status_code == 401, "the old password must stop working"
    new = client.post("/api/auth/login", json={"email": new_email, "password": "a-brand-new-password"})
    assert new.status_code == 200


def test_reset_token_is_single_use(client, new_email, sent):
    signup(client, new_email)
    sent.clear()
    client.post("/api/auth/forgot-password", json={"email": new_email})
    token = _token_from(sent[0])
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "first-new-password"}).status_code == 200
    replay = client.post("/api/auth/reset-password", json={"token": token, "password": "second-new-password"})
    assert replay.status_code == 400, "a reset token must not work twice"


def test_reset_revokes_existing_sessions(client, new_email, sent):
    """An attacker holding a stolen session loses it when the owner resets."""
    signup(client, new_email)
    stolen = client.cookies.get("tj_session")

    sent.clear()
    client.post("/api/auth/forgot-password", json={"email": new_email})
    token = _token_from(sent[0])
    client.post("/api/auth/reset-password", json={"token": token, "password": "another-new-password"})

    # Replay the pre-reset cookie.
    client.cookies.clear()
    client.cookies.set("tj_session", stolen)
    assert client.get("/api/auth/me").status_code == 401


def test_reset_rejects_a_verification_token(client, new_email, sent):
    """Tokens are scoped by purpose and cannot be used across flows."""
    signup(client, new_email)
    verify_token = _token_from(sent[0])
    r = client.post("/api/auth/reset-password", json={"token": verify_token, "password": "some-new-password"})
    assert r.status_code == 400


def test_reset_rejects_a_short_password(client, new_email, sent):
    signup(client, new_email)
    sent.clear()
    client.post("/api/auth/forgot-password", json={"email": new_email})
    token = _token_from(sent[0])
    r = client.post("/api/auth/reset-password", json={"token": token, "password": "short"})
    assert r.status_code == 422


# --------------------------------------------------------------------------
# Captcha
# --------------------------------------------------------------------------


def test_captcha_is_skipped_when_not_configured_locally(client, new_email, sent):
    """With no secret and not in production, flows work for development."""
    assert get_settings().turnstile_secret == ""
    assert signup(client, new_email).status_code == 201


def test_captcha_fails_closed_in_production_without_a_secret(client, new_email, monkeypatch):
    """A missing secret in production must not silently disable protection."""
    monkeypatch.setenv("VERCEL", "1")
    get_settings.cache_clear()
    try:
        r = signup(client, new_email)
        assert r.status_code == 503
    finally:
        monkeypatch.delenv("VERCEL", raising=False)
        get_settings.cache_clear()


def test_captcha_rejects_a_missing_token_when_configured(client, new_email, monkeypatch):
    monkeypatch.setattr(captcha, "enabled", lambda: True)
    monkeypatch.setattr(get_settings(), "turnstile_secret", "test-secret", raising=False)
    r = signup(client, new_email)
    assert r.status_code == 400
    assert "bot check" in r.json()["detail"].lower()


def test_captcha_rejects_a_failed_verification(client, new_email, monkeypatch):
    monkeypatch.setattr(get_settings(), "turnstile_secret", "test-secret", raising=False)

    class FakeResponse:
        def json(self):
            return {"success": False, "error-codes": ["invalid-input-response"]}

    monkeypatch.setattr(captcha.httpx, "post", lambda *a, **k: FakeResponse())
    r = client.post(
        "/api/auth/signup",
        json={"email": new_email, "password": "correct horse battery staple", "captcha_token": "bad"},
    )
    assert r.status_code == 400


def test_captcha_verification_outage_fails_closed(client, new_email, monkeypatch):
    """If Cloudflare is unreachable, signup must not be open to bots."""
    monkeypatch.setattr(get_settings(), "turnstile_secret", "test-secret", raising=False)

    def boom(*args, **kwargs):
        raise captcha.httpx.ConnectError("network down")

    monkeypatch.setattr(captcha.httpx, "post", boom)
    r = client.post(
        "/api/auth/signup",
        json={"email": new_email, "password": "correct horse battery staple", "captcha_token": "x"},
    )
    assert r.status_code == 503


def test_auth_config_never_leaks_the_secret(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "turnstile_secret", "super-secret-value", raising=False)
    monkeypatch.setattr(get_settings(), "turnstile_site_key", "public-site-key", raising=False)
    body = client.get("/api/auth/config").json()
    assert body["captcha_enabled"] is True
    assert body["captcha_site_key"] == "public-site-key"
    assert "super-secret-value" not in str(body)


# --------------------------------------------------------------------------
# Email driver
# --------------------------------------------------------------------------


def test_console_driver_does_not_raise(capsys):
    emailer.send(emailer.verification_email("a@example.com", "http://x/#/verify-email?token=t", 24))
    out = capsys.readouterr().out
    assert "EMAIL NOT SENT" in out
    assert "a@example.com" in out


def test_smtp_failure_raises_a_friendly_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "email_driver", "smtp", raising=False)
    monkeypatch.setattr(get_settings(), "smtp_host", "127.0.0.1", raising=False)
    monkeypatch.setattr(get_settings(), "smtp_port", 1, raising=False)
    with pytest.raises(emailer.EmailError):
        emailer.send(emailer.verification_email("a@example.com", "http://x", 24))


# --------------------------------------------------------------------------
# Development link fallback
#
# When no mail provider is configured the API can return the action link so
# the UI can show it. The rules that matter: it is on outside production, it
# is OFF in production unless explicitly enabled, and it is never returned
# from forgot-password (which would leak whether an account exists).
# --------------------------------------------------------------------------


def test_link_fallback_is_active_outside_production(client, new_email, sent):
    r = signup(client, new_email)
    assert r.status_code == 201
    link = r.json().get("verification_link")
    assert link, "development should return the verification link"
    assert "/#/verify-email?token=" in link


def test_link_fallback_is_off_in_production(client, new_email, sent, monkeypatch):
    """The most important assertion here: a public deployment must not hand
    out a working verification link to whoever asked."""
    monkeypatch.setenv("VERCEL", "1")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(get_settings(), "turnstile_secret", "s", raising=False)
        monkeypatch.setattr(captcha.httpx, "post", lambda *a, **k: _ok_captcha())
        r = client.post(
            "/api/auth/signup",
            json={"email": new_email, "password": "correct horse battery staple", "captcha_token": "t"},
        )
        assert r.status_code == 201
        assert r.json().get("verification_link") == "", "production must not leak the link"
    finally:
        monkeypatch.delenv("VERCEL", raising=False)
        get_settings.cache_clear()


def test_link_fallback_can_be_enabled_in_production(client, new_email, sent, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    get_settings.cache_clear()
    try:
        monkeypatch.setattr(get_settings(), "turnstile_secret", "s", raising=False)
        monkeypatch.setattr(get_settings(), "allow_link_fallback", True, raising=False)
        monkeypatch.setattr(captcha.httpx, "post", lambda *a, **k: _ok_captcha())
        r = client.post(
            "/api/auth/signup",
            json={"email": new_email, "password": "correct horse battery staple", "captcha_token": "t"},
        )
        assert r.status_code == 201
        assert r.json().get("verification_link"), "explicit opt-in should expose the link"
    finally:
        monkeypatch.delenv("VERCEL", raising=False)
        get_settings.cache_clear()


def test_link_fallback_is_absent_once_a_provider_is_configured(client, new_email, sent, monkeypatch):
    monkeypatch.setattr(get_settings(), "email_driver", "resend", raising=False)
    monkeypatch.setattr(get_settings(), "resend_api_key", "test", raising=False)
    monkeypatch.setattr(emailer, "_send_resend", lambda message: None)
    r = signup(client, new_email)
    assert r.status_code == 201
    assert r.json().get("verification_link") == "", "a real send must not echo the link"


def test_forgot_password_never_returns_a_link(client, new_email, sent):
    """No link from the public endpoint, in any mode: a link that appears
    only for real accounts would make this an enumeration oracle."""
    signup(client, new_email)
    sent.clear()
    known = client.post("/api/auth/forgot-password", json={"email": new_email})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert known.json() == unknown.json()
    body = str(known.json())
    assert "token=" not in body
    assert "http" not in body


def test_signed_in_user_can_get_their_own_reset_link(client, new_email, sent):
    """The enumeration-safe way to offer the link in development: the caller
    is already authenticated as the owner, so it reveals nothing new."""
    signup(client, new_email)
    r = client.post("/api/auth/reset-link")
    assert r.status_code == 200
    link = r.json()["reset_link"]
    assert "/#/reset-password?token=" in link

    # And it actually works.
    token = link.split("token=")[1]
    assert client.post(
        "/api/auth/reset-password", json={"token": token, "password": "a-fresh-password"}
    ).status_code == 200


def test_reset_link_requires_authentication(client):
    client.cookies.clear()
    assert client.post("/api/auth/reset-link").status_code == 401


def test_reset_link_is_empty_in_production_without_opt_in(client, new_email, sent, monkeypatch):
    signup(client, new_email)
    monkeypatch.setenv("VERCEL", "1")
    get_settings.cache_clear()
    try:
        r = client.post("/api/auth/reset-link")
        assert r.status_code == 200
        assert r.json()["reset_link"] == ""
    finally:
        monkeypatch.delenv("VERCEL", raising=False)
        get_settings.cache_clear()


def test_config_reports_delivery_mode(client):
    assert client.get("/api/auth/config").json()["delivery"] == "exposed"


class _ok_captcha:
    status_code = 200

    def json(self):
        return {"success": True}
