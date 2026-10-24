"""Job type -> handler registry (plan §17). Handlers run outside any DB transaction.

Add a job type::

    @register("my_type", timeout_s=300)
    def my_type(ctx: JobContext) -> dict | None:
        ctx.progress(0.5, "halfway")        # opens its own short write transaction
        return {"done": True}               # stored in job.result

Raise any exception to fail the attempt (it is retried with backoff until max_attempts).
Handlers must be idempotent: a job can run twice if a worker dies after finishing the work.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.db.connection import Database
from app.jobs import queue

DEFAULT_TIMEOUT_S = 300

Handler = Callable[["JobContext"], dict[str, Any] | None]


@dataclass
class JobContext:
    db: Database
    job: dict[str, Any]

    @property
    def payload(self) -> dict[str, Any]:
        return dict(self.job["payload"])

    @property
    def project_id(self) -> str | None:
        value = self.job["project_id"]
        return None if value is None else str(value)

    @property
    def attempts(self) -> int:
        return int(self.job["attempts"])

    def progress(self, fraction: float, note: str | None = None) -> None:
        queue.report_progress(self.db, self.job, fraction, note)


@dataclass(frozen=True)
class HandlerSpec:
    func: Handler
    timeout_s: int


_REGISTRY: dict[str, HandlerSpec] = {}


def register(job_type: str, *, timeout_s: int = DEFAULT_TIMEOUT_S) -> Callable[[Handler], Handler]:
    def decorator(func: Handler) -> Handler:
        if job_type in _REGISTRY:
            raise ValueError(f"job type already registered: {job_type}")
        _REGISTRY[job_type] = HandlerSpec(func, timeout_s)
        return func

    return decorator


def get_handler(job_type: str) -> HandlerSpec | None:
    return _REGISTRY.get(job_type)


def timeouts() -> dict[str, int]:
    return {name: spec.timeout_s for name, spec in _REGISTRY.items()}


def registered_types() -> list[str]:
    return sorted(_REGISTRY)


# --- test jobs (also used by `make dev` smoke runs) ---------------------------------------------


@register("noop", timeout_s=60)
def noop(ctx: JobContext) -> dict[str, Any]:
    return {"ok": True}


@register("sleep", timeout_s=300)
def sleep(ctx: JobContext) -> dict[str, Any]:
    """payload: {"seconds": 2, "steps": 4}. Reports progress after every step."""
    seconds = float(ctx.payload.get("seconds", 1))
    steps = max(int(ctx.payload.get("steps", 4)), 1)
    for step in range(1, steps + 1):
        time.sleep(seconds / steps)
        ctx.progress(step / steps, f"step {step} of {steps}")
    return {"slept": seconds, "steps": steps}


@register("fail", timeout_s=60)
def fail(ctx: JobContext) -> dict[str, Any]:
    """payload: {"until_attempt": 2}. Fails on attempts below the number, then succeeds."""
    until = int(ctx.payload.get("until_attempt", 10**6))
    if ctx.attempts < until:
        raise RuntimeError(f"deliberate failure on attempt {ctx.attempts}")
    return {"succeeded_on_attempt": ctx.attempts}


# Timeouts of job types built in later sessions (plan §17); their handlers register themselves.
PLANNED_TIMEOUTS_S = {
    "parse_document": 5 * 60,
    "extract_framework": 60 * 60,
    "recalculate": 10 * 60,
    "qualitative": 60 * 60,
    "report": 5 * 60,
    "revision_diff": 60 * 60,
}
