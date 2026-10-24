"""`GET /dashboard` (indicators with baseline, target, actual, breakdowns and status/reason)
and `GET /export.csv` (the same as a flat table)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbDep
from app.services import dashboard as service
from app.services import export

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def get_dashboard(db: DbDep) -> dict[str, Any]:
    return service.get(db)


@router.get("/export.csv", response_class=Response)
def export_csv(db: DbDep) -> Response:
    return Response(
        export.to_csv(db),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="indicators.csv"'},
    )
