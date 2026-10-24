from __future__ import annotations

import shutil
from pathlib import Path

import check_migrations
import pytest
from sqlalchemy import text

from app.db import migrate, protection
from app.db.connection import Database

REAL = migrate.MIGRATIONS_DIR
NL = chr(10)


@pytest.fixture
def mig_dir(tmp_path: Path) -> Path:
    """A copy of the foundation migration only (0001 + its lock line), so these tests can add
    their own `0002_*` files whatever later migrations exist in the real directory."""
    target = tmp_path / "migrations"
    target.mkdir()
    shutil.copy(REAL / "0001_foundation.sql", target)
    lock = (REAL / "checksums.lock").read_text(encoding="utf-8").splitlines()
    kept = [line for line in lock if line.startswith("#") or line.startswith("0001 ")]
    (target / "checksums.lock").write_text(NL.join(kept) + NL, encoding="utf-8")
    return target


def test_migrate_applies_once_and_is_idempotent(empty_db: Database) -> None:
    every = [m.filename for m in migrate.discover()]
    assert every[0] == "0001_foundation.sql"
    assert migrate.migrate(empty_db) == every
    assert migrate.migrate(empty_db) == []
    with empty_db.read_tx() as conn:
        ledger = migrate.read_ledger(conn)
        names = set(protection.list_tables(conn))
    assert ledger[1][0] == "0001_foundation.sql"
    assert ledger[1][1] == migrate.discover()[0].sha256
    assert {"schema_migrations", "audit_log", "file", "job"} <= names
    assert migrate.pending(empty_db) == []


def test_real_migrations_match_the_committed_lock() -> None:
    assert check_migrations.check(REAL) == []


def test_checksum_ignores_line_endings(mig_dir: Path) -> None:
    before = migrate.discover(mig_dir)[0].sha256
    path = mig_dir / "0001_foundation.sql"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert migrate.discover(mig_dir)[0].sha256 == before
    assert check_migrations.check(mig_dir) == []


def test_tampered_migration_is_detected_by_the_lock(mig_dir: Path) -> None:
    path = mig_dir / "0001_foundation.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- sneaky edit\n", encoding="utf-8")
    problems = check_migrations.check(mig_dir)
    assert any("differs from checksums.lock" in p for p in problems)
    assert check_migrations.main(["--dir", str(mig_dir), "--db", str(mig_dir / "none.db")]) == 1


def test_tampered_migration_is_detected_by_the_database_ledger(
    mig_dir: Path, tmp_path: Path
) -> None:
    db = Database(tmp_path / "ledger.db")
    migrate.migrate(db, mig_dir)
    db.close()
    path = mig_dir / "0001_foundation.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- sneaky edit\n", encoding="utf-8")
    check_migrations.amend_lock(mig_dir, 1)  # even with a fixed-up lock the ledger still objects
    problems = check_migrations.check(mig_dir, tmp_path / "ledger.db")
    assert any("changed after it was applied" in p for p in problems)


def test_runner_refuses_to_apply_on_top_of_a_changed_migration(
    mig_dir: Path, tmp_path: Path
) -> None:
    db = Database(tmp_path / "ledger.db")
    migrate.migrate(db, mig_dir)
    path = mig_dir / "0001_foundation.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- sneaky edit\n", encoding="utf-8")
    (mig_dir / "0002_more.sql").write_text(
        "CREATE TABLE extra (id TEXT PRIMARY KEY, deleted_at TEXT) STRICT;\n", encoding="utf-8"
    )
    with pytest.raises(migrate.MigrationError, match="changed after it was applied"):
        migrate.migrate(db, mig_dir)
    db.close()


def test_new_file_must_be_registered_and_update_never_rewrites_old_hashes(mig_dir: Path) -> None:
    (mig_dir / "0002_more.sql").write_text("CREATE TABLE extra_t (id TEXT) STRICT;\n")
    assert any("not registered" in p for p in check_migrations.check(mig_dir))
    path = mig_dir / "0001_foundation.sql"
    path.write_text(path.read_text(encoding="utf-8") + "\n-- edit\n", encoding="utf-8")
    assert check_migrations.update_lock(mig_dir) == ["0002_more.sql"]
    assert any("0001_foundation.sql differs" in p for p in check_migrations.check(mig_dir))


