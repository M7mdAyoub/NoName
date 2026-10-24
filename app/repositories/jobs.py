"""SQL for the job queue (plan §17, decision D-05). Transactions are managed by app/jobs/queue.py."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import timedelta
from typing import Any

from sqlalchemy import Connection, text

from app.db.ids import from_iso, new_id, to_iso

BACKOFF_BASE_SECONDS = 30
TERMINAL = ("succeeded", "failed", "cancelled")


def _row(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for key in ("payload", "result"):
        if data.get(key) is not None:
            data[key] = json.loads(data[key])
    return data


def enqueue(
    conn: Connection,
    *,
    job_type: str,
    payload: dict[str, Any],
    now: str,
    project_id: str | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 3,
    run_after: str | None = None,
    created_by: str | None = None,
) -> tuple[str, bool]:
    """Insert a queued job. Returns (job_id, created). A queued job with the same dedupe_key wins."""
    job_id = new_id()
    result = conn.execute(
        text(
            "INSERT INTO job (id, project_id, type, status, payload, max_attempts, run_after, "
            "dedupe_key, created_by, created_at) "
            "VALUES (:id, :project_id, :type, 'queued', :payload, :max_attempts, :run_after, "
            ":dedupe_key, :created_by, :now) ON CONFLICT DO NOTHING"
        ),
        {
            "id": job_id,
            "project_id": project_id,
            "type": job_type,
            "payload": json.dumps(payload, sort_keys=True),
            "max_attempts": max_attempts,
            "run_after": run_after or now,
            "dedupe_key": dedupe_key,
            "created_by": created_by,
            "now": now,
        },
    )
    if result.rowcount == 1:
        return job_id, True
    existing = conn.execute(
        text("SELECT id FROM job WHERE dedupe_key = :k AND status = 'queued'"), {"k": dedupe_key}
    ).scalar_one()
    return str(existing), False


def get(conn: Connection, job_id: str) -> dict[str, Any] | None:
    row = conn.execute(text("SELECT * FROM job WHERE id = :id"), {"id": job_id}).mappings().first()
    return _row(row)


def claim_next(conn: Connection, *, worker_id: str, now: str) -> dict[str, Any] | None:
    row = (
        conn.execute(
            text(
                "UPDATE job SET status = 'running', locked_by = :worker, locked_at = :now, "
                "attempts = attempts + 1 "
                "WHERE id = (SELECT id FROM job WHERE status = 'queued' AND run_after <= :now "
                "ORDER BY run_after, id LIMIT 1) RETURNING *"
            ),
            {"worker": worker_id, "now": now},
        )
        .mappings()
        .first()
    )
    return _row(row)


_OWNED = "id = :id AND status = 'running' AND locked_by = :worker AND attempts = :attempts"


def set_progress(
    conn: Connection,
    *,
    job_id: str,
    worker_id: str,
    attempts: int,
    progress: float,
    note: str | None,
) -> bool:
    result = conn.execute(
        text(f"UPDATE job SET progress = :progress, progress_note = :note WHERE {_OWNED}"),
        {
            "id": job_id,
            "worker": worker_id,
            "attempts": attempts,
            "progress": progress,
            "note": note,
        },
    )
    return result.rowcount == 1


def finish_success(
    conn: Connection,
    *,
    job_id: str,
    worker_id: str,
    attempts: int,
    result: dict[str, Any] | None,
    now: str,
) -> bool:
    out = conn.execute(
        text(
            "UPDATE job SET status = 'succeeded', progress = 1, result = :result, finished_at = :now, "
            f"locked_by = NULL, locked_at = NULL, error = NULL WHERE {_OWNED}"
        ),
        {
            "id": job_id,
            "worker": worker_id,
            "attempts": attempts,
            "result": None if result is None else json.dumps(result, sort_keys=True),
            "now": now,
        },
    )
    return out.rowcount == 1


def finish_failure(
    conn: Connection,
    *,
    job_id: str,
    worker_id: str,
    attempts: int,
    error: str,
    now: str,
    retry: bool = True,
) -> str | None:
    """Re-queue with backoff or mark failed. Returns the new status, or None if the lock was lost."""
    job = (
        conn.execute(
            text(f"SELECT * FROM job WHERE {_OWNED}"),
            {"id": job_id, "worker": worker_id, "attempts": attempts},
        )
        .mappings()
        .first()
    )
    if job is None:
        return None
    return _retry_or_fail(conn, dict(job), error=error, now=now, retry=retry)


def _retry_or_fail(
    conn: Connection, job: dict[str, Any], *, error: str, now: str, retry: bool
) -> str:
    job_id = job["id"]
    if not retry or job["attempts"] >= job["max_attempts"]:
        conn.execute(
            text(
                "UPDATE job SET status = 'failed', error = :error, finished_at = :now, "
                "locked_by = NULL, locked_at = NULL WHERE id = :id"
            ),
            {"id": job_id, "error": error[:2000], "now": now},
        )
        return "failed"
    if job["dedupe_key"] is not None:
        clash = conn.execute(
            text("SELECT 1 FROM job WHERE dedupe_key = :k AND status = 'queued' AND id <> :id"),
            {"k": job["dedupe_key"], "id": job_id},
        ).first()
        if clash:
            conn.execute(
                text(
                    "UPDATE job SET status = 'cancelled', error = 'superseded by queued duplicate', "
                    "finished_at = :now, locked_by = NULL, locked_at = NULL WHERE id = :id"
                ),
                {"id": job_id, "now": now},
            )
            return "cancelled"
    delay = timedelta(seconds=BACKOFF_BASE_SECONDS * 2 ** job["attempts"])
    conn.execute(
        text(
            "UPDATE job SET status = 'queued', run_after = :run_after, error = :error, "
            "locked_by = NULL, locked_at = NULL, progress = 0, progress_note = NULL WHERE id = :id"
        ),
        {"id": job_id, "run_after": to_iso(from_iso(now) + delay), "error": error[:2000]},
    )
    return "queued"


def requeue_stale(
    conn: Connection, *, timeouts: Mapping[str, int], default_timeout: int, now: str
) -> dict[str, int]:
    """Handle `running` jobs whose lock is older than their type's timeout."""
    counts = {"queued": 0, "failed": 0, "cancelled": 0}
    running = conn.execute(text("SELECT * FROM job WHERE status = 'running'")).mappings().all()
    current = from_iso(now)
    for job in running:
        timeout = timeouts.get(job["type"], default_timeout)
        locked_at = job["locked_at"]
        if locked_at is not None and current - from_iso(locked_at) <= timedelta(seconds=timeout):
            continue
        status = _retry_or_fail(
            conn,
            dict(job),
            error=f"lock expired after {timeout}s; worker presumed dead",
            now=now,
            retry=True,
        )
        counts[status] += 1
    return counts
