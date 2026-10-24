"""Human review of the AI draft (docs/MVP.md M3): edit, then publish.

Rules:
- Results, indicators, definitions and open-question answers can be edited at any time.
- A form can only be edited while it is a draft; once published, submissions depend on it.
  Forms can be created in the form builder at any time (also after publishing; publish again to
  use them) and deleted while they are drafts that no definition reads.
- A definition only needs to parse to be saved as a draft; its problems show in `GET /draft`.
  Once its indicator is published, a definition must be fully valid to be saved.
- Publish refuses while any form or definition has problems. Indicators without a definition
  are published anyway and show as not computable on the dashboard.
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.db.connection import Database
from app.db.ids import new_id, utc_now
from app.repositories import draft as repo
from app.schemas.definition import KINDS, Definition, forms_used, validate_definition
from app.schemas.form import FormSchema, unique_slug, validate_form


class NotFound(LookupError):
    pass


class Conflict(Exception):
    pass


class Invalid(ValueError):
    def __init__(self, message: str, details: list[Any]) -> None:
        super().__init__(message)
        self.details = details


def _pydantic_errors(exc: ValidationError) -> list[str]:
    return [f"{'.'.join(map(str, e['loc'])) or 'definition'}: {e['msg']}" for e in exc.errors()]


def _forms(conn: Any) -> dict[str, FormSchema]:
    return {f["key"]: FormSchema.model_validate(f["schema"]) for f in repo.read(conn)["forms"]}


def update_result(db: Database, result_id: str, changes: dict[str, Any]) -> None:
    with db.write_tx() as conn:
        if not repo.update_result(conn, result_id, changes):
            raise NotFound("result not found")


def update_indicator(db: Database, indicator_id: str, changes: dict[str, Any]) -> None:
    if changes.get("kind") is not None and changes["kind"] not in KINDS:
        raise Invalid("invalid kind", [f"kind must be one of {list(KINDS)}"])
    with db.write_tx() as conn:
        if "result_id" in changes and changes["result_id"] is not None:
            results = {r["id"] for r in repo.read(conn)["results"]}
            if changes["result_id"] not in results:
                raise Invalid("invalid result_id", ["result_id is not an existing result"])
        if not repo.update_indicator(conn, indicator_id, changes):
            raise NotFound("indicator not found")


def update_form(db: Database, key: str, title: str | None, schema: dict[str, Any] | None) -> None:
    with db.read_tx() as conn:
        current = repo.get_form(conn, key)
    if current is None:
        raise NotFound("form not found")
    if current["status"] == "published":
        raise Conflict("form is published and can no longer be edited")
    new_schema = schema if schema is not None else current["schema"]
    if title is not None:
        new_schema = {**new_schema, "title": title}
    # where the form came from is not the editor's to change
    for kept in ("origin", "source"):
        new_schema = {**new_schema, kept: current["schema"].get(kept)}
    form = _valid_form(new_schema)
    with db.write_tx() as conn:
        repo.update_form(conn, key, form.title, form.model_dump(mode="json"), utc_now())


def _valid_form(schema: dict[str, Any]) -> FormSchema:
    try:
        form = FormSchema.model_validate(schema)
    except ValidationError as exc:
        raise Invalid("form schema is not valid", _pydantic_errors(exc)) from exc
    if errors := validate_form(form):
        raise Invalid("form schema is not valid", errors)
    return form


def create_form(db: Database, title: str, schema: dict[str, Any] | None) -> str:
    """A new draft form (from the form builder); returns its key, made from the title."""
    if not title.strip():
        raise Invalid("form schema is not valid", ["title is empty"])
    schema = schema or {"fields": [{"id": "question_1", "type": "text", "label": "Question 1"}]}
    form = _valid_form(
        {**schema, "title": title.strip(), "origin": schema.get("origin") or "manual"}
    )
    with db.write_tx() as conn:
        key = unique_slug(form.title, repo.form_keys(conn), 30)
        repo.insert_form(conn, new_id(), key, form.title, form.model_dump(mode="json"), utc_now())
    return key


def delete_form(db: Database, key: str) -> None:
    with db.write_tx() as conn:
        draft = repo.read(conn)
        form = next((f for f in draft["forms"] if f["key"] == key), None)
        if form is None:
            raise NotFound("form not found")
        if form["status"] == "published":
            raise Conflict("form is published and can no longer be deleted")
        users = []
        for d in draft["definitions"]:
            try:
                if key in forms_used(Definition.model_validate(d["definition"])):
                    users.append(d["indicator_id"])
            except ValidationError:
                continue
        if users:
            raise Conflict(f"form is used by the calculation rule of {len(users)} indicator(s); "
                           "change those rules first")  # fmt: skip
        repo.delete_form(conn, key)


def delete_definition(db: Database, indicator_id: str) -> None:
    """Drop a draft rule: the indicator is then published without one (not computable)."""
    with db.write_tx() as conn:
        draft = repo.read(conn)
        indicator = next((i for i in draft["indicators"] if i["id"] == indicator_id), None)
        if indicator is None:
            raise NotFound("indicator not found")
        if indicator["status"] == "published":
            raise Conflict("a published indicator keeps its rule; replace it instead")
        repo.delete_definition(conn, indicator_id)


def put_definition(db: Database, indicator_id: str, body: dict[str, Any]) -> list[str]:
    """Save (create or replace) an indicator's definition; returns its remaining problems."""
    try:
        defn = Definition.model_validate(body)
    except ValidationError as exc:
        raise Invalid("definition is not valid", _pydantic_errors(exc)) from exc
    with db.write_tx() as conn:
        draft = repo.read(conn)
        indicator = next((i for i in draft["indicators"] if i["id"] == indicator_id), None)
        if indicator is None:
            raise NotFound("indicator not found")
        errors = validate_definition(defn, _forms(conn))
        published = indicator["status"] == "published"
        if published and errors:
            raise Invalid("a published indicator needs a valid definition", errors)
        status = "approved" if published else "draft"
        dumped = defn.model_dump(mode="json", exclude_none=True)
        repo.upsert_definition(conn, new_id(), indicator_id, dumped, status, utc_now())
        repo.update_indicator(conn, indicator_id, {"kind": defn.kind})  # keep the two in step
    return errors


