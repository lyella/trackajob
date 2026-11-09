from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local default is SQLite so the app runs with zero setup.
    # In production set DATABASE_URL to the Neon connection string, e.g.
    # postgresql+psycopg://user:password@host/dbname?sslmode=require
    database_url: str = "sqlite:///./trackajob.db"

    app_name: str = "TrackAJob"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
