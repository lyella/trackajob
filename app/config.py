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

    # Tailoring LLM (any OpenAI-compatible chat completions API).
    llm_base_url: str = "https://api.mistral.ai/v1"
    llm_api_key: str = ""
    llm_model: str = "mistral-small-latest"
    llm_price_in: float = 0.10
    llm_price_out: float = 0.30

    app_name: str = "TrackAJob"
    debug: bool = False

    # --- Email delivery ---------------------------------------------------
    # "console" prints messages to the server log (default, so every flow is
    # testable before credentials exist), "smtp" uses a mail server, and
    # "resend" uses the Resend HTTP API.
    email_driver: str = "console"
    email_from: str = "TrackAJob <no-reply@trackajob.local>"

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True

    resend_api_key: str = ""

    # --- Bot protection ---------------------------------------------------
    # Cloudflare Turnstile. The site key is public and served to the browser;
    # the secret stays on the server.
    turnstile_site_key: str = ""
    turnstile_secret: str = ""

    # --- Links ------------------------------------------------------------
    # Absolute base URL used in verification and reset emails. Must be the
    # public origin, or the links in the email will not work.
    app_base_url: str = "http://localhost:5173"

    verify_token_hours: int = 24
    reset_token_minutes: int = 60

    @property
    def is_production(self) -> bool:
        """Vercel sets VERCEL=1 in its build and runtime environments."""
        return bool(os.environ.get("VERCEL")) or os.environ.get("APP_ENV") == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
