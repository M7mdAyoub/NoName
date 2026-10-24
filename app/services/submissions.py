"""Collect data: list published forms and store submissions validated against their schema."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.connection import Database
from app.db.ids import new_id, to_iso, utc_now
from app.repositories import draft as draft_repo
from app.repositories import submissions as repo
from app.schemas.form import FormSchema, validate_submission
from app.services.review import Conflict, Invalid, NotFound


def list_forms(db: Database) -> list[dict[str, Any]]:
    with db.read_tx() as conn:
        forms = draft_repo.read(conn)["forms"]
        counts = repo.counts(conn)
    return [
        {
            "key": f["key"],
            "title": f["title"],
            "status": f["status"],
            "submissions": counts.get(f["key"], 0),
        }  # fmt: skip
        for f in forms
    ]


def get_form(db: Database, key: str) -> dict[str, Any]:
    with db.read_tx() as conn:
        form = draft_repo.get_form(conn, key)
    if form is None:
        raise NotFound("form not found")
    return form


def _collected_at(value: str | None) -> str:
    """ISO date or datetime -> stored timestamp; defaults to now. No zone means UTC."""
    if value is None:
        return utc_now()
    try:
        moment = datetime.fromisoformat(value)
    except ValueError as exc:
        raise Invalid(
            "invalid collected_at", ["collected_at must be an ISO date or datetime"]
        ) from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return to_iso(moment)


def submit(
    db: Database, key: str, data: dict[str, Any], collected_at: str | None = None
) -> dict[str, Any]:
    form = get_form(db, key)
    if form["status"] != "published":
        raise Conflict("form is not published yet; publish the draft first")
    schema = FormSchema.model_validate(form["schema"])
    clean, errors = validate_submission(schema, data)
    if errors:
        raise Invalid("submission does not match the form", errors)
    key_field = schema.entity_key_field
    entity_key = str(clean[key_field]) if key_field and key_field in clean else None
    row = {"id": new_id(), "form_id": form["id"], "data": clean, "entity_key": entity_key,
           "collected_at": _collected_at(collected_at), "created_at": utc_now()}  # fmt: skip
    with db.write_tx() as conn:
        repo.insert(conn, row)
    return {"id": row["id"], "form": key, "entity_key": entity_key, "collected_at": row["collected_at"],
            "data": clean}  # fmt: skip
