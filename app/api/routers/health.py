"""Liveness and readiness probes (mounted at the root, not under /api/v1)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import DbDep, SettingsDep
from app.db import protection
from app.db.migrate import discover, read_ledger

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(db: DbDep, settings: SettingsDep) -> JSONResponse:
    checks: dict[str, Any] = {}
    try:
        with db.read_tx() as conn:
            checks["database"] = "ok" if conn.exec_driver_sql("SELECT 1").scalar() == 1 else "fail"
            applied = read_ledger(conn)
            wanted = {m.version for m in discover()}
            missing = sorted(wanted - set(applied))
            checks["migrations"] = "ok" if not missing else f"pending: {missing}"
            problems = protection.verify_triggers(conn) if not missing else []
            checks["delete_protection"] = problems if problems else "ok"
    except Exception as exc:  # noqa: BLE001 - readiness must report, not raise
        checks["database"] = f"error: {type(exc).__name__}"
    checks["llm"] = "not_checked" if settings.llm_configured else "not_configured"
    ready = (
        checks.get("database") == "ok"
        and checks.get("migrations") == "ok"
        and checks.get("delete_protection") == "ok"
    )
    return JSONResponse(
        {"status": "ready" if ready else "not_ready", "checks": checks},
        status_code=200 if ready else 503,
    )
