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


# -- review edits (M3) ----------------------------------------------------------------------

RESULT_FIELDS = ("level_name", "code", "statement")
INDICATOR_FIELDS = ("result_id", "code", "name", "unit", "kind", "baseline", "target", "frequency",
                    "data_source")  # fmt: skip


def _update(conn: Connection, table: str, columns: tuple[str, ...], row_id: str,
            changes: dict[str, Any]) -> bool:  # fmt: skip
    """UPDATE only the given columns; the names come from the fixed tuples above, never from input."""
    sets = [c for c in columns if c in changes]
    assignments = ", ".join(f"{c} = :{c}" for c in sets) or "id = id"  # no changes: existence check
    sql = f"UPDATE {table} SET {assignments} WHERE id = :id"  # noqa: S608
    return conn.execute(text(sql), {**{c: changes[c] for c in sets}, "id": row_id}).rowcount > 0


def update_result(conn: Connection, result_id: str, changes: dict[str, Any]) -> bool:
    return _update(conn, "result", RESULT_FIELDS, result_id, changes)


def update_indicator(conn: Connection, indicator_id: str, changes: dict[str, Any]) -> bool:
    return _update(conn, "indicator", INDICATOR_FIELDS, indicator_id, changes)


def get_form(conn: Connection, key: str) -> dict[str, Any] | None:
    row = (
        conn.execute(
            text("SELECT id, key, title, schema, status FROM form WHERE key = :key"), {"key": key}
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    form = dict(row)
    form["schema"] = json.loads(form["schema"])
    return form


def update_form(conn: Connection, key: str, title: str, schema: dict[str, Any], now: str) -> None:
    conn.execute(
        text(
            "UPDATE form SET title = :title, schema = :schema, updated_at = :now WHERE key = :key"
        ),
        {"key": key, "title": title, "schema": json.dumps(schema), "now": now},
    )


def indicator_exists(conn: Connection, indicator_id: str) -> bool:
    row = conn.execute(text("SELECT 1 FROM indicator WHERE id = :id"), {"id": indicator_id}).first()
    return row is not None


def upsert_definition(conn: Connection, def_id: str, indicator_id: str,
                      definition: dict[str, Any], status: str, now: str) -> None:  # fmt: skip
    conn.execute(
        text(
            "INSERT INTO indicator_definition (id, indicator_id, definition, status, created_at,"
            " updated_at) VALUES (:id, :indicator_id, :definition, :status, :now, :now)"
            " ON CONFLICT (indicator_id) DO UPDATE SET definition = excluded.definition,"
            " status = excluded.status, updated_at = excluded.updated_at"
        ),
        {
            "id": def_id,
            "indicator_id": indicator_id,
            "definition": json.dumps(definition),
            "status": status,
            "now": now,
        },  # fmt: skip
    )


def answer_question(conn: Connection, question_id: str, answer: str | None) -> bool:
    result = conn.execute(
        text("UPDATE open_question SET answer = :answer WHERE id = :id"),
        {"id": question_id, "answer": answer},
    )
    return result.rowcount > 0


def publish(conn: Connection, now: str) -> None:
    conn.execute(text("UPDATE form SET status = 'published', updated_at = :now"
                      " WHERE status = 'draft'"), {"now": now})  # fmt: skip
    conn.execute(text("UPDATE indicator SET status = 'published' WHERE status = 'draft'"))
    conn.execute(text("UPDATE indicator_definition SET status = 'approved', updated_at = :now"
                      " WHERE status = 'draft'"), {"now": now})  # fmt: skip
