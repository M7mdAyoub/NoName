"""Settings from environment variables (see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator
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
    # the frontend's Vite dev server (outputs/impactos-frontend) on either local name
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # built frontend (npm run build); served at /app/ when present. Relative to the repository.
    # Empty turns it off (an empty path would otherwise mean the repository itself).
    frontend_dist: Path | None = Path("outputs/impactos-frontend/dist")
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
    # Extra JSON fields for every chat request, e.g. for Qwen3.5 on vLLM without thinking:
    # LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}
    llm_extra_body: dict[str, Any] = Field(default_factory=dict)
    # Strict structured outputs (`strict: true`, every field required): needed on Groq, whose
    # best-effort JSON mode often returns broken JSON. Leave off for vLLM.
    llm_strict_schema: bool = False
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

    @field_validator("frontend_dist", mode="before")
    @classmethod
    def _empty_means_off(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

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
