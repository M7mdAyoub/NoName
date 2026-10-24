"""`POST /qualitative`: themes in open-text answers (qualitative, non-pii text fields)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbDep, SettingsDep
from app.api.errors import ApiError
from app.services import qualitative as service
from app.services.review import NotFound

router = APIRouter(tags=["qualitative"])


class QualitativeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    form: str | None = None  # limit to one form ...
    field: str | None = None  # ... and/or one field; default: every qualitative field


@router.post("/qualitative")
def qualitative(
    db: DbDep, settings: SettingsDep, body: QualitativeIn | None = None
) -> dict[str, Any]:
    body = body or QualitativeIn()
    try:
        return service.analyse(db, settings, body.form, body.field)
    except NotFound as exc:
        raise ApiError(404, "not_found", str(exc)) from exc
