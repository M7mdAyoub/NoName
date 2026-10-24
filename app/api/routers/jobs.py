"""Job status (polling) and progress stream (Server-Sent Events). Plan §17, §18.

NOTE: unauthenticated in phase 00 because no users exist yet (L-21 fixes this in session 01).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import DbDep, SettingsDep
from app.config import DEV_ENVS
from app.db.connection import Database
from app.jobs import queue
from app.repositories.jobs import TERMINAL

router = APIRouter(prefix="/jobs", tags=["jobs"])
dev_router = APIRouter(prefix="/dev", tags=["dev"])

POLL_SECONDS = 0.5
HEARTBEAT_EVERY = 20  # polls (= 10 s)
PUBLIC_FIELDS = (
    "id",
    "project_id",
    "type",
    "status",
    "progress",
    "progress_note",
    "result",
    "attempts",
    "max_attempts",
    "error",
    "created_at",
    "finished_at",
)


def public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: job[key] for key in PUBLIC_FIELDS}


@router.get("/{job_id}")
def get_job(job_id: str, db: DbDep) -> dict[str, Any]:
    job = queue.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return public_job(job)


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _events(db: Database, job_id: str, poll: float) -> AsyncIterator[str]:
    last: tuple[Any, ...] | None = None
    idle = 0
    while True:
        job = await run_in_threadpool(queue.get_job, db, job_id)
        if job is None:
            yield _sse("error", {"message": "job not found"})
            return
        snapshot = (job["status"], job["progress"], job["progress_note"], job["attempts"])
        if snapshot != last:
            last = snapshot
            idle = 0
            yield _sse("progress", public_job(job))
        else:
            idle += 1
            if idle % HEARTBEAT_EVERY == 0:
                yield ": heartbeat\n\n"
        if job["status"] in TERMINAL:
            yield _sse("done", public_job(job))
            return
        await asyncio.sleep(poll)


@router.get("/{job_id}/events")
async def job_events(job_id: str, db: DbDep) -> StreamingResponse:
    existing = await run_in_threadpool(queue.get_job, db, job_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="job not found")
    return StreamingResponse(
        _events(db, job_id, POLL_SECONDS),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class DevJobIn(BaseModel):
    type: str = Field(pattern="^(noop|sleep|fail)$")
    payload: dict[str, Any] = Field(default_factory=dict)


@dev_router.post("/jobs", status_code=202)
def enqueue_dev_job(body: DevJobIn, db: DbDep, settings: SettingsDep) -> dict[str, Any]:
    """Enqueue a test job. Only mounted when APP_ENV is development or test."""
    if settings.app_env not in DEV_ENVS:
        raise HTTPException(status_code=404, detail="not found")
    job_id, created = queue.enqueue(db, body.type, body.payload)
    return {"id": job_id, "created": created}
