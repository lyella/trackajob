"""Shared fixtures. One throwaway SQLite file per pytest run, chosen BEFORE
the app modules import, because engine and settings cache at first use.
The engine is disposed after each test so Windows file handles release."""
import os
import tempfile
import uuid
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / f"trackajob_test_{uuid.uuid4().hex[:8]}.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.db as db_module  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_database():
    yield
    # Release the file handles so each test can start from an empty database.
    if db_module._engine is not None:
        db_module._engine.dispose()
        db_module._engine = None
        db_module._session_factory = None
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def new_email():
    return f"user-{uuid.uuid4().hex[:12]}@example.com"


def signup(client, email, password="correct horse battery staple"):
    return client.post(
        "/api/auth/signup", json={"email": email, "password": password}
    )
