"""Insert-only audit log writer (plan §5.1, decision D-07).

Call it inside the same `db.write_tx()` block as the change it records.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from sqlalchemy import Connection, text

from app.db.connection import BEGIN_OPTION, IMMEDIATE
from app.db.ids import utc_now
from app.logging_setup import get_request_id

PiiMasker = Callable[[str, dict[str, Any]], dict[str, Any]]


def _identity(_table: str, data: dict[str, Any]) -> dict[str, Any]:
    return data


_masker: PiiMasker = _identity


def set_pii_masker(masker: PiiMasker | None) -> None:
    """Install the hook that hides `pii` field values in `before`/`after` (finished in session 03)."""
    global _masker
    _masker = masker or _identity


def mask_pii(table_name: str, data: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if data is None else _masker(table_name, data)


def _dump(table_name: str, data: dict[str, Any] | None) -> str | None:
    masked = mask_pii(table_name, data)
    return (
        None
        if masked is None
        else json.dumps(masked, sort_keys=True, ensure_ascii=False, default=str)
    )


def write_audit(
    conn: Connection,
    *,
    action: str,
    table_name: str,
    row_id: str | None = None,
    user_id: str | None = None,
    project_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> int:
    """Append one audit row and return its id. Refuses to run outside a write transaction."""
    if not conn.in_transaction() or conn.get_execution_options().get(BEGIN_OPTION) != IMMEDIATE:
        raise RuntimeError("write_audit must be called inside db.write_tx()")
    result = conn.execute(
        text(
            "INSERT INTO audit_log (at, user_id, project_id, action, table_name, row_id, before, after, request_id) "
            "VALUES (:at, :user_id, :project_id, :action, :table_name, :row_id, :before, :after, :request_id)"
        ),
        {
            "at": utc_now(),
            "user_id": user_id,
            "project_id": project_id,
            "action": action,
            "table_name": table_name,
            "row_id": row_id,
            "before": _dump(table_name, before),
            "after": _dump(table_name, after),
            "request_id": request_id if request_id is not None else get_request_id(),
        },
    )
    return int(result.lastrowid)
