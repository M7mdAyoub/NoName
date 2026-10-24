"""Plain-SQL migration runner with a checksum ledger (plan §2, decision D-04).

Files are `migrations/NNNN_name.sql`, numbered 0001.. without gaps. Applied files are never edited:
the SHA-256 (line endings normalised to LF) is stored in `schema_migrations` and in the committed
`migrations/checksums.lock`.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Connection

from app.db import protection
from app.db.connection import Database
from app.db.ids import utc_now

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
LOCK_NAME = "checksums.lock"
_FILENAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


class MigrationError(Exception):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    path: Path
    sha256: str
    sql: str


def normalized_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Read and validate the migration files (names, numbering without gaps or duplicates)."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = _FILENAME.match(path.name)
        if not match:
            raise MigrationError(f"bad migration filename: {path.name} (want NNNN_name.sql)")
        raw = path.read_bytes()
        found.append(
            Migration(
                version=int(match.group(1)),
                filename=path.name,
                path=path,
                sha256=normalized_sha256(raw),
                sql=raw.decode("utf-8").replace("\r\n", "\n"),
            )
        )
    for expected, migration in enumerate(found, start=1):
        if migration.version != expected:
            raise MigrationError(
                f"migration numbering must be contiguous: expected {expected:04d}, "
                f"found {migration.filename}"
            )
    return found


def split_statements(sql: str) -> list[str]:
    """Split a script into statements; trigger bodies keep their inner semicolons."""
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    leftover = re.sub(r"--[^\n]*", "", buffer).strip()
    if leftover:
        raise MigrationError(f"incomplete statement at end of script: {leftover[:60]!r}")
    return statements


def read_ledger(conn: Connection) -> dict[int, tuple[str, str]]:
    """version -> (filename, sha256). Empty when the ledger table does not exist yet."""
    has_table = conn.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
    ).first()
    if not has_table:
        return {}
    rows = conn.exec_driver_sql("SELECT version, filename, sha256 FROM schema_migrations")
    return {r[0]: (r[1], r[2]) for r in rows}


def compare_with_ledger(
    migrations: list[Migration], ledger: dict[int, tuple[str, str]]
) -> list[str]:
    """Problems where applied migrations and files disagree."""
    problems: list[str] = []
    by_version = {m.version: m for m in migrations}
    for version, (filename, sha) in sorted(ledger.items()):
        migration = by_version.get(version)
        if migration is None:
            problems.append(f"applied migration {version:04d} ({filename}) has no file")
        elif migration.filename != filename:
            problems.append(
                f"migration {version:04d} was applied as {filename}, file is {migration.filename}"
            )
        elif migration.sha256 != sha:
            problems.append(f"migration {migration.filename} was changed after it was applied")
    if ledger:
        top = max(ledger)
        for version in range(1, top):
            if version not in ledger:
                problems.append(
                    f"migration {version:04d} is missing from the ledger below {top:04d}"
                )
    return problems


def read_lock(directory: Path = MIGRATIONS_DIR) -> dict[int, tuple[str, str]]:
    path = directory / LOCK_NAME
    if not path.exists():
        return {}
    entries: dict[int, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        version, filename, sha = line.split()
        entries[int(version)] = (filename, sha)
    return entries


def write_lock(entries: dict[int, tuple[str, str]], directory: Path = MIGRATIONS_DIR) -> None:
    lines = ["# version filename sha256 (LF-normalised). Maintained by scripts/check_migrations.py"]
    lines += [f"{v:04d} {name} {sha}" for v, (name, sha) in sorted(entries.items())]
    (directory / LOCK_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def compare_with_lock(migrations: list[Migration], lock: dict[int, tuple[str, str]]) -> list[str]:
    problems: list[str] = []
    by_version = {m.version: m for m in migrations}
    for version, (filename, sha) in sorted(lock.items()):
        migration = by_version.get(version)
        if migration is None:
            problems.append(f"{filename} is in {LOCK_NAME} but the file is missing")
        elif migration.filename != filename:
            problems.append(
                f"{version:04d} was registered as {filename}, file is {migration.filename}"
            )
        elif migration.sha256 != sha:
            problems.append(
                f"{migration.filename} differs from {LOCK_NAME} (applied migrations are never edited)"
            )
    for migration in migrations:
        if migration.version not in lock:
            problems.append(
                f"{migration.filename} is not registered; run scripts/check_migrations.py --update"
            )
    return problems


def pending(db: Database, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    migrations = discover(directory)
    with db.read_tx() as conn:
        ledger = read_ledger(conn)
    return [m for m in migrations if m.version not in ledger]


def migrate(db: Database, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply every pending migration, one transaction per file. Returns the filenames applied."""
    migrations = discover(directory)
    applied_now: list[str] = []
    for migration in migrations:
        if _apply_one(db, migration, migrations):
            applied_now.append(migration.filename)
    with db.write_tx() as conn:
        protection.ensure_triggers(conn)
    return applied_now


def _apply_one(db: Database, migration: Migration, all_migrations: list[Migration]) -> bool:
    with db.write_tx() as conn:
        ledger = read_ledger(conn)  # re-read under the write lock: another process may have won
        problems = compare_with_ledger(all_migrations, ledger)
        if problems:
            raise MigrationError("; ".join(problems))
        if migration.version in ledger:
            return False
        log.info("applying migration", extra={"migration": migration.filename})
        for statement in split_statements(migration.sql):
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(
            "INSERT INTO schema_migrations (version, filename, sha256, applied_at) VALUES (?, ?, ?, ?)",
            (migration.version, migration.filename, migration.sha256, utc_now()),
        )
        protection.ensure_triggers(conn)
        unclassified = protection.unclassified_tables(conn)
        if unclassified:
            raise MigrationError(
                f"{migration.filename} creates tables that app/db/protection.py does not classify: "
                f"{', '.join(unclassified)}"
            )
    return True
