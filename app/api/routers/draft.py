"""`GET /draft`: the AI-proposed framework awaiting review (docs/MVP.md API)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbDep
from app.services import draft as service

router = APIRouter(tags=["draft"])


@router.get("/draft")
def get_draft(db: DbDep) -> dict[str, Any]:
    return service.get(db)
