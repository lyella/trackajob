"""Login verification for unfamiliar locations and devices.

The properties that matter:

- a familiar device in a familiar country signs in with no code;
- a new country or a new device triggers a code;
- a wrong code never signs anyone in, and cannot be brute-forced;
- a code is single use and expires;
- the feature degrades safely when the platform gives no country.
"""
import uuid

import pytest

from app import emailer, loginverify
from app.config import get_settings
from tests.conftest import signup

PASSWORD = "correct horse battery staple"


@pytest.fixture
def sent(monkeypatch):
    outbox: list[emailer.Message] = []

    def fake_send(message):
        outbox.append(message)
        return "test"

    monkeypatch.setattr(emailer, "send", fake_send)
    return outbox


def _login(client, email, headers=None):
    return client.post(
        "/api/auth/login",
        json={"email": email, "password": PASSWORD},
        headers=headers or {},
    )


def _code_from(message: emailer.Message) -> str:
    # The subject carries the code: "Your TrackAJob sign-in code: 123456"
    return message.subject.rsplit(":", 1)[-1].strip()


# --------------------------------------------------------------------------
# When a code is required
# --------------------------------------------------------------------------


def test_no_country_header_skips_verification(client, new_email, sent):
    """Local development and self-hosting send no geo header. Guessing
    "suspicious" there would prompt on every single login."""
    signup(client, new_email)
    client.cookies.clear()
    r = _login(client, new_email)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_new_country_requires_a_code(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()
    r = _login(client, new_email, headers={"x-vercel-ip-country": "PH"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "code_required"
    assert body["country"] == "PH"
    assert body["sent_to"].startswith(new_email[0])  # masked
    assert "@" in body["sent_to"]
    assert len(sent) >= 1
    assert "sign-in code" in sent[-1].subject


def test_known_device_and_country_signs_in_without_a_code(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()

    first = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    code = _code_from(sent[-1])
    ok = client.post(
        "/api/auth/login/verify",
        json={"challenge": first["challenge"], "code": code},
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "ok"

    # Same browser, same country: no code the second time.
    client.cookies.clear()
    second = _login(client, new_email, headers={"x-vercel-ip-country": "PH"})
    assert second.json()["status"] == "ok"


def test_different_country_requires_a_code_again(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()

    first = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    client.post(
        "/api/auth/login/verify",
        json={"challenge": first["challenge"], "code": _code_from(sent[-1])},
    )

    # Same browser, different country: prompt again.
    client.cookies.clear()
    other = _login(client, new_email, headers={"x-vercel-ip-country": "US"})
    assert other.json()["status"] == "code_required"


def test_different_device_requires_a_code(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()

    first = _login(
        client,
        new_email,
        headers={"x-vercel-ip-country": "PH", "user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/120"},
    ).json()
    client.post(
        "/api/auth/login/verify",
        json={"challenge": first["challenge"], "code": _code_from(sent[-1])},
    )

    # Different browser on the same country: prompt again.
    client.cookies.clear()
    other = _login(
        client,
        new_email,
        headers={"x-vercel-ip-country": "PH", "user-agent": "Mozilla/5.0 (iPhone) Safari/604"},
    )
    assert other.json()["status"] == "code_required"


def test_wrong_password_never_starts_a_challenge(client, new_email, sent):
    """A challenge must only exist once the password is known to be right,
    otherwise it leaks that the address exists."""
    signup(client, new_email)
    client.cookies.clear()
    sent.clear()
    r = client.post(
        "/api/auth/login",
        json={"email": new_email, "password": "wrong"},
        headers={"x-vercel-ip-country": "PH"},
    )
    assert r.status_code == 401
    assert sent == []


def test_verification_can_be_disabled(client, new_email, sent, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_code_enabled", False, raising=False)
    signup(client, new_email)
    client.cookies.clear()
    r = _login(client, new_email, headers={"x-vercel-ip-country": "PH"})
    assert r.json()["status"] == "ok"


# --------------------------------------------------------------------------
# The code itself
# --------------------------------------------------------------------------


def test_wrong_code_is_rejected(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()
    ch = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    r = client.post(
        "/api/auth/login/verify", json={"challenge": ch["challenge"], "code": "000000"}
    )
    assert r.status_code == 401
    assert client.get("/api/auth/me").status_code == 401, "no session on a wrong code"


def test_code_is_single_use(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()
    ch = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    code = _code_from(sent[-1])

    first = client.post("/api/auth/login/verify", json={"challenge": ch["challenge"], "code": code})
    assert first.status_code == 200

    client.cookies.clear()
    replay = client.post("/api/auth/login/verify", json={"challenge": ch["challenge"], "code": code})
    assert replay.status_code == 401


def test_code_expires(client, new_email, sent):
    from sqlalchemy import select

    from app.db import get_session_factory
    from app.models import LoginChallenge, utcnow
    from datetime import timedelta

    signup(client, new_email)
    client.cookies.clear()
    ch = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    code = _code_from(sent[-1])

    with get_session_factory()() as db:
        row = db.execute(select(LoginChallenge)).scalars().first()
        row.expires_at = utcnow() - timedelta(minutes=1)
        db.commit()

    r = client.post("/api/auth/login/verify", json={"challenge": ch["challenge"], "code": code})
    assert r.status_code == 401


def test_brute_force_is_cut_off_after_five_attempts(client, new_email, sent):
    """A 6-digit code is only 1e6 guesses; the attempt cap is what makes it
    safe. After the cap even the correct code must fail."""
    signup(client, new_email)
    client.cookies.clear()
    ch = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    correct = _code_from(sent[-1])

    for _ in range(loginverify.MAX_ATTEMPTS):
        client.post("/api/auth/login/verify", json={"challenge": ch["challenge"], "code": "000000"})

    r = client.post("/api/auth/login/verify", json={"challenge": ch["challenge"], "code": correct})
    assert r.status_code == 401, "the challenge must be dead after too many wrong guesses"


def test_resend_retires_the_previous_code(client, new_email, sent):
    signup(client, new_email)
    client.cookies.clear()
    first = _login(client, new_email, headers={"x-vercel-ip-country": "PH"}).json()
    first_code = _code_from(sent[-1])
    _login(client, new_email, headers={"x-vercel-ip-country": "PH"})

    r = client.post(
        "/api/auth/login/verify", json={"challenge": first["challenge"], "code": first_code}
    )
    assert r.status_code == 401, "starting a new challenge invalidates the old one"


def test_unknown_challenge_is_rejected(client):
    r = client.post("/api/auth/login/verify", json={"challenge": "nope", "code": "123456"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def test_fingerprint_is_stable_and_coarse():
    a = loginverify.fingerprint_for("Mozilla/5.0 (Windows NT 10.0) Chrome/120", "en-US,en")
    b = loginverify.fingerprint_for("Mozilla/5.0 (Windows NT 10.0) Chrome/121", "en-US,en")
    assert a == b, "a browser version bump must not look like a new device"

    c = loginverify.fingerprint_for("Mozilla/5.0 (iPhone) Safari/604", "en-US,en")
    assert a != c, "a different platform is a different device"


def test_country_header_parsing():
    from starlette.datastructures import Headers

    assert loginverify.country_for(Headers({"x-vercel-ip-country": "PH"})) == "PH"
    assert loginverify.country_for(Headers({"cf-ipcountry": "us"})) == "US"
    assert loginverify.country_for(Headers({})) == ""
    assert loginverify.country_for(Headers({"x-vercel-ip-country": "XX1"})) == ""
