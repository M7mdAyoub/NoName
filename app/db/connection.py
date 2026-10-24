"""SQLite connections, PRAGMAs and the explicit transaction helpers (plan §3, decision D-02).

Connections run in autocommit mode (`isolation_level=None`), so the sqlite3 driver never opens a
transaction behind our back. Transactions are started explicitly through a SQLAlchemy `begin`
event that issues `BEGIN DEFERRED` (reads) or `BEGIN IMMEDIATE` (writes).

Usage in repositories and services::

    with db.read_tx() as conn:        # snapshot, query_only, always rolled back
        rows = conn.execute(text("SELECT ..."), {...}).mappings().all()

    with db.write_tx() as conn:       # BEGIN IMMEDIATE ... COMMIT (ROLLBACK on exception)
        conn.execute(text("INSERT ..."), {...})
        write_audit(conn, ...)

Never call the LLM, parse files or do HTTP inside either block.
"""

from __future__ import annotations

import logging
import random
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import OperationalError

log = logging.getLogger(__name__)

MIN_SQLITE_VERSION = (3, 38, 0)
BEGIN_OPTION = "sqlite_begin"
IMMEDIATE = "IMMEDIATE"
DEFERRED = "DEFERRED"

T = TypeVar("T")

_PRAGMAS_COMMON = (
    "PRAGMA busy_timeout = {busy}",
    "PRAGMA foreign_keys = ON",
    "PRAGMA temp_store = MEMORY",
    "PRAGMA cache_size = -64000",
)


def check_sqlite_version() -> None:
    if sqlite3.sqlite_version_info < MIN_SQLITE_VERSION:
        need = ".".join(map(str, MIN_SQLITE_VERSION))
        raise RuntimeError(f"SQLite >= {need} required, found {sqlite3.sqlite_version}")


def is_busy_error(exc: BaseException) -> bool:
    """True for SQLITE_BUSY / SQLITE_LOCKED ("database is locked")."""
    orig = getattr(exc, "orig", exc)
    code = getattr(orig, "sqlite_errorcode", None)
    if code is not None:
        return (code & 0xFF) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
    text_ = str(orig).lower()
    return "database is locked" in text_ or "database table is locked" in text_


def _ensure_wal(cursor: sqlite3.Cursor, max_wait_s: float) -> None:
    """Switch the file to WAL. Changing the journal mode of a new file needs a lock that SQLite's
    busy handler does not wait for, so several processes starting together must retry it here."""
    deadline = time.monotonic() + max_wait_s
    while cursor.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
        try:
            cursor.execute("PRAGMA journal_mode = WAL").fetchall()
        except sqlite3.OperationalError as exc:
            if not is_busy_error(exc) or time.monotonic() > deadline:
                raise
            time.sleep(0.01 + random.random() * 0.04)  # noqa: S311


class Database:
    """Owns one read engine and one write engine on the same SQLite file."""

    def __init__(
        self,
        path: Path | str,
        *,
        busy_timeout_ms: int = 5000,
        begin_retries: int = 5,
    ) -> None:
        check_sqlite_version()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.busy_timeout_ms = busy_timeout_ms
        self.begin_retries = begin_retries
        self.busy_retries = 0
        self._lock = threading.Lock()
        self.write_engine = self._make_engine(read_only=False)
        self.read_engine = self._make_engine(read_only=True)
        with self.write_engine.connect():  # creates the file and switches it to WAL
            pass

    # -- engines ---------------------------------------------------------------------------

    def _make_engine(self, *, read_only: bool) -> Engine:
        engine = create_engine(
            f"sqlite:///{self.path.as_posix()}",
            connect_args={
                "isolation_level": None,
                "check_same_thread": False,
                "timeout": self.busy_timeout_ms / 1000,
            },
            # FastAPI's threadpool defaults to 40 threads; readers must not queue behind the pool
            pool_size=5 if not read_only else 20,
            max_overflow=10 if not read_only else 40,
        )
        pragmas = [p.format(busy=self.busy_timeout_ms) for p in _PRAGMAS_COMMON]
        if read_only:
            pragmas.append("PRAGMA query_only = ON")
        else:
            pragmas.append("PRAGMA synchronous = NORMAL")
        enable_wal = not read_only
        wal_wait_s = max(self.busy_timeout_ms / 1000, 1.0) * 2

        @event.listens_for(engine, "connect")
        def _on_connect(dbapi_conn: sqlite3.Connection, _record: Any) -> None:
            cursor = dbapi_conn.cursor()
            for pragma in pragmas:  # busy_timeout comes first in the list
                cursor.execute(pragma)
            if enable_wal:
                _ensure_wal(cursor, wal_wait_s)
            cursor.close()

        @event.listens_for(engine, "begin")
        def _on_begin(conn: Connection) -> None:
            mode = conn.get_execution_options().get(BEGIN_OPTION, DEFERRED)
            conn.exec_driver_sql(f"BEGIN {mode}")

        return engine

    # -- transactions ----------------------------------------------------------------------

    @contextmanager
    def read_tx(self) -> Iterator[Connection]:
        """A consistent snapshot. The connection is query_only; the transaction is rolled back."""
        conn = self.read_engine.connect().execution_options(**{BEGIN_OPTION: DEFERRED})
        try:
            conn.begin()
            yield conn
        finally:
            try:
                if conn.in_transaction():
                    conn.rollback()
            finally:
                conn.close()

    @contextmanager
    def write_tx(self) -> Iterator[Connection]:
        """`BEGIN IMMEDIATE` ... `COMMIT`. Only acquiring the lock is retried on SQLITE_BUSY."""
        conn = self._begin_immediate()
        try:
            yield conn
            conn.commit()
        except BaseException:
            if conn.in_transaction():
                conn.rollback()
            raise
        finally:
            conn.close()

    def _begin_immediate(self) -> Connection:
        attempt = 0
        while True:
            conn = self.write_engine.connect().execution_options(**{BEGIN_OPTION: IMMEDIATE})
            try:
                conn.begin()
                return conn
            except OperationalError as exc:
                conn.close()
                if not is_busy_error(exc) or attempt >= self.begin_retries:
                    raise
                self._note_busy(attempt)
                attempt += 1

    def run_write(self, work: Callable[[Connection], T], *, retries: int | None = None) -> T:
        """Run `work` in a write transaction, repeating the whole unit if SQLite reports BUSY.

        `work` must be safe to repeat (it is rolled back before every retry)."""
        limit = self.begin_retries if retries is None else retries
        attempt = 0
        while True:
            try:
                with self.write_tx() as conn:
                    return work(conn)
            except OperationalError as exc:
                if not is_busy_error(exc) or attempt >= limit:
                    raise
                self._note_busy(attempt)
                attempt += 1

    def _note_busy(self, attempt: int) -> None:
        with self._lock:
            self.busy_retries += 1
        log.warning("sqlite busy, retrying", extra={"attempt": attempt + 1})
        time.sleep(min(0.05 * 2**attempt, 1.0) * (0.5 + random.random()))  # noqa: S311

    # -- lifecycle -------------------------------------------------------------------------

    def close(self) -> None:
        try:
            with self.write_engine.connect() as conn:
                conn.exec_driver_sql("PRAGMA optimize")
        except Exception:  # noqa: BLE001 - shutdown must not fail
            log.exception("PRAGMA optimize failed")
        self.read_engine.dispose()
        self.write_engine.dispose()

    def ping(self) -> bool:
        with self.read_tx() as conn:
            return conn.exec_driver_sql("SELECT 1").scalar() == 1
