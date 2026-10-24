"""The demo page (`GET /`) and, in development only, `POST /demo/seed` for its seed button."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.api.deps import DbDep
from app.services import seed

PAGE = Path(__file__).resolve().parents[2] / "static" / "index.html"

router = APIRouter(tags=["demo"])
dev_router = APIRouter(tags=["demo"])


@router.get("/", include_in_schema=False)
def page() -> FileResponse:
    return FileResponse(PAGE, media_type="text/html")


@dev_router.post("/demo/seed")
def seed_demo(
    db: DbDep,
    per_form: int = Query(30, ge=1, le=500),
    seed_value: int = Query(7, alias="seed"),
) -> dict[str, Any]:
    return {"added": seed.seed(db, per_form, seed_value)}
