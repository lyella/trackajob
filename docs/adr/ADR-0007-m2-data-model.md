# ADR-0007: M2 data model and session design

## Status

Accepted

## Context

M2 adds accounts and the versioned resume model that M6's diff and revert
depend on. Two decisions were non-obvious and are recorded here.

## Decision 1: Resume versions are full JSON snapshots, not normalized rows

The PRD described sections and entries, which suggests tables per section.
The model instead stores each version as one JSON snapshot row
(`resume_versions.content`), with the same schema the tailoring CLI uses.

Reasons:

- Diff and revert are the whole point of versioning. Comparing two JSON
  documents is a solved problem and reads well in the UI. Comparing graphs of
  section rows requires joins, row identity juggling, and reassembly logic,
  all for zero user-visible benefit at this scale.
- The M6 tailor produces JSON and the CLI consumes JSON. Snapshots let the
  same shape flow from spike to product unchanged.
- SQLAlchemy querying inside resume sections is not a need anywhere in v1.

Tradeoff, named honestly: you cannot write SQL against individual bullets.
If a reporting feature ever needs that, the JSON is parseable and the model
can be normalized later, at a real cost.

## Decision 2: stdlib scrypt hashing, opaque DB-backed session cookies

- Passwords hash with `hashlib.scrypt` (stdlib): memory-hard, no binary
  dependency added to the serverless bundle, parameters recorded in code.
- Sessions are opaque random tokens in the `sessions` table, delivered as
  HttpOnly cookies with SameSite=Lax and the Secure flag in production.
  Chosen over JWTs because logout genuinely revokes a session (deleting a
  row), which matters for a job seeker using a shared computer. JWTs would
  keep working after "logout" until expiry.

## CSRF posture, honestly

SameSite=Lax cookies plus a JSON-only API give reasonable CSRF protection for
a single-user app. A dedicated CSRF token flow is deferred; it becomes
mandatory before this app is shared publicly.

## Schema creation

`Base.metadata.create_all()` runs in the app lifespan, idempotently. Fine at
this scale, on SQLite, Turso, and Neon alike. Add a real migration tool the
first time a schema change must preserve data.
