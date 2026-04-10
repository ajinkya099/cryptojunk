"""Application configuration via pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # ── Database ─────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./iga_dev.db"

    # ── Redis / Celery ────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Security ─────────────────────────────────────────────────
    secret_key: str = "dev-secret-key-change-in-production"
    access_token_expire_minutes: int = 60

    # ── Anthropic / AI Agents ─────────────────────────────────────
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    agent_model: str = "claude-sonnet-4-6"
    agent_max_tokens: int = 4096
    agent_confidence_threshold: float = 0.85
    agent_dry_run: bool = True  # Safety: True means agents log but don't execute

    # ── Certification ─────────────────────────────────────────────
    cert_campaign_auto_approve_threshold: float = 0.95
    cert_campaign_auto_revoke_threshold: float = 0.80
    cert_campaign_default_duration_days: int = 14

    # ── SoD ───────────────────────────────────────────────────────
    sod_auto_remediate: bool = False
    sod_alert_email: str = "iga-alerts@example.com"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url

    @property
    def celery_result_backend(self) -> str:
        return self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
