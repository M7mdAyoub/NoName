"""Review and publish the AI draft (docs/MVP.md API: `PATCH` edits and `POST /publish`)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import DbDep
from app.api.errors import ApiError
from app.services import draft
from app.services import review as service

router = APIRouter(tags=["review"])


class ResultEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    level_name: str | None = None
    code: str | None = None
    statement: str | None = None


class IndicatorEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_id: str | None = None
    code: str | None = None
    name: str | None = None
    unit: str | None = None
    kind: str | None = None
    baseline: float | None = None
    target: float | None = None
    frequency: str | None = None
    data_source: str | None = None


class FormEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = None
    form_schema: dict[str, Any] | None = Field(default=None, alias="schema")  # the whole schema


class DefinitionPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: dict[str, Any]


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str | None


def _call[T](fn: Callable[[], T]) -> T:
    """Map service errors to the API error shape."""
    try:
        return fn()
    except service.NotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
    except service.Conflict as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    except service.Invalid as exc:
        raise ApiError(422, "validation_failed", str(exc), exc.details) from exc


def _set(body: BaseModel) -> dict[str, Any]:
    """Only the fields the client sent, so `null` can clear a value and absent leaves it alone."""
    return {k: getattr(body, k) for k in body.model_fields_set}


@router.patch("/draft/results/{result_id}")
def edit_result(result_id: str, body: ResultEdit, db: DbDep) -> dict[str, Any]:
    _call(lambda: service.update_result(db, result_id, _set(body)))
    return next(r for r in draft.get(db)["results"] if r["id"] == result_id)


@router.patch("/draft/indicators/{indicator_id}")
def edit_indicator(indicator_id: str, body: IndicatorEdit, db: DbDep) -> dict[str, Any]:
    _call(lambda: service.update_indicator(db, indicator_id, _set(body)))
    return next(i for i in draft.get(db)["indicators"] if i["id"] == indicator_id)


@router.patch("/draft/forms/{key}")
def edit_form(key: str, body: FormEdit, db: DbDep) -> dict[str, Any]:
    _call(lambda: service.update_form(db, key, body.title, body.form_schema))
    return next(f for f in draft.get(db)["forms"] if f["key"] == key)


@router.put("/draft/definitions/{indicator_id}")
def put_definition(indicator_id: str, body: DefinitionPut, db: DbDep) -> dict[str, Any]:
    _call(lambda: service.put_definition(db, indicator_id, body.definition))
    return next(d for d in draft.get(db)["definitions"] if d["indicator_id"] == indicator_id)


@router.patch("/draft/open_questions/{question_id}")
def answer_question(question_id: str, body: Answer, db: DbDep) -> dict[str, Any]:
    _call(lambda: service.answer_question(db, question_id, body.answer))
    return next(q for q in draft.get(db)["open_questions"] if q["id"] == question_id)


@router.post("/publish")
def publish(db: DbDep) -> dict[str, Any]:
    return _call(lambda: service.publish(db))
