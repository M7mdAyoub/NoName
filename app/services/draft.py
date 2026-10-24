"""Read the current draft (docs/MVP.md `GET /draft`), with each definition re-validated."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.db.connection import Database
from app.repositories import draft as repo
from app.schemas.definition import Definition, validate_definition
from app.schemas.form import FormSchema


def get(db: Database) -> dict[str, Any]:
    with db.read_tx() as conn:
        draft = repo.read(conn)
    forms = {f["key"]: FormSchema.model_validate(f["schema"]) for f in draft["forms"]}
    for row in draft["definitions"]:
        try:
            row["errors"] = validate_definition(Definition.model_validate(row["definition"]), forms)
        except ValidationError as exc:
            row["errors"] = [str(e["msg"]) for e in exc.errors()]
        row["valid"] = not row["errors"]
    return draft
