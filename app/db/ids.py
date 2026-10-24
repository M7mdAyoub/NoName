"""Identifiers and timestamps shared by every table (UUIDv7, ISO-8601 UTC)."""

from __future__ import annotations

from datetime import UTC, datetime

import uuid_utils


def new_id() -> str:
    """A time-ordered UUIDv7 as a lowercase hyphenated string."""
    return str(uuid_utils.uuid7())


def utc_now() -> str:
    """Current time as `2026-10-24T09:30:00.000Z`. Strings of this shape sort chronologically."""
    return to_iso(datetime.now(UTC))


def to_iso(moment: datetime) -> str:
    return (
        moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
    )


def from_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
