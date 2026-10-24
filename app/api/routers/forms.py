"""Data collection: `GET /forms`, `GET /forms/{key}` and `POST /forms/{key}/submissions`."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbDep
from app.api.errors import ApiError
from app.services import submissions as service
from app.services.review import Conflict, Invalid, NotFound

router = APIRouter(tags=["forms"])


class SubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: dict[str, Any]  # answers keyed by field id
    collected_at: str | None = None  # ISO date or datetime; defaults to now


@router.get("/forms")
def list_forms(db: DbDep) -> list[dict[str, Any]]:
    return service.list_forms(db)


@router.get("/forms/{key}")
def get_form(key: str, db: DbDep) -> dict[str, Any]:
    try:
        return service.get_form(db, key)
    except NotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc


@router.post("/forms/{key}/submissions", status_code=201)
def submit(key: str, body: SubmissionIn, db: DbDep) -> dict[str, Any]:
    try:
        return service.submit(db, key, body.data, body.collected_at)
    except NotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    except Conflict as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except Invalid as exc:
        raise ApiError(422, "validation_failed", str(exc), exc.details) from exc
