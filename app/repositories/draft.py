"""SQL for the draft framework: results, indicators, forms, definitions and open questions.

Single implicit project (docs/MVP.md): a new extraction replaces the whole draft, as long as
nothing has been published yet.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, text


def has_published(conn: Connection) -> bool:
    row = conn.execute(
        text(
            "SELECT EXISTS (SELECT 1 FROM form WHERE status = 'published') "
            "OR EXISTS (SELECT 1 FROM indicator WHERE status = 'published')"
        )
    ).scalar_one()
    return bool(row)


def clear(conn: Connection) -> None:
    """Remove the current draft (children first, for the foreign keys)."""
    for sql in (
        "DELETE FROM open_question",
        "DELETE FROM indicator_definition",
        "DELETE FROM indicator",
        "UPDATE result SET parent_id = NULL",
        "DELETE FROM result",
        "DELETE FROM form WHERE status = 'draft'",
    ):
        conn.execute(text(sql))


def insert_result(conn: Connection, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO result (id, upload_id, parent_id, level_name, code, statement, sort_order,"
            " created_at) VALUES (:id, :upload_id, :parent_id, :level_name, :code, :statement,"
            " :sort_order, :created_at)"
        ),
        row,
    )


def insert_indicator(conn: Connection, row: dict[str, Any]) -> None:
    conn.execute(
        text(
            "INSERT INTO indicator (id, result_id, code, name, unit, kind, baseline, target,"
            " frequency, data_source, status, created_at) VALUES (:id, :result_id, :code, :name,"
            " :unit, :kind, :baseline, :target, :frequency, :data_source, 'draft', :created_at)"
        ),
        row,
    )


def insert_form(conn: Connection, form_id: str, key: str, title: str, schema: dict[str, Any],
                now: str) -> None:  # fmt: skip
    conn.execute(
        text(
            "INSERT INTO form (id, key, title, schema, status, created_at, updated_at)"
            " VALUES (:id, :key, :title, :schema, 'draft', :now, :now)"
        ),
        {"id": form_id, "key": key, "title": title, "schema": json.dumps(schema), "now": now},
    )


def insert_definition(conn: Connection, def_id: str, indicator_id: str,
                      definition: dict[str, Any], now: str) -> None:  # fmt: skip
    conn.execute(
        text(
            "INSERT INTO indicator_definition (id, indicator_id, definition, status, created_at,"
            " updated_at) VALUES (:id, :indicator_id, :definition, 'draft', :now, :now)"
        ),
        {
            "id": def_id,
            "indicator_id": indicator_id,
            "definition": json.dumps(definition),
            "now": now,
        },  # fmt: skip
    )


def insert_question(conn: Connection, q_id: str, indicator_id: str | None, question: str,
                    now: str) -> None:  # fmt: skip
    conn.execute(
        text(
            "INSERT INTO open_question (id, indicator_id, question, created_at)"
            " VALUES (:id, :indicator_id, :question, :now)"
        ),
        {"id": q_id, "indicator_id": indicator_id, "question": question, "now": now},
    )


def read(conn: Connection) -> dict[str, list[dict[str, Any]]]:
    def rows(sql: str) -> list[dict[str, Any]]:
        return [dict(r) for r in conn.execute(text(sql)).mappings().all()]

    forms = rows("SELECT id, key, title, schema, status FROM form ORDER BY created_at, key")
    for form in forms:
        form["schema"] = json.loads(form["schema"])
    definitions = rows(
        "SELECT id, indicator_id, definition, status FROM indicator_definition ORDER BY created_at"
    )
    for definition in definitions:
        definition["definition"] = json.loads(definition["definition"])
    return {
        "results": rows(
            "SELECT id, parent_id, level_name, code, statement, sort_order FROM result"
            " ORDER BY sort_order"
        ),
        "indicators": rows(
            "SELECT i.id, i.result_id, i.code, i.name, i.unit, i.kind, i.baseline, i.target,"
            " i.frequency, i.data_source, i.status FROM indicator i"
            " LEFT JOIN result r ON r.id = i.result_id ORDER BY r.sort_order, i.created_at, i.id"
        ),
        "forms": forms,
        "definitions": definitions,
        "open_questions": rows(
            "SELECT id, indicator_id, question, answer FROM open_question ORDER BY created_at, id"
        ),
    }
