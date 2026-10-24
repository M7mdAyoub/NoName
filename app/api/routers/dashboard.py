"""`GET /dashboard`: indicators with baseline, target, actual, breakdowns and status/reason."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.api.deps import DbDep
from app.services import dashboard as service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(db: DbDep) -> dict[str, Any]:
    return service.get(db)
