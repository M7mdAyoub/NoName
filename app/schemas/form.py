"""Form schema (MVP version of plan §7): a flat list of typed fields, labels as plain strings.

Stored in `form.schema`. The AI proposes it, a person edits it, M3 validates submissions with it.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FIELD_ID = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
FORM_KEY = FIELD_ID
FieldType = Literal["text", "integer", "decimal", "select_one", "select_multiple", "date"]
NUMERIC_TYPES = frozenset({"integer", "decimal"})
SELECT_TYPES = frozenset({"select_one", "select_multiple"})


class Option(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str
    label: str


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    min: float | None = None
    max: float | None = None


class FormField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: FieldType
    label: str
    required: bool = False
    options: list[Option] = Field(default_factory=list)
    unit: str | None = None
    constraints: Constraints | None = None
    pii: bool = False  # never sent to the LLM, hidden from exports
    qualitative: bool = False  # open text for qualitative analysis


class FormSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    title: str
    # The field whose answer identifies who/what a record is about (copied to submission.entity_key)
    entity_key_field: str | None = None
    fields: list[FormField]

    def field(self, field_id: str) -> FormField | None:
        return next((f for f in self.fields if f.id == field_id), None)


def validate_form(form: FormSchema) -> list[str]:
    """Structural problems of a form schema; an empty list means it is valid."""
    errors: list[str] = []
    if not form.title.strip():
        errors.append("title is empty")
    if not form.fields:
        errors.append("form has no fields")
    seen: set[str] = set()
    for f in form.fields:
        where = f"field '{f.id}'"
        if not FIELD_ID.match(f.id):
            errors.append(f"{where}: id must match {FIELD_ID.pattern}")
        if f.id in seen:
            errors.append(f"{where}: duplicate id")
        seen.add(f.id)
        if not f.label.strip():
            errors.append(f"{where}: label is empty")
        if f.type in SELECT_TYPES:
            values = [o.value for o in f.options]
            if len(values) < 2:
                errors.append(f"{where}: {f.type} needs at least two options")
            if len(set(values)) != len(values):
                errors.append(f"{where}: option values must be unique")
        elif f.options:
            errors.append(f"{where}: options are only allowed on select fields")
        if f.constraints and f.type not in NUMERIC_TYPES:
            errors.append(f"{where}: min/max constraints are only allowed on numeric fields")
    if form.entity_key_field is not None:
        key = form.field(form.entity_key_field)
        if key is None:
            errors.append(f"entity_key_field '{form.entity_key_field}' is not a field of the form")
        elif key.type not in ("text", "integer"):
            errors.append("entity_key_field must be a text or integer field")
    return errors
