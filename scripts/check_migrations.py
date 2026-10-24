"""Verify migrations: numbering, checksums vs migrations/checksums.lock, and the database ledger.

python scripts/check_migrations.py            check (exit 1 on any problem)
python scripts/check_migrations.py --update   register NEW files in the lock (never changes old hashes)
python scripts/check_migrations.py --amend N  re-hash migration N (only for a migration not yet
                                              applied anywhere; record the amendment in DECISIONS.md)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db import migrate, protection  # noqa: E402
from app.db.connection import Database  # noqa: E402


def check(directory: Path, db_path: Path | None = None) -> list[str]:
    try:
        migrations = migrate.discover(directory)
    except migrate.MigrationError as exc:
        return [str(exc)]
    problems = migrate.compare_with_lock(migrations, migrate.read_lock(directory))
    if db_path is not None and db_path.exists():
        db = Database(db_path)
        try:
            with db.read_tx() as conn:
                ledger = migrate.read_ledger(conn)
                problems += migrate.compare_with_ledger(migrations, ledger)
                if ledger:
                    problems += protection.verify_triggers(conn)
        finally:
            db.close()
    return problems


def update_lock(directory: Path) -> list[str]:
    migrations = migrate.discover(directory)
    lock = migrate.read_lock(directory)
    added: list[str] = []
    for m in migrations:
        if m.version not in lock:
            lock[m.version] = (m.filename, m.sha256)
            added.append(m.filename)
    migrate.write_lock(lock, directory)
    return added


def amend_lock(directory: Path, version: int) -> str:
    migrations = {m.version: m for m in migrate.discover(directory)}
    if version not in migrations:
        raise SystemExit(f"no migration {version:04d}")
    lock = migrate.read_lock(directory)
    m = migrations[version]
    lock[version] = (m.filename, m.sha256)
    migrate.write_lock(lock, directory)
    return m.filename


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--amend", type=int, metavar="N")
    parser.add_argument("--dir", type=Path, default=migrate.MIGRATIONS_DIR)
    parser.add_argument(
        "--db", type=Path, default=None, help="database to check (default: DATABASE_PATH)"
    )
    args = parser.parse_args(argv)

    if args.update:
        added = update_lock(args.dir)
        print("registered:", ", ".join(added) if added else "nothing new")
        return 0
    if args.amend is not None:
        name = amend_lock(args.dir, args.amend)
        print(f"re-hashed {name}. Record this amendment in docs/handoff/DECISIONS.md.")
        return 0

    db_path = args.db
    if db_path is None:
        from app.config import get_settings

        db_path = get_settings().database_path
    problems = check(args.dir, db_path)
    for problem in problems:
        print(f"FAIL: {problem}")
    if not problems:
        count = len(migrate.discover(args.dir))
        print(f"migrations ok ({count} files)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
