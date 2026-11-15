"""Application configuration.

All configuration – including platform credentials – is read from environment
variables (optionally via a local ``.env`` file). Nothing secret is ever
hard-coded or committed; see ``.env.example`` for the full list of settings.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application -------------------------------------------------------
    app_name: str = "Automated Multi-Platform Posting API"
    app_version: str = "1.0.0"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    timezone: str = Field(
        default="UTC",
        description="IANA timezone used for the posting date/time in responses.",
    )

    # --- Outbound HTTP behaviour ------------------------------------------
    http_timeout_seconds: float = Field(default=15.0, gt=0)
    platform_timeout_seconds: float = Field(
        default=30.0,
        gt=0,
        description="Hard upper bound for one platform, including retries.",
    )
    http_max_retries: int = Field(default=2, ge=0, le=5)
    http_backoff_seconds: float = Field(default=0.5, ge=0)
    verify_public_access: bool = Field(
        default=True,
        description="Probe each published URL anonymously to confirm it is public.",
    )

    # --- Telegram (Bot API) -----------------------------------------------
    telegram_bot_token: SecretStr | None = None
    telegram_chat_id: str | None = None

    # --- Discord (Webhooks) -----------------------------------------------
    discord_webhook_url: SecretStr | None = None

    # --- Mastodon ---------------------------------------------------------
    mastodon_base_url: str = "https://mastodon.social"
    mastodon_access_token: SecretStr | None = None

    # --- Bluesky (AT Protocol) --------------------------------------------
    bluesky_service_url: str = "https://bsky.social"
    bluesky_handle: str | None = None
    bluesky_app_password: SecretStr | None = None

    # --- GitHub Gists -----------------------------------------------------
    github_token: SecretStr | None = None

    # --- DEV Community (Forem API) ----------------------------------------
    devto_api_key: SecretStr | None = None
    devto_tags: str = "business,marketing"

    # --- Hugging Face Hub -------------------------------------------------
    huggingface_token: SecretStr | None = None
    huggingface_repo_id: str | None = None
    huggingface_repo_type: Literal["dataset", "model", "space"] = "dataset"

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"Unknown timezone: {value!r}") from exc
        return value

    @field_validator("mastodon_base_url", "bluesky_service_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (cached)."""
    return Settings()
