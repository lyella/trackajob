import os
import os

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    # Vercel's serverless filesystem is read-only except /tmp, so the SQLite
    # fallback has to live there in production. No DATABASE_URL means no real
    # data survives, but health checks and boot work.
    if os.environ.get("VERCEL"):
        return "sqlite:////tmp/trackajob.db"
    return "sqlite:///./trackajob.db"


class Settings(BaseSettings):
    # Real environment variables always beat these files, so Vercel's
    # DATABASE_URL wins in production. Locally .env is manual overrides and
    # .env.local holds what the Neon CLI writes (last file wins).
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    # In production set DATABASE_URL to the database connection string.
    database_url: str = Field(default_factory=_default_database_url)
    # An empty value in an env file (e.g. the template line in .env.example)
    # must mean "not set", not "parse an empty URL and crash".
    @field_validator("database_url", mode="before")
    @classmethod
    def _empty_url_means_default(cls, value):
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return _default_database_url()
        return value

    # Turso remote connections need the database auth token separately.
    turso_auth_token: str = ""

    app_name: str = "TrackAJob"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
