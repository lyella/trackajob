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


def get_engine():
    global _engine
    if _engine is None:
        url = normalize_url(get_settings().database_url)
        if url.startswith("sqlite"):
            # SQLite needs check_same_thread=False for FastAPI's threadpool.
            _engine = create_engine(url, connect_args={"check_same_thread": False})
        else:
            # Neon suspends idle databases, so always verify the connection.
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
