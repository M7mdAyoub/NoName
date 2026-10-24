"""SQL for collected data: one row per form submission, answers as JSON keyed by field id."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text


def insert(conn: Connection, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO submission (id, form_id, data, entity_key, collected_at, created_at)"
            " VALUES (:id, :form_id, :data, :entity_key, :collected_at, :created_at)"
        ),
        {**row, "data": json.dumps(row["data"])},
    )


def by_form(conn: Connection) -> dict[str, list[dict[str, Any]]]:
    """Every submission of every published form, grouped by form key."""
    out: dict[str, list[dict[str, Any]]] = {}
    for row in conn.execute(
        text(
            "SELECT f.key, s.data, s.entity_key FROM submission s JOIN form f ON f.id = s.form_id"
            " WHERE f.status = 'published' ORDER BY s.collected_at, s.id"
        )
    ).mappings():
        out.setdefault(row["key"], []).append(
            {"data": json.loads(row["data"]), "entity_key": row["entity_key"]}
        )
    return out


def counts(conn: Connection) -> dict[str, int]:
    rows = conn.execute(
        text(
            "SELECT f.key, count(s.id) FROM form f LEFT JOIN submission s ON s.form_id = f.id"
            " GROUP BY f.key"
        )  # fmt: skip
    ).all()
    return {key: n for key, n in rows}
