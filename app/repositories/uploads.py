"""SQL for `framework_upload`."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text


def create(conn: Connection, upload_id: str, files: list[dict[str, Any]], now: str) -> None:
    conn.execute(
        text(
            "INSERT INTO framework_upload (id, files, status, created_at, updated_at) "
            "VALUES (:id, :files, 'uploaded', :now, :now)"
        ),
        {"id": upload_id, "files": json.dumps(files), "now": now},
    )


def set_status(
    conn: Connection,
    upload_id: str,
    status: str,
    now: str,
    *,
    ir: dict[str, Any] | None = None,
    error: str | None = None,
    extraction: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        text(
            "UPDATE framework_upload SET status = :status, ir = coalesce(:ir, ir), error = :error, "
            "extraction = coalesce(:extraction, extraction), updated_at = :now WHERE id = :id"
        ),
        {
            "id": upload_id,
            "status": status,
            "ir": json.dumps(ir, ensure_ascii=False) if ir is not None else None,
            "error": error,
            "extraction": json.dumps(extraction) if extraction is not None else None,
            "now": now,
        },
    )


def get(conn: Connection, upload_id: str) -> dict[str, Any] | None:
    row = (
        conn.execute(text("SELECT * FROM framework_upload WHERE id = :id"), {"id": upload_id})
        .mappings()
        .first()
    )
    if row is None:
        return None
    data = dict(row)
    data["files"] = json.loads(data["files"])
    data["ir"] = json.loads(data["ir"]) if data["ir"] else None
    data["extraction"] = json.loads(data["extraction"]) if data["extraction"] else None
    return data
