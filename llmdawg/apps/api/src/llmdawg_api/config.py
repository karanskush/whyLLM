"""Application configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # Allow extra env vars without raising errors (e.g. Docker-injected vars)
        extra="ignore",
    )

    # ---- Application ----------------------------------------------------------
    app_name: str = "LLMDawg API"
    api_version: str = Field(default="0.1.0", alias="API_VERSION")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=False, alias="DEBUG")

    # ---- Database -------------------------------------------------------------
    # Must be postgresql+asyncpg://... for async SQLAlchemy
    database_url: str = Field(
        default="postgresql+asyncpg://llmdawg:llmdawg@localhost:5432/llmdawg",
        alias="DATABASE_URL",
    )

    # SQLAlchemy connection pool tuning
    db_pool_size: int = Field(default=10, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=20, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, alias="DB_POOL_RECYCLE")

    # ---- Redis ----------------------------------------------------------------
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        alias="REDIS_URL",
    )

    # ---- Auth -----------------------------------------------------------------
    secret_key: str = Field(
        default="change-me-in-production-min-32-chars",
        alias="SECRET_KEY",
    )
    access_token_expire_minutes: int = Field(
        default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    refresh_token_expire_days: int = Field(
        default=7, alias="REFRESH_TOKEN_EXPIRE_DAYS"
    )
    algorithm: str = "HS256"

    # ---- External URLs --------------------------------------------------------
    api_base_url: str = Field(
        default="http://localhost:8000", alias="API_BASE_URL"
    )

    # ---- Admin ----------------------------------------------------------------
    # Comma-separated list of emails that can access /api/v1/admin/* routes.
    # e.g. ADMIN_EMAILS=you@example.com,teammate@example.com
    admin_emails: str = Field(default="", alias="ADMIN_EMAILS")

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    # ---- Optional LLM keys (hallucination judge) ------------------------------
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    @field_validator("secret_key")
    @classmethod
    def secret_key_min_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
