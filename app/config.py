import os
import os

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    # Vercel's serverless filesystem is read-only except /tmp, so the SQLite
    # fallback has to live there in production. No DATABASE_URL means no real
    # data survives, but health checks and boot work.
    if os.environ.get("VERCEL"):
        return "sqlite:////tmp/trackajob.db"
    return "sqlite:///./trackajob.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # In production set DATABASE_URL to the Neon connection string.
    database_url: str = Field(default_factory=_default_database_url)

    app_name: str = "TrackAJob"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
