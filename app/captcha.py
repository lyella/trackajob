"""Bot protection, using Cloudflare Turnstile.

Turnstile is the default because it is free, privacy-friendly, and needs no
image puzzles. The widget runs in the browser and produces a token; the
server verifies that token against Cloudflare before allowing signup, login,
or password reset.

Behaviour by configuration:

- ``TURNSTILE_SECRET`` set: every protected request must carry a valid token.
  Verification errors fail closed, because a captcha that fails open is not a
  captcha.
- ``TURNSTILE_SECRET`` unset: verification is skipped, but only when the app
  is not in production. In production with no secret configured, protected
  requests are refused with a clear error rather than silently unprotected.
  That is the safer failure: a misconfiguration must not quietly disable the
  defence.

The site key is served to the frontend by ``GET /api/auth/config`` so the
widget can render itself; the secret never leaves the server.
"""

from __future__ import annotations

import httpx

from app.config import get_settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class CaptchaError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def enabled() -> bool:
    return bool(get_settings().turnstile_secret)


def verify(token: str | None, remote_ip: str | None = None) -> None:
    """Raise CaptchaError unless the request passes bot checks."""
    settings = get_settings()

    if not settings.turnstile_secret:
        if settings.is_production:
            # Fail closed: never run a public signup with no bot protection
            # because of a missing environment variable.
            raise CaptchaError(
                "Sign-up is temporarily unavailable. Please try again later.",
                status=503,
            )
        return  # local development and tests

    if not token:
        raise CaptchaError("Complete the bot check and try again.")

    data = {"secret": settings.turnstile_secret, "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    try:
        response = httpx.post(VERIFY_URL, data=data, timeout=10)
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        # A verification outage must not become an open door.
        raise CaptchaError(
            "We could not check the bot challenge. Try again in a moment.", status=503
        ) from exc

    if not payload.get("success"):
        raise CaptchaError("The bot check failed. Try again.")
