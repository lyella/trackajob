# ADR-0006: Production database moves from Neon Postgres to Turso (libSQL)

## Status

Accepted

## Context

The developer asked for SQLite to be used in production, given a user count
under ten. SQLite in production is a sound choice on paper for this
workload, but Vercel serverless functions have no persistent disk, so an
on-disk database file cannot survive requests (ADR-0005). The options were
documented in the conversation: Turso (hosted SQLite over a wire protocol,
free tier, works from Vercel with no rewrite), Fly or Railway with a real
volume (not free), Oracle Cloud free VM (free but real sysadmin work), or
keeping Neon Postgres (free, boring, already working).

Turso was chosen as a deliberate learning exercise and to align the
production engine with the SQLite used locally. It is recorded here that
the primary motivation is learning, not product need: nothing a user would
perceive changes.

## Verified facts at decision time

- Turso is an active, funded company; its engine is being rewritten in Rust
  and that rewrite was at 0.x versions, still evolving.
- The Python SQLAlchemy dialect, `sqlalchemy-libsql` (PyPI 0.2.0), is
  labeled by Turso themselves as experimental and "not considered
  production grade", and ships native components for Linux and macOS only.
- `turso_serverless`, a pure-Python DB-API client over HTTP, exists for
  connectivity testing from Windows.
- Turso free tier covers this project's scale with large margin.

## Decision

Production database: Turso (libSQL dialect for the deployed function).
Local development: unchanged, plain SQLite file, because the libsql native
driver does not ship for Windows and a local file is faster anyway.

Wiring is purely environment driven in `app/db.py`: `DATABASE_URL` starting
with `libsql://` or `https://` selects the Turso engine, `postgresql` selects
Neon, `sqlite` selects the local file.

## Consequences and mitigations

- The experimental-dialect risk is accepted because the blast radius is
  small: a personal tool with no data yet, a single non-commercial user,
  and the whole database layer reversible by swapping two environment
  variables in Vercel back to the Neon values. No code changes are needed
  to roll back, and the Neon project stays configured as the fallback.
- The deployed function gets real write coverage only when M2 introduces
  tables; until then, health checks plus explicit remote write/read tests
  via `turso_serverless` prove the connection.
- If Turso pricing, the dialect, or the engine rewrite ever makes this
  regrettable, the rollback is an env var swap plus one redeploy.
- Neon Postgres stays provisioned and free. It becomes the escape hatch
  instead of the default.