def answer_question(db: Database, question_id: str, answer: str | None) -> None:
    with db.write_tx() as conn:
        if not repo.answer_question(conn, question_id, answer):
            raise NotFound("open question not found")


def publish(db: Database) -> dict[str, Any]:
    with db.write_tx() as conn:
        draft = repo.read(conn)
        if not draft["indicators"]:
            raise Conflict("there is nothing to publish; upload a framework first")
        problems: list[dict[str, Any]] = []
        forms: dict[str, FormSchema] = {}
        for row in draft["forms"]:
            form = FormSchema.model_validate(row["schema"])
            forms[row["key"]] = form
            if errors := validate_form(form):
                problems.append({"form": row["key"], "errors": errors})
        defined = set()
        for row in draft["definitions"]:
            defined.add(row["indicator_id"])
            try:
                errors = validate_definition(Definition.model_validate(row["definition"]), forms)
            except ValidationError as exc:
                errors = _pydantic_errors(exc)
            if errors:
                problems.append({"indicator_id": row["indicator_id"], "errors": errors})
        if problems:
            raise Invalid("fix these problems before publishing", problems)
        repo.publish(conn, utc_now())
    return {
        "published": True,
        "forms": len(draft["forms"]),
        "indicators": len(draft["indicators"]),
        "definitions": len(draft["definitions"]),
        "without_definition": [i["id"] for i in draft["indicators"] if i["id"] not in defined],
        "unanswered_questions": sum(1 for q in draft["open_questions"] if not q["answer"]),
    }
