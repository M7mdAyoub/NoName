from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from app.config import Settings  # noqa: E402
from app.db.connection import Database  # noqa: E402
from app.db.migrate import migrate  # noqa: E402


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        database_path=tmp_path / "app.db",
        files_path=tmp_path / "files",
        backup_path=tmp_path / "backups",
        job_poll_seconds=0.05,
    )


@pytest.fixture
def empty_db(tmp_path: Path) -> Iterator[Database]:
    database = Database(tmp_path / "empty.db")
    yield database
    database.close()


@pytest.fixture
def db(settings: Settings) -> Iterator[Database]:
    """A freshly migrated database."""
    database = Database(
        settings.database_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        begin_retries=settings.sqlite_begin_retries,
    )
    migrate(database)
    yield database
    database.close()
