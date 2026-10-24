"""The LLM steps of the extraction (plan §11.3 C, E, G, H): output models, prompts and checks.

Each check returns a list of problems; the LLM client sends them back to the model and retries.
Checks are deterministic code, so a real model and the mock are held to the same rules.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.definition import KINDS, Definition, Kind, validate_definition
from app.schemas.form import FORM_KEY, FormField, FormSchema, validate_form

PROMPT_VERSION = "mvp-1"
_STRICT = ConfigDict(extra="forbid")

# --- C. map table layout -------------------------------------------------------------------------

Role = Literal["level", "result_code", "result_statement", "indicator", "unit", "baseline",
               "target", "means_of_verification", "frequency", "ignore"]  # fmt: skip
SAMPLE_ROWS = 8


class ColumnRole(BaseModel):
    model_config = _STRICT
    index: int = Field(ge=0)
    role: Role


class TableLayout(BaseModel):
    model_config = _STRICT
    is_framework: bool
    header_row: int = Field(default=0, ge=0)
    columns: list[ColumnRole] = Field(default_factory=list)

    def column(self, role: str) -> int | None:
        return next((c.index for c in self.columns if c.role == role), None)


MAP_LAYOUT = """You read one table from a project document and decide whether it is a results \
framework (logframe): rows of results (impact/outcome/output ...) with their indicators.
You get the first rows of the table. Return:
- is_framework: true only if the table lists indicators.
- header_row: index (0-based) of the row with the column titles.
- columns: the role of each useful column, by 0-based index. Roles: level (Impact/Outcome/Output \
...), result_code (1, 1.1, ...), result_statement, indicator, unit, baseline, target, \
means_of_verification (data source), frequency, ignore. Each role at most once.
Example: header ["Level","Code","Result","Indicator","Baseline","Target"] -> \
{"is_framework": true, "header_row": 0, "columns": [{"index":0,"role":"level"},\
{"index":1,"role":"result_code"},{"index":2,"role":"result_statement"},\
{"index":3,"role":"indicator"},{"index":4,"role":"baseline"},{"index":5,"role":"target"}]}"""


def check_layout(rows: list[list[str]]) -> Callable[[TableLayout], list[str]]:
    width = max((len(r) for r in rows), default=0)

    def check(layout: TableLayout) -> list[str]:
        errors: list[str] = []
        if layout.header_row >= len(rows):
            errors.append(f"header_row must be below {len(rows)}")
        indices = [c.index for c in layout.columns]
        if any(i >= width for i in indices):
            errors.append(f"column indices must be below {width}")
        if len(set(indices)) != len(indices):
            errors.append("each column index may appear once")
        roles = [c.role for c in layout.columns if c.role != "ignore"]
        if len(set(roles)) != len(roles):
            errors.append("each role may appear once")
        if layout.is_framework and "indicator" not in roles:
            errors.append("a framework table needs an 'indicator' column")
        if layout.is_framework and not {"result_statement", "result_code"} & set(roles):
            errors.append("a framework table needs a 'result_statement' or 'result_code' column")
        return errors

    return check


# --- E. normalise indicators ---------------------------------------------------------------------


class NormalizedIndicator(BaseModel):
    model_config = _STRICT
    name: str = Field(min_length=1)
    unit: str | None = None
    kind: Kind | None = None
    baseline: float | None = None
    target: float | None = None
    frequency: str | None = None
    data_source: str | None = None
    open_questions: list[str] = Field(default_factory=list)


NORMALIZE = f"""You clean up one indicator row of a results framework.
Return name (clear, without the unit), unit, kind, baseline and target as numbers, frequency \
and data_source (the means of verification).
kind is one of {", ".join(KINDS)}: count = number of people/things; sum = total of an amount; \
average = mean of a value; ratio = a percentage or share (unit "%"); milestone = done or not \
(baseline 0, target 1).
Rules: never invent a number. If the baseline or target cell is empty or not a number, set it \
to null and add an open question. If you are unsure about the kind, the unit of count (people \
or households?) or the denominator of a percentage, add a short open question. Questions are \
for the project's M&E officer."""


