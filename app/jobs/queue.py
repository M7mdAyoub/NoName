"""Job queue facade: short transactions around the SQL in app/repositories/jobs.py (plan §17)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.db.connection import Database
from app.db.ids import utc_now
from app.repositories import jobs as repo


class LostLock(Exception):  # noqa: N818 - reads better than LostLockError at call sites
    """The job is no longer owned by this worker attempt (stale re-queue, cancel)."""


def enqueue(
    db: Database,
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    project_id: str | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
    run_after: str | None = None,
    created_by: str | None = None,
    now: str | None = None,
) -> tuple[str, bool]:
    stamp = now or utc_now()
    return db.run_write(
        lambda conn: repo.enqueue(
            conn,
            job_type=job_type,
            payload=payload or {},
            now=stamp,
            project_id=project_id,
            dedupe_key=dedupe_key,
            max_attempts=max_attempts,
            run_after=run_after,
            created_by=created_by,
        )
    )


def get_job(db: Database, job_id: str) -> dict[str, Any] | None:
    with db.read_tx() as conn:
        return repo.get(conn, job_id)


def claim(db: Database, worker_id: str, *, now: str | None = None) -> dict[str, Any] | None:
    stamp = now or utc_now()
    return db.run_write(lambda conn: repo.claim_next(conn, worker_id=worker_id, now=stamp))


def report_progress(
    db: Database, job: Mapping[str, Any], progress: float, note: str | None = None
) -> None:
    value = min(max(progress, 0.0), 1.0)
    ok = db.run_write(
        lambda conn: repo.set_progress(
            conn,
            job_id=job["id"],
            worker_id=job["locked_by"],
            attempts=job["attempts"],
            progress=value,
            note=note,
        )
    )
    if not ok:
        raise LostLock(job["id"])


def succeed(
    db: Database,
    job: Mapping[str, Any],
    result: dict[str, Any] | None = None,
    *,
    now: str | None = None,
) -> None:
    stamp = now or utc_now()
    ok = db.run_write(
        lambda conn: repo.finish_success(
            conn,
            job_id=job["id"],
            worker_id=job["locked_by"],
            attempts=job["attempts"],
            result=result,
            now=stamp,
        )
    )
    if not ok:
        raise LostLock(job["id"])


def fail(
    db: Database, job: Mapping[str, Any], error: str, *, retry: bool = True, now: str | None = None
) -> str:
    """Re-queue with backoff (or mark failed). Returns the job's new status."""
    stamp = now or utc_now()
    status = db.run_write(
        lambda conn: repo.finish_failure(
            conn,
            job_id=job["id"],
            worker_id=job["locked_by"],
            attempts=job["attempts"],
            error=error,
            now=stamp,
            retry=retry,
        )
    )
    if status is None:
        raise LostLock(job["id"])
    return status


def requeue_stale(
    db: Database, timeouts: Mapping[str, int], default_timeout: int, *, now: str | None = None
) -> dict[str, int]:
    stamp = now or utc_now()
    return db.run_write(
        lambda conn: repo.requeue_stale(
            conn, timeouts=timeouts, default_timeout=default_timeout, now=stamp
        )
    )
