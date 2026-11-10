from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory = None


def normalize_url(url: str) -> str:
    """Neon gives postgresql:// connection strings. SQLAlchemy needs the
    psycopg (v3) driver named explicitly, while psycopg2 is not installed."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


def _create_remote_engine(url: str):
    """Turso (libsql) remote connection via the sqlalchemy-libsql dialect.

    The dialect (v0.2.0) rebuilds a https URL from the parsed engine URL's
    host and path (libsql.py: _build_connection_url), so the scheme from the
    Turso connection string must be stripped here. Passing the raw
    libsql:// URL into the engine string makes SQLAlchemy parse an empty
    port and crash; verified against the deployed function's error.
    The dialect package only ships for Linux and macOS, which is fine:
    local development runs on a plain SQLite file, only the deployed Vercel
    function (Linux) uses this path."""
    from app.config import get_settings

    host_part = url.split("://", 1)[-1]
    engine_url = f"sqlite+libsql://{host_part}?secure=true"
    return create_engine(
        engine_url,
        connect_args={"auth_token": get_settings().turso_auth_token},
        pool_pre_ping=True,
    )


def get_engine():
    global _engine
    if _engine is None:
        url = normalize_url(get_settings().database_url)
        if url.startswith(("libsql://", "https://")) and url not in ("", "sqlite"):
            _engine = _create_remote_engine(url)
        elif url.startswith("sqlite"):
            # SQLite needs check_same_thread=False for FastAPI's threadpool.
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # Plain Postgres (Neon). It suspends idle databases, so always
            # verify the connection.
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _session_factory


def get_db() -> Iterator[Session]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