def check_normalized(row: Mapping[str, str]) -> Callable[[NormalizedIndicator], list[str]]:
    def check(ind: NormalizedIndicator) -> list[str]:
        errors: list[str] = []
        for name in ("baseline", "target"):
            if not row.get(name, "").strip() and getattr(ind, name) is not None:
                errors.append(f"{name} is empty in the document: set it to null and ask")
        if ind.kind is None and not ind.open_questions:
            errors.append("kind is null: add an open question about it")
        if ind.kind == "milestone":
            for name in ("baseline", "target"):
                if getattr(ind, name) not in (None, 0, 1):
                    errors.append(f"a milestone {name} is 0 (not done) or 1 (done)")
        return errors

    return check


# --- G. propose forms ----------------------------------------------------------------------------


class ProposedForm(BaseModel):
    model_config = _STRICT
    key: str
    title: str
    data_source: str | None = None
    indicators: list[str] = Field(description="refs of the indicators this form feeds")
    entity_key_field: str | None = None
    fields: list[FormField]

    def form_schema(self) -> FormSchema:
        return FormSchema(title=self.title, entity_key_field=self.entity_key_field,
                          fields=self.fields)  # fmt: skip


class FormsProposal(BaseModel):
    model_config = _STRICT
    forms: list[ProposedForm]


PROPOSE_FORMS = """You design data-collection forms for the indicators of a results framework.
Make one form per data source (means of verification) and list in `indicators` the refs it \
feeds. Each form has a key (lowercase snake_case), a title and typed fields.
Field types: text, integer, decimal, select_one, select_multiple, date. Field ids are \
lowercase snake_case, unique in the form. select fields need at least two options \
({"value","label"}). Numbers that are summed or averaged are integer/decimal with a unit.
If indicators count distinct people or households, add an identifier field (text, required, \
pii: true) and name it in entity_key_field. Add a select_one field for every breakdown an \
indicator needs (for example sex). Mark names, phone numbers and IDs as pii: true.
Only ask what the indicators need; keep forms short."""


def check_forms(refs: list[str]) -> Callable[[FormsProposal], list[str]]:
    def check(proposal: FormsProposal) -> list[str]:
        errors: list[str] = []
        keys = [f.key for f in proposal.forms]
        if len(set(keys)) != len(keys):
            errors.append("form keys must be unique")
        covered: set[str] = set()
        for form in proposal.forms:
            if not FORM_KEY.match(form.key):
                errors.append(f"form '{form.key}': key must match {FORM_KEY.pattern}")
            errors += [f"form '{form.key}': {e}" for e in validate_form(form.form_schema())]
            if unknown := set(form.indicators) - set(refs):
                errors.append(f"form '{form.key}': unknown indicator refs {sorted(unknown)}")
            covered |= set(form.indicators)
        if missing := [r for r in refs if r not in covered]:
            errors.append(f"indicators {missing} are not fed by any form")
        return errors

    return check


# --- H. propose indicator definitions ------------------------------------------------------------

PROPOSE_DEFINITION = """You write the calculation rule of one indicator, using only the forms \
given. A deterministic engine computes it; you never compute numbers.
Shape: {"schema_version": 1, "kind": ..., <block>, "disaggregate_by": [select_one field ids]}.
- count: "count": {"form": key, "unit": "entity" (distinct people/things, needs the form's \
entity_key_field) or "record", "where": condition}
- sum / average: "value": {"form": key, "field": numeric field id, "where": condition}
- ratio: "numerator" and "denominator", each {"count": {...}} or {"sum": {...}}, "scale": 100
- milestone: "milestone": {"form": key, "achieved_when": condition}
Conditions: {"field": id, "op": eq|neq|gt|gte|lt|lte|in|not_in|contains|is_empty|is_not_empty, \
"value": ...}, {"all": [conditions]}, {"any": [conditions]}. Values of select fields are option \
values. Reference only form keys and field ids that exist. Leave out "where" when every record \
counts."""


def check_definition(
    forms: Mapping[str, FormSchema], kind: str | None
) -> Callable[[Definition], list[str]]:
    def check(defn: Definition) -> list[str]:
        errors = validate_definition(defn, forms)
        if kind is not None and defn.kind != kind:
            errors.append(f"the indicator's kind is '{kind}', not '{defn.kind}'")
        return errors

    return check


def form_for_prompt(key: str, form: FormSchema) -> dict[str, Any]:
    """What the model sees of a form: structure only (never submitted data)."""
    return {
        "key": key,
        "title": form.title,
        "entity_key_field": form.entity_key_field,
        "fields": [
            {
                "id": f.id,
                "type": f.type,
                "label": f.label,
                "unit": f.unit,
                "options": [o.value for o in f.options],
            }  # fmt: skip
            for f in form.fields
        ],
    }
