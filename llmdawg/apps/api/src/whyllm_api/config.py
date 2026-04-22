"""Application configuration loaded from environment variables via pydantic-settings."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _resolve_database_url() -> str:
    """Prefer DATABASE_URL; fall back to Vercel Postgres env vars (POSTGRES_URL).
    Ensures the asyncpg driver prefix is present."""
    url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("POSTGRES_URL_NON_POOLING")
        or "postgresql+asyncpg://whyllm:whyllm@localhost:5432/whyllm"
    )
    # Vercel Postgres uses plain postgresql:// — swap in the asyncpg driver
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _resolve_redis_url() -> str:
    """Prefer REDIS_URL; fall back to Vercel KV env vars (KV_URL)."""
    return (
        os.environ.get("REDIS_URL")
        or os.environ.get("KV_URL")
        or "redis://localhost:6379/0"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application ----------------------------------------------------------
    app_name: str = "whyllm API"
    api_version: str = Field(default="0.1.0", alias="API_VERSION")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    debug: bool = Field(default=False, alias="DEBUG")

    # ---- Database -------------------------------------------------------------
    # Reads DATABASE_URL or Vercel's POSTGRES_URL automatically via _resolve_database_url()
    database_url: str = Field(default_factory=_resolve_database_url, alias="DATABASE_URL")

    # SQLAlchemy connection pool — keep small on serverless (each cold start = new pool)
    db_pool_size: int = Field(default=5, alias="DB_POOL_SIZE")
    db_max_overflow: int = Field(default=10, alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=1800, alias="DB_POOL_RECYCLE")

    # ---- Redis ----------------------------------------------------------------
    # Reads REDIS_URL or Vercel KV's KV_URL automatically via _resolve_redis_url()
    redis_url: str = Field(default_factory=_resolve_redis_url, alias="REDIS_URL")

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

    # Comma-separated frontend origins allowed by CORS.
    # e.g. CORS_ORIGINS=https://whyllm.vercel.app,https://whyllm.io
    cors_origins: str = Field(
        default="http://localhost:14392,http://127.0.0.1:14392",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # ---- Admin ----------------------------------------------------------------
    admin_emails: str = Field(default="", alias="ADMIN_EMAILS")

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    # ---- Optional LLM keys (hallucination judge) ------------------------------
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")

    @field_validator("environment", mode="before")
    @classmethod
    def strip_environment(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @field_validator("database_url", mode="before")
    @classmethod
    def ensure_asyncpg_driver(cls, v: str) -> str:
        """Ensure the asyncpg driver prefix is present regardless of how the URL was set."""
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("postgresql://") or v.startswith("postgres://"):
                v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
                v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

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
