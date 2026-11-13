# ADR-0010: Email verification, password reset, and bot protection

## Status

Accepted

## Context

The first release had email and password signup with no verification, no
recovery, and no bot protection. PLAN.md deferred all three ("real email
flows arrive only if other people start using the app"). That is no longer
acceptable: a user who forgets a password has no way back into their account,
and an open signup endpoint is free for spam accounts.

Three questions had to be settled: how email is sent, which captcha, and
whether an unverified account can use the app.

## Decision

### Email: pluggable driver, console by default

`app/emailer.py` defines one `send(Message)` interface with three drivers:

- `console` (default) prints the message to the server log;
- `smtp` for any mail server;
- `resend` for the Resend HTTP API.

Switching is an environment change, never a code change.

**Why console is the default.** Every flow is then fully testable before any
mail credentials exist, including in CI. The output is deliberately loud
("EMAIL NOT SENT") so it can never be mistaken for real delivery during a
demo or a production misconfiguration.

### Captcha: Cloudflare Turnstile

Free, privacy-friendly, no image puzzles, and the widget can be swapped for
reCAPTCHA later without touching the server contract.

**It fails closed.** Three cases, all deliberate:

- No secret configured in production: protected requests return 503. A
  missing environment variable must not silently disable the defence.
- No secret locally: the check is skipped, so development and tests work.
- Cloudflare unreachable: 503. A verification outage is not an open door.

The site key is served by `GET /api/auth/config`; the secret never leaves the
server. A test asserts the config response does not contain the secret.

### Verification: nudge, do not block

A new account is signed in immediately and shown a banner until the address is
confirmed.

Blocking would be stricter against fake signups, but it makes a broken mail
provider a total outage: nobody can sign up, and the failure looks like the
app is down. Nudging keeps the app usable and degrades gracefully. The
tradeoff is accepted: this is a personal job tracker, not a bank.

## Token design

- Random 32-byte URL-safe tokens.
- Only the SHA-256 hash is stored (`auth_tokens.token_hash`). A database leak
  therefore does not contain working reset links.
- Single use (`used_at`) and expiring (24 h verify, 60 min reset).
- Scoped by purpose: a verification token cannot reset a password.
- Issuing a new token marks older unused ones as used.
- Password reset revokes every session for that user, then signs the user
  back in so the legitimate owner is not kicked out.

## Account enumeration

`POST /api/auth/forgot-password` returns an identical body and status whether
or not the address exists, and swallows delivery failures, because a distinct
error would leak that the account is real. The email is sent only when there
is an account.

This was verified by introducing a 404 for unknown addresses and watching the
test fail.

## Consequences

- Two new tables/columns: `users.email_verified`, `users.email_verified_at`,
  and `auth_tokens`. The migration in `db.ensure_schema_upgrades` backfills
  existing users as verified, so nobody is locked out by the upgrade.
- `APP_BASE_URL` must be set to the public origin in production, or emailed
  links point at localhost. This is the most likely deployment mistake.
- There is no rate limiting yet. The captcha covers the automated case; a
  determined attacker can still hammer `forgot-password` for a known address.
  Add per-IP and per-address throttling before opening signup publicly.
- Verification and reset links are single-use, so a user who opens the same
  email twice sees "invalid or expired". The message says to request a new
  one, which is the correct next step.
- The frontend must key the token screens by token (`key={route.token}`).
  Without it React reuses the component and a second link inherits the first
  one's success state. This was a real bug found while testing.
