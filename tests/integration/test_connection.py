from __future__ import annotations

import threading
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.db.connection import Database, check_sqlite_version, is_busy_error


def test_sqlite_version_is_acceptable() -> None:
    check_sqlite_version()


def test_pragmas_on_write_and_read_connections(db: Database) -> None:
    with db.write_tx() as conn:
        pragmas = {
            name: conn.exec_driver_sql(f"PRAGMA {name}").scalar()
            for name in (
                "journal_mode",
                "synchronous",
                "foreign_keys",
                "busy_timeout",
                "temp_store",
                "cache_size",
                "query_only",
            )
        }
    assert pragmas == {
        "journal_mode": "wal",
        "synchronous": 1,  # NORMAL
        "foreign_keys": 1,
        "busy_timeout": 5000,
        "temp_store": 2,  # MEMORY
        "cache_size": -64000,
        "query_only": 0,
    }
    with db.read_tx() as conn:
        assert conn.exec_driver_sql("PRAGMA query_only").scalar() == 1
        assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1


def test_write_commits_and_is_visible_to_readers(db: Database) -> None:
    with db.write_tx() as conn:
        conn.execute(
            text(
                "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                "VALUES ('a','noop','queued','{}','t','t')"
            )
        )
    with db.read_tx() as conn:
        assert conn.execute(text("SELECT count(*) FROM job")).scalar() == 1


def test_write_rolls_back_on_exception(db: Database) -> None:
    with pytest.raises(RuntimeError), db.write_tx() as conn:
        conn.execute(
            text(
                "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                "VALUES ('a','noop','queued','{}','t','t')"
            )
        )
        raise RuntimeError("boom")
    with db.read_tx() as conn:
        assert conn.execute(text("SELECT count(*) FROM job")).scalar() == 0


def test_write_is_begin_immediate_and_autocommit_between_transactions(db: Database) -> None:
    with db.write_tx() as conn:
        raw = conn.connection.dbapi_connection
        assert raw is not None and raw.in_transaction  # type: ignore[attr-defined]
    # after the block the pooled driver connection is back in autocommit, outside any transaction
    with db.write_engine.connect() as conn:
        raw = conn.connection.dbapi_connection
        assert raw is not None and raw.isolation_level is None  # type: ignore[attr-defined]
        assert not raw.in_transaction  # type: ignore[attr-defined]


def test_write_inside_read_tx_is_refused(db: Database) -> None:
    with pytest.raises(OperationalError, match="readonly"), db.read_tx() as conn:
        conn.exec_driver_sql("DELETE FROM job")


def test_read_tx_sees_a_stable_snapshot(db: Database) -> None:
    with db.read_tx() as reader:
        assert reader.execute(text("SELECT count(*) FROM job")).scalar() == 0
        with db.write_tx() as writer:
            writer.execute(
                text(
                    "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                    "VALUES ('a','noop','queued','{}','t','t')"
                )
            )
        assert reader.execute(text("SELECT count(*) FROM job")).scalar() == 0  # snapshot


def _hold_write_lock(db: Database, acquired: threading.Event, release: threading.Event) -> None:
    with db.write_tx():
        acquired.set()
        release.wait(10)


def test_begin_immediate_retries_on_busy_then_succeeds(db: Database) -> None:
    impatient = Database(db.path, busy_timeout_ms=20, begin_retries=8)
    acquired, release = threading.Event(), threading.Event()
    holder = threading.Thread(target=_hold_write_lock, args=(db, acquired, release))
    holder.start()
    assert acquired.wait(5)
    threading.Timer(0.4, release.set).start()
    try:
        with impatient.write_tx() as conn:
            conn.execute(
                text(
                    "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                    "VALUES ('x','noop','queued','{}','t','t')"
                )
            )
        assert impatient.busy_retries >= 1
    finally:
        release.set()
        holder.join()
        impatient.close()


def test_busy_error_is_raised_when_retries_are_exhausted(db: Database) -> None:
    impatient = Database(db.path, busy_timeout_ms=10, begin_retries=1)
    acquired, release = threading.Event(), threading.Event()
    holder = threading.Thread(target=_hold_write_lock, args=(db, acquired, release))
    holder.start()
    assert acquired.wait(5)
    try:
        started = time.monotonic()
        with pytest.raises(OperationalError) as info, impatient.write_tx():
            pass
        assert is_busy_error(info.value)
        assert time.monotonic() - started < 3
    finally:
        release.set()
        holder.join()
        impatient.close()


def test_run_write_repeats_the_unit_of_work(db: Database) -> None:
    calls = {"n": 0}

    def work(conn):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] < 3:
            raise OperationalError("stmt", {}, Exception("database is locked"))
        return "done"

    assert db.run_write(work, retries=5) == "done"
    assert calls["n"] == 3
    assert db.busy_retries >= 2
