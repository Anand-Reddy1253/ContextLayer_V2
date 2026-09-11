"""Application settings, loaded from environment variables / .env.

Mirrors .env.example exactly. No default carries a real secret —
CF_SECRET_KEY and every live-connector credential default to None and must
be supplied by the deployment environment (docs/SECURITY.md).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Runtime mode ---
    CF_MODE: str = "fixture"  # "fixture" | "live"

    # --- Database ---
    CF_DATABASE_URL: str = (
        "postgresql+psycopg://context_fabric:context_fabric@localhost:5432/context_fabric"
    )

    # --- Secrets-at-rest key for encrypted connector credentials ---
    CF_SECRET_KEY: str | None = None

    # --- API / MCP ---
    CF_API_HOST: str = "0.0.0.0"
    CF_API_PORT: int = 8000
    CF_MCP_HTTP_PORT: int = 8100
    CF_LOG_LEVEL: str = "INFO"
    CF_LOG_FORMAT: str = "json"

    # --- CORS ---
    CF_CORS_ORIGINS: str = "http://localhost:5173"

    # --- Azure DevOps (live mode only) ---
    CF_ADO_ORG_URL: str | None = None
    CF_ADO_PAT: str | None = None

    # --- GitHub (live mode only) ---
    CF_GITHUB_APP_ID: str | None = None
    CF_GITHUB_APP_PRIVATE_KEY_PATH: str | None = None
    CF_GITHUB_TOKEN: str | None = None
