from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest

from app.db.connection import Database
from app.db.ids import from_iso, to_iso
from app.jobs import handlers, queue, worker

T0 = "2026-10-24T09:00:00.000Z"


def at(seconds: float, base: str = T0) -> str:
    return to_iso(from_iso(base) + timedelta(seconds=seconds))


def job_row(db: Database, job_id: str) -> dict[str, Any]:
    job = queue.get_job(db, job_id)
    assert job is not None
    return job


def test_enqueue_claim_succeed(db: Database) -> None:
    job_id, created = queue.enqueue(db, "noop", {"a": 1}, project_id="p1", now=T0)
    assert created
    assert job_row(db, job_id)["status"] == "queued"
    claimed = queue.claim(db, "w1", now=T0)
    assert claimed is not None and claimed["id"] == job_id
    assert claimed["status"] == "running" and claimed["attempts"] == 1
    assert claimed["locked_by"] == "w1" and claimed["payload"] == {"a": 1}
    assert queue.claim(db, "w2", now=T0) is None  # nothing else to take
    queue.succeed(db, claimed, {"ok": True}, now=at(5))
    done = job_row(db, job_id)
    assert (done["status"], done["progress"], done["result"]) == ("succeeded", 1, {"ok": True})
    assert done["locked_by"] is None and done["finished_at"] == at(5)


def test_claim_respects_run_after_and_order(db: Database) -> None:
    later, _ = queue.enqueue(db, "noop", run_after=at(60), now=T0)
    first, _ = queue.enqueue(db, "noop", run_after=at(1), now=T0)
    assert queue.claim(db, "w", now=T0) is None
    claimed = queue.claim(db, "w", now=at(2))
    assert claimed is not None and claimed["id"] == first
    assert queue.claim(db, "w", now=at(2)) is None
    claimed = queue.claim(db, "w", now=at(61))
    assert claimed is not None and claimed["id"] == later


def test_dedupe_collapses_queued_duplicates_only(db: Database) -> None:
    first, created1 = queue.enqueue(db, "noop", dedupe_key="recalc:p1", now=T0)
    again, created2 = queue.enqueue(db, "noop", dedupe_key="recalc:p1", now=T0)
    assert created1 and not created2 and again == first
    queue.claim(db, "w", now=T0)  # first is now running, so a new one may queue
    third, created3 = queue.enqueue(db, "noop", dedupe_key="recalc:p1", now=T0)
    assert created3 and third != first


def test_failure_requeues_with_exponential_backoff_then_fails(db: Database) -> None:
    job_id, _ = queue.enqueue(db, "noop", max_attempts=3, now=T0)
    now = T0
    expected_delays = [60, 120]  # 30 s x 2^attempts, attempts already incremented
    for attempt, delay in enumerate(expected_delays, start=1):
        job = queue.claim(db, "w", now=now)
        assert job is not None and job["attempts"] == attempt
        assert queue.fail(db, job, "boom", now=now) == "queued"
        row = job_row(db, job_id)
        assert row["run_after"] == at(delay, now)
        assert row["error"] == "boom" and row["locked_by"] is None
        assert queue.claim(db, "w", now=now) is None  # still backing off
        now = row["run_after"]
    last = queue.claim(db, "w", now=now)
    assert last is not None and last["attempts"] == 3
    assert queue.fail(db, last, "boom again", now=now) == "failed"
    final = job_row(db, job_id)
    assert final["status"] == "failed" and final["error"] == "boom again" and final["finished_at"]


def test_retry_that_collides_with_a_queued_duplicate_is_cancelled(db: Database) -> None:
    first, _ = queue.enqueue(db, "noop", dedupe_key="k", now=T0)
    running = queue.claim(db, "w", now=T0)
    assert running is not None
    second, created = queue.enqueue(db, "noop", dedupe_key="k", now=T0)
    assert created and second != first
    assert queue.fail(db, running, "boom", now=T0) == "cancelled"
    old = job_row(db, first)
    assert old["status"] == "cancelled" and old["error"] == "superseded by queued duplicate"
    assert job_row(db, second)["status"] == "queued"


