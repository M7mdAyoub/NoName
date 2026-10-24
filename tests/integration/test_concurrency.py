"""Two or more writers on one SQLite file must never surface `database is locked` (plan §3.2)."""

from __future__ import annotations

import multiprocessing
import threading
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import Settings
from app.db.connection import Database
from app.db.ids import new_id, utc_now
from app.db.migrate import migrate
from app.repositories.audit import write_audit

WRITERS = 4
PER_WRITER = 60


def _write_batch(db: Database, name: str, count: int) -> None:
    for i in range(count):
        with db.write_tx() as conn:
            conn.execute(
                text(
                    "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                    "VALUES (:id,'noop','queued','{}',:n,:n)"
                ),
                {"id": new_id(), "n": utc_now()},
            )
            write_audit(conn, action="create", table_name="job", row_id=f"{name}-{i}")


def _process_main(path: str, name: str, count: int, queue: multiprocessing.Queue[str]) -> None:
    settings = Settings(app_env="test")
    db = Database(path, busy_timeout_ms=settings.sqlite_busy_timeout_ms)
    try:
        _write_batch(db, name, count)
        queue.put("ok")
    except Exception as exc:  # noqa: BLE001
        queue.put(f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def _counts(db: Database) -> tuple[int, int]:
    with db.read_tx() as conn:
        jobs = conn.execute(text("SELECT count(*) FROM job")).scalar_one()
        audits = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
    return int(jobs), int(audits)


def test_threads_with_separate_connections_never_see_database_is_locked(db: Database) -> None:
    errors: list[BaseException] = []
    readers_ok = threading.Event()
    stop_readers = threading.Event()

    def writer(name: str) -> None:
        try:
            _write_batch(db, name, PER_WRITER)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    def reader() -> None:
        try:
            while not stop_readers.is_set():
                with db.read_tx() as conn:
                    jobs = conn.execute(text("SELECT count(*) FROM job")).scalar_one()
                    audits = conn.execute(text("SELECT count(*) FROM audit_log")).scalar_one()
                    assert jobs == audits  # one snapshot: change and audit row are atomic
            readers_ok.set()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    readers = [threading.Thread(target=reader) for _ in range(2)]
    writers = [threading.Thread(target=writer, args=(f"t{i}",)) for i in range(WRITERS)]
    for t in readers + writers:
        t.start()
    for t in writers:
        t.join()
    stop_readers.set()
    for t in readers:
        t.join()

    assert not errors, errors
    assert _counts(db) == (WRITERS * PER_WRITER, WRITERS * PER_WRITER)


def test_two_processes_writing_at_once(tmp_path: Path) -> None:
    path = tmp_path / "multi.db"
    setup = Database(path)
    migrate(setup)
    ctx = multiprocessing.get_context("spawn")
    results: multiprocessing.Queue[str] = ctx.Queue()
    procs = [
        ctx.Process(target=_process_main, args=(str(path), f"p{i}", PER_WRITER, results))
        for i in range(2)
    ]
    for p in procs:
        p.start()
    outcomes = [results.get(timeout=120) for _ in procs]
    for p in procs:
        p.join(30)
    try:
        assert outcomes == ["ok", "ok"], outcomes
        assert _counts(setup) == (2 * PER_WRITER, 2 * PER_WRITER)
    finally:
        setup.close()


def test_reader_is_not_blocked_by_an_open_write_transaction(db: Database) -> None:
    started = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with db.write_tx() as conn:
            conn.execute(
                text(
                    "INSERT INTO job (id,type,status,payload,run_after,created_at) "
                    "VALUES ('held','noop','queued','{}','t','t')"
                )
            )
            started.set()
            release.wait(10)

    thread = threading.Thread(target=hold)
    thread.start()
    try:
        assert started.wait(5)
        with db.read_tx() as conn:  # WAL: readers proceed, and do not see the uncommitted row
            assert conn.execute(text("SELECT count(*) FROM job")).scalar_one() == 0
    finally:
        release.set()
        thread.join()
    with db.read_tx() as conn:
        assert conn.execute(text("SELECT count(*) FROM job")).scalar_one() == 1


@pytest.mark.parametrize("writers", [8])
def test_many_threads_share_the_same_database_object(db: Database, writers: int) -> None:
    errors: list[BaseException] = []

    def work(i: int) -> None:
        try:
            _write_batch(db, f"m{i}", 20)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert _counts(db) == (writers * 20, writers * 20)
