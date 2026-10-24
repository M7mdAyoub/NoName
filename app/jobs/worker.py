"""The background worker process: `python -m app.jobs.worker` (plan §17).

One worker process serialises all heavy writes. It claims a job in a short transaction, runs the
handler with no transaction open, and records the outcome in another short transaction.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
from collections.abc import Callable
from typing import Any

from app.config import Settings, get_settings
from app.db.connection import Database
from app.db.migrate import pending
from app.jobs import handlers, queue
from app.logging_setup import configure_logging, request_id_var

log = logging.getLogger("app.worker")


def effective_timeouts() -> dict[str, int]:
    return {**handlers.PLANNED_TIMEOUTS_S, **handlers.timeouts()}


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def sweep_stale(db: Database, *, now: str | None = None) -> dict[str, int]:
    counts = queue.requeue_stale(db, effective_timeouts(), handlers.DEFAULT_TIMEOUT_S, now=now)
    if any(counts.values()):
        log.warning("stale jobs handled", extra={"counts": counts})
    return counts


def run_job(db: Database, job: dict[str, Any]) -> str:
    """Run one claimed job and record the outcome. Returns the resulting status."""
    token = request_id_var.set(f"job-{job['id']}")
    try:
        spec = handlers.get_handler(job["type"])
        if spec is None:
            return queue.fail(
                db, job, f"no handler registered for job type {job['type']!r}", retry=False
            )
        started = time.monotonic()
        try:
            result = spec.func(handlers.JobContext(db, job))
        except queue.LostLock:
            log.warning("job lock lost; abandoning", extra={"job_id": job["id"]})
            return "lost"
        except Exception as exc:  # noqa: BLE001 - any handler error fails the attempt
            log.exception("job failed", extra={"job_id": job["id"], "job_type": job["type"]})
            message = f"{type(exc).__name__}: {exc}"
            return _safe(lambda: queue.fail(db, job, message))
        status = _safe(lambda: _succeed(db, job, result))
        log.info(
            "job finished",
            extra={
                "job_id": job["id"],
                "job_type": job["type"],
                "status": status,
                "seconds": round(time.monotonic() - started, 3),
            },
        )
        return status
    finally:
        request_id_var.reset(token)


def _succeed(db: Database, job: dict[str, Any], result: dict[str, Any] | None) -> str:
    queue.succeed(db, job, result)
    return "succeeded"


def _safe(action: Callable[[], str]) -> str:
    try:
        return str(action())
    except queue.LostLock:
        return "lost"


def run_once(db: Database, wid: str, *, now: str | None = None) -> bool:
    """Claim and run at most one job. Returns True if a job was run."""
    job = queue.claim(db, wid, now=now)
    if job is None:
        return False
    run_job(db, job)
    return True


def run_forever(
    db: Database, settings: Settings, stop: threading.Event, wid: str | None = None
) -> None:
    wid = wid or worker_id()
    log.info("worker started", extra={"worker": wid, "job_types": handlers.registered_types()})
    next_sweep = 0.0
    while not stop.is_set():
        try:
            if time.monotonic() >= next_sweep:
                sweep_stale(db)
                next_sweep = time.monotonic() + settings.job_stale_check_seconds
            busy = run_once(db, wid)
        except Exception:  # noqa: BLE001 - a DB hiccup must not kill the worker
            log.exception("worker loop error")
            busy = False
        if not busy:
            stop.wait(settings.job_poll_seconds)
    log.info("worker stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    db = Database(
        settings.database_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        begin_retries=settings.sqlite_begin_retries,
    )
    if pending(db):
        raise SystemExit("database has pending migrations; run `make migrate` first")
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    try:
        run_forever(db, settings, stop)
    finally:
        db.close()


if __name__ == "__main__":
    main()