def test_stale_running_job_is_requeued_then_failed_at_max_attempts(db: Database) -> None:
    job_id, _ = queue.enqueue(db, "sleep", max_attempts=2, now=T0)
    queue.claim(db, "dead-worker", now=T0)
    assert queue.requeue_stale(db, {"sleep": 300}, 300, now=at(299)) == {
        "queued": 0,
        "failed": 0,
        "cancelled": 0,
    }
    assert job_row(db, job_id)["status"] == "running"
    assert queue.requeue_stale(db, {"sleep": 300}, 300, now=at(301))["queued"] == 1
    row = job_row(db, job_id)
    assert row["status"] == "queued" and "lock expired" in row["error"]
    queue.claim(db, "w2", now=row["run_after"])
    later = at(301, row["run_after"])
    assert queue.requeue_stale(db, {"sleep": 300}, 300, now=later)["failed"] == 1
    assert job_row(db, job_id)["status"] == "failed"


def test_old_attempt_cannot_overwrite_a_newer_one(db: Database) -> None:
    job_id, _ = queue.enqueue(db, "noop", now=T0)
    old = queue.claim(db, "w1", now=T0)
    assert old is not None
    queue.requeue_stale(db, {"noop": 10}, 10, now=at(11))  # w1 presumed dead
    new = queue.claim(db, "w2", now=job_row(db, job_id)["run_after"])
    assert new is not None and new["attempts"] == 2
    with pytest.raises(queue.LostLock):
        queue.report_progress(db, old, 0.5)
    with pytest.raises(queue.LostLock):
        queue.succeed(db, old, {"stale": True})
    with pytest.raises(queue.LostLock):
        queue.fail(db, old, "late failure")
    queue.report_progress(db, new, 0.5, "half")
    assert job_row(db, job_id)["progress_note"] == "half"
    queue.succeed(db, new, {"fresh": True})
    assert job_row(db, job_id)["result"] == {"fresh": True}


def test_run_once_executes_handler_with_progress(db: Database) -> None:
    job_id, _ = queue.enqueue(db, "sleep", {"seconds": 0, "steps": 4})
    assert worker.run_once(db, "w") is True
    row = job_row(db, job_id)
    assert row["status"] == "succeeded" and row["progress"] == 1
    assert row["result"] == {"slept": 0.0, "steps": 4}
    assert row["progress_note"] == "step 4 of 4"
    assert worker.run_once(db, "w") is False


def test_failing_handler_is_retried_and_eventually_succeeds(db: Database) -> None:
    job_id, _ = queue.enqueue(db, "fail", {"until_attempt": 2}, max_attempts=3, now=T0)
    assert worker.run_once(db, "w", now=T0) is True
    assert job_row(db, job_id)["status"] == "queued"
    assert "RuntimeError: deliberate failure" in job_row(db, job_id)["error"]
    assert worker.run_once(db, "w", now=T0) is False  # backing off
    assert worker.run_once(db, "w", now=job_row(db, job_id)["run_after"]) is True
    final = job_row(db, job_id)
    assert final["status"] == "succeeded" and final["result"] == {"succeeded_on_attempt": 2}


def test_unknown_job_type_fails_without_retrying(db: Database) -> None:
    job_id, _ = queue.enqueue(db, "does_not_exist", max_attempts=5)
    worker.run_once(db, "w")
    row = job_row(db, job_id)
    assert row["status"] == "failed" and "no handler registered" in row["error"]
    assert row["attempts"] == 1


def test_sweep_uses_registered_and_planned_timeouts() -> None:
    timeouts = worker.effective_timeouts()
    assert timeouts["extract_framework"] == 3600
    assert timeouts["parse_document"] == 300
    assert timeouts["noop"] == 60
    assert {"noop", "sleep", "fail"} <= set(handlers.registered_types())


def test_registering_the_same_type_twice_is_an_error() -> None:
    with pytest.raises(ValueError, match="already registered"):
        handlers.register("noop")(lambda ctx: None)
