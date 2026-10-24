from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.db.ids import from_iso, new_id, to_iso, utc_now
from app.logging_setup import JsonFormatter, accept_or_make_request_id, request_id_var

ROOT = Path(__file__).resolve().parents[2]


def test_uuid7_is_time_ordered_and_unique() -> None:
    ids = [new_id() for _ in range(200)]
    assert len(set(ids)) == 200
    assert ids == sorted(ids)
    assert ids[0][14] == "7"  # version nibble


def test_timestamp_format_round_trips() -> None:
    moment = datetime(2026, 10, 24, 9, 30, 0, 123456, tzinfo=UTC)
    assert to_iso(moment) == "2026-10-24T09:30:00.123Z"
    assert from_iso("2026-10-24T09:30:00.123Z").microsecond == 123000
    assert len(utc_now()) == len("2026-10-24T09:30:00.000Z")


def test_env_example_loads_in_development() -> None:
    settings = Settings(_env_file=ROOT / ".env.example")  # type: ignore[call-arg]
    assert settings.app_env == "development"
    assert settings.secret_key == "change-me"
    assert settings.cors_origin_list == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert settings.frontend_dist == Path("outputs/impactos-frontend/dist")
    assert settings.llm_max_concurrency == 4
    assert settings.llm_is_external is False
    assert not settings.llm_configured or settings.llm_model_extract
    assert settings.llm_use_mock  # a fresh copy runs without a model...
    assert settings.llm_model_extract == "qwen3.5"  # ...and is ready for scripts/serve_vllm.sh
    assert settings.llm_extra_body == {"chat_template_kwargs": {"enable_thinking": False}}


def test_placeholder_secrets_refused_outside_development() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(app_env="production", identity_hmac_key="x" * 32)
    ok = Settings(app_env="production", secret_key="a" * 32, identity_hmac_key="b" * 32)
    assert ok.app_env == "production"


def test_request_id_accepts_safe_values_only() -> None:
    assert accept_or_make_request_id("abc12345-def") == "abc12345-def"
    for bad in (None, "", "short", "has space in it", "x" * 65, 'evil"\n{"a":1}'):
        generated = accept_or_make_request_id(bad)
        assert generated != bad and len(generated) == 36


def test_json_log_line_carries_request_id() -> None:
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.job_id = "j1"
    token = request_id_var.set("req-12345678")
    try:
        entry = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert entry["msg"] == "hello world"
    assert entry["request_id"] == "req-12345678"
    assert entry["job_id"] == "j1"
    assert entry["level"] == "INFO"
