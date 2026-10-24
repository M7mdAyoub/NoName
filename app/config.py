"""Settings from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRET = "change-me"  # noqa: S105
DEV_ENVS = ("development", "test")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    database_path: Path = Path("./data/app.db")
    files_path: Path = Path("./data/files")
    backup_path: Path = Path("./data/backups")
    secret_key: str = PLACEHOLDER_SECRET
    identity_hmac_key: str = PLACEHOLDER_SECRET
    cors_origins: str = "http://localhost:5173"
    access_token_minutes: int = 15
    refresh_token_days: int = 30

    # auto: call LLM_BASE_URL when it and LLM_MODEL_EXTRACT are set, else the built-in mock
    llm_mode: Literal["auto", "mock", "real"] = "auto"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model_extract: str = ""
    llm_model_fast: str = ""
    llm_model_vision: str = ""
    llm_max_concurrency: int = Field(default=4, ge=1)
    llm_timeout_seconds: int = Field(default=180, ge=1)
    llm_is_external: bool = False

    upload_max_mb: int = Field(default=25, ge=1)

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=0)
    sqlite_begin_retries: int = Field(default=5, ge=0)
    job_poll_seconds: float = Field(default=1.0, gt=0)
    job_stale_check_seconds: float = Field(default=60.0, gt=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_base_url and self.llm_model_extract)

    @property
    def llm_use_mock(self) -> bool:
        return self.llm_mode == "mock" or (self.llm_mode == "auto" and not self.llm_configured)

    @model_validator(mode="after")
    def _refuse_placeholder_secrets(self) -> Settings:
        if self.app_env not in DEV_ENVS:
            for name in ("secret_key", "identity_hmac_key"):
                if getattr(self, name) in ("", PLACEHOLDER_SECRET):
                    raise ValueError(f"{name.upper()} must be set when APP_ENV={self.app_env}")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