def test_missing_renamed_and_gapped_files_are_detected(mig_dir: Path) -> None:
    (mig_dir / "0003_gap.sql").write_text("SELECT 1;\n")
    assert any("contiguous" in p for p in check_migrations.check(mig_dir))
    (mig_dir / "0003_gap.sql").unlink()
    (mig_dir / "0001_foundation.sql").rename(mig_dir / "0001_renamed.sql")
    assert any("registered as 0001_foundation.sql" in p for p in check_migrations.check(mig_dir))
    (mig_dir / "0001_renamed.sql").unlink()
    assert any("file is missing" in p for p in check_migrations.check(mig_dir))
    (mig_dir / "oops.sql").write_text("SELECT 1;\n")
    assert any("bad migration filename" in p for p in check_migrations.check(mig_dir))


def test_split_statements_keeps_trigger_bodies_together() -> None:
    sql = (
        "-- header\nCREATE TABLE t (a TEXT) STRICT;\n"
        "CREATE TRIGGER trg BEFORE DELETE ON t\nBEGIN SELECT RAISE(ABORT, 'no; way'); END;\n"
        "INSERT INTO t VALUES ('x;y');\n-- trailing comment\n"
    )
    parts = migrate.split_statements(sql)
    assert len(parts) == 3
    assert parts[1].startswith("CREATE TRIGGER") and parts[1].endswith("END;")
    with pytest.raises(migrate.MigrationError):
        migrate.split_statements("CREATE TABLE broken (a TEXT")


def test_failed_migration_rolls_back_completely(mig_dir: Path, tmp_path: Path) -> None:
    (mig_dir / "0002_bad.sql").write_text(
        "CREATE TABLE half (id TEXT PRIMARY KEY) STRICT;\nTHIS IS NOT SQL;\n"
    )
    db = Database(tmp_path / "rb.db")
    with pytest.raises(Exception, match="syntax error"):
        migrate.migrate(db, mig_dir)
    with db.read_tx() as conn:
        assert "half" not in protection.list_tables(conn)
        assert set(migrate.read_ledger(conn)) == {1}
    db.close()


def test_unclassified_table_makes_the_migration_fail(mig_dir: Path, tmp_path: Path) -> None:
    (mig_dir / "0002_orphan.sql").write_text(
        "CREATE TABLE orphan_values (id TEXT PRIMARY KEY, v TEXT) STRICT;\n"
    )
    db = Database(tmp_path / "orphan.db")
    with pytest.raises(migrate.MigrationError, match="orphan_values"):
        migrate.migrate(db, mig_dir)
    with db.read_tx() as conn:
        assert "orphan_values" not in protection.list_tables(conn)
    db.close()


def test_later_business_tables_get_triggers_automatically(mig_dir: Path, tmp_path: Path) -> None:
    (mig_dir / "0002_biz.sql").write_text(
        "CREATE TABLE widget (id TEXT PRIMARY KEY, name TEXT, created_at TEXT, deleted_at TEXT) STRICT;\n"
        "CREATE TABLE membership_component (a TEXT, b TEXT) STRICT;\n"
        "CREATE TABLE submission_revision (id TEXT PRIMARY KEY, v TEXT) STRICT;\n"
    )
    db = Database(tmp_path / "biz.db")
    migrate.migrate(db, mig_dir)
    with db.write_tx() as conn:
        conn.execute(text("INSERT INTO widget (id) VALUES ('w')"))
        conn.execute(text("INSERT INTO membership_component VALUES ('a','b')"))
        conn.execute(text("INSERT INTO submission_revision VALUES ('r','v')"))
    for table in ("widget", "submission_revision"):
        with pytest.raises(Exception, match="hard delete forbidden"), db.write_tx() as conn:
            conn.exec_driver_sql(f"DELETE FROM {table}")
    with db.write_tx() as conn:  # exempt: allowed
        conn.exec_driver_sql("DELETE FROM membership_component")
    db.close()


def test_two_runners_starting_together_apply_once(tmp_path: Path) -> None:
    import threading

    path = tmp_path / "race.db"
    results: list[list[str]] = []
    errors: list[BaseException] = []

    def run() -> None:
        database = Database(path)
        try:
            results.append(migrate.migrate(database))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            database.close()

    threads = [threading.Thread(target=run) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert sorted(len(r) for r in results) == [0] * 7 + [len(migrate.discover())]
