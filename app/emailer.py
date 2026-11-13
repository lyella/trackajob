"""Outbound email.

A provider interface with three drivers, chosen by configuration:

- ``console`` (default): prints the message to the server log. This is what
  makes every flow testable before any mail credentials exist, and it is
  deliberately loud so it can never be mistaken for real delivery.
- ``smtp``: any mail server (Gmail, Fastmail, a company relay).
- ``resend``: the Resend HTTP API.

Switching drivers is a configuration change, never a code change. If sending
fails, the caller decides what to do; this module raises ``EmailError`` rather
than swallowing the failure, because a password reset that silently does not
send is worse than one that reports an error.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.config import get_settings


class EmailError(Exception):
    """Delivery failed. The message is safe to show a user."""


@dataclass
class Message:
    to: str
    subject: str
    text: str
    html: str | None = None


def _from_address() -> str:
    settings = get_settings()
    return settings.email_from or "TrackAJob <no-reply@trackajob.local>"


def _send_console(message: Message) -> None:
    """Print instead of sending. Loud on purpose: this must never look like
    a successful real send during a demo or a production misconfiguration."""
    line = "=" * 72
    print(line, flush=True)
    print("EMAIL NOT SENT (console driver): no mail provider is configured.", flush=True)
    print(f"  To:      {message.to}", flush=True)
    print(f"  Subject: {message.subject}", flush=True)
    print(line, flush=True)
    print(message.text, flush=True)
    print(line, flush=True)


def _send_smtp(message: Message) -> None:
    settings = get_settings()
    msg = EmailMessage()
    msg["From"] = _from_address()
    msg["To"] = message.to
    msg["Subject"] = message.subject
    msg.set_content(message.text)
    if message.html:
        msg.add_alternative(message.html, subtype="html")

    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
                server.ehlo()
                if settings.smtp_starttls:
                    server.starttls()
                    server.ehlo()
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailError("We could not send that email right now. Try again in a moment.") from exc


def _send_resend(message: Message) -> None:
    settings = get_settings()
    payload = {
        "from": _from_address(),
        "to": [message.to],
        "subject": message.subject,
        "text": message.text,
    }
    if message.html:
        payload["html"] = message.html
    try:
        response = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json=payload,
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise EmailError("We could not send that email right now. Try again in a moment.") from exc
    if response.status_code >= 400:
        raise EmailError("We could not send that email right now. Try again in a moment.")


def send(message: Message) -> str:
    """Send one message. Returns the driver used, for logging and tests."""
    settings = get_settings()
    driver = settings.email_driver
    if driver == "console":
        _send_console(message)
        return "console"
    if driver == "smtp":
        _send_smtp(message)
        return "smtp"
    if driver == "resend":
        _send_resend(message)
        return "resend"
    raise EmailError(f"Unknown email driver: {driver}")


# --------------------------------------------------------------------------
# Message templates
# --------------------------------------------------------------------------


def verification_email(to: str, link: str, hours: int) -> Message:
    return Message(
        to=to,
        subject="Verify your TrackAJob email",
        text=(
            "Confirm your email address to finish setting up TrackAJob.\n\n"
            f"{link}\n\n"
            f"This link works once and expires in {hours} hours.\n"
            "If you did not create an account, you can ignore this email.\n"
        ),
        html=(
            '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.6">'
            "<p>Confirm your email address to finish setting up TrackAJob.</p>"
            f'<p><a href="{link}">Verify my email</a></p>'
            f'<p style="color:#666">This link works once and expires in {hours} hours. '
            "If you did not create an account, you can ignore this email.</p></div>"
        ),
    )


def reset_email(to: str, link: str, minutes: int) -> Message:
    return Message(
        to=to,
        subject="Reset your TrackAJob password",
        text=(
            "Someone asked to reset the password for this TrackAJob account.\n\n"
            f"{link}\n\n"
            f"This link works once and expires in {minutes} minutes.\n"
            "If this was not you, no action is needed: your password has not changed.\n"
        ),
        html=(
            '<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.6">'
            "<p>Someone asked to reset the password for this TrackAJob account.</p>"
            f'<p><a href="{link}">Choose a new password</a></p>'
            f'<p style="color:#666">This link works once and expires in {minutes} minutes. '
            "If this was not you, no action is needed: your password has not changed.</p></div>"
        ),
    )
