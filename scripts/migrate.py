"""Apply pending migrations to DATABASE_PATH (`make migrate`)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db.connection import Database  # noqa: E402
from app.db.migrate import migrate  # noqa: E402
from app.logging_setup import configure_logging  # noqa: E402


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    db = Database(
        settings.database_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        begin_retries=settings.sqlite_begin_retries,
    )
    try:
        applied = migrate(db)
    finally:
        db.close()
    print("applied: " + ", ".join(applied) if applied else "database is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
