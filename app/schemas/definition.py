"""Indicator definition (MVP version of plan §8): declarative, closed, validated against forms.

Kinds and their blocks::

    count      {"count": {"form", "unit": "entity"|"record", "where"?}}
    sum        {"value": {"form", "field", "where"?}}
    average    {"value": {"form", "field", "where"?}}
    ratio      {"numerator": Measure, "denominator": Measure, "scale": 100}
               Measure = {"count": <count block>} or {"sum": <value block>}
    milestone  {"milestone": {"form", "achieved_when"}}  -> 1 if any matching record exists, else 0

Every kind may add `disaggregate_by` (select_one field ids present in every form it reads).
Conditions: {"all": [...]}, {"any": [...]}, {"field", "op", "value"}.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.form import NUMERIC_TYPES, SELECT_TYPES, FormSchema

Kind = Literal["count", "sum", "average", "ratio", "milestone"]
KINDS: tuple[str, ...] = ("count", "sum", "average", "ratio", "milestone")
Op = Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "not_in", "contains", "is_empty",
             "is_not_empty"]  # fmt: skip
Scalar = str | float | bool
ORDER_OPS = frozenset({"gt", "gte", "lt", "lte"})
LIST_OPS = frozenset({"in", "not_in"})
NO_VALUE_OPS = frozenset({"is_empty", "is_not_empty"})
_STRICT = ConfigDict(extra="forbid")


class Comparison(BaseModel):
    model_config = _STRICT
    field: str
    op: Op
    value: Scalar | list[Scalar] | None = None


class AllOf(BaseModel):
    model_config = _STRICT
    all: list[Condition] = Field(min_length=1)


class AnyOf(BaseModel):
    model_config = _STRICT
    any: list[Condition] = Field(min_length=1)


Condition = Comparison | AllOf | AnyOf


class CountBlock(BaseModel):
    model_config = _STRICT
    form: str
    unit: Literal["entity", "record"] = "record"  # entity = distinct submission.entity_key
    where: Condition | None = None


class ValueBlock(BaseModel):
    model_config = _STRICT
    form: str
    field: str
    where: Condition | None = None


class Measure(BaseModel):
    model_config = _STRICT
    count: CountBlock | None = None
    sum: ValueBlock | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Measure:
        if (self.count is None) == (self.sum is None):
            raise ValueError("a ratio side needs exactly one of 'count' or 'sum'")
        return self


class MilestoneBlock(BaseModel):
    model_config = _STRICT
    form: str
    achieved_when: Condition


class Definition(BaseModel):
    model_config = _STRICT
    schema_version: Literal[1] = 1
    kind: Kind
    count: CountBlock | None = None
    value: ValueBlock | None = None
    numerator: Measure | None = None
    denominator: Measure | None = None
    scale: float | None = None
    milestone: MilestoneBlock | None = None
    disaggregate_by: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _blocks_match_kind(self) -> Definition:
        needed = {
            "count": {"count"},
            "sum": {"value"},
            "average": {"value"},
            "ratio": {"numerator", "denominator"},
            "milestone": {"milestone"},
        }[self.kind]
        blocks = {"count", "value", "numerator", "denominator", "milestone"}
        present = {b for b in blocks if getattr(self, b) is not None}
        if missing := needed - present:
            raise ValueError(f"kind '{self.kind}' needs {sorted(missing)}")
        if extra := present - needed:
            raise ValueError(f"kind '{self.kind}' does not take {sorted(extra)}")
        if self.kind == "ratio" and self.scale is None:
            self.scale = 100
        if self.kind != "ratio" and self.scale is not None:
            raise ValueError("scale is only used by ratio")
        return self


def _sources(defn: Definition) -> Iterator[tuple[str, CountBlock | ValueBlock | MilestoneBlock]]:
    if defn.count:
        yield "count", defn.count
    if defn.value:
        yield "value", defn.value
    if defn.milestone:
        yield "milestone", defn.milestone
    for side in ("numerator", "denominator"):
        measure: Measure | None = getattr(defn, side)
        if measure is not None and measure.count:
            yield f"{side}.count", measure.count
        if measure is not None and measure.sum:
            yield f"{side}.sum", measure.sum


def forms_used(defn: Definition) -> list[str]:
    return sorted({block.form for _, block in _sources(defn)})


def _comparisons(cond: Condition | None) -> Iterator[Comparison]:
    if isinstance(cond, Comparison):
        yield cond
    elif isinstance(cond, AllOf):
        for c in cond.all:
            yield from _comparisons(c)
    elif isinstance(cond, AnyOf):
        for c in cond.any:
            yield from _comparisons(c)


def _check_condition(cond: Condition | None, key: str, form: FormSchema, where: str) -> list[str]:
    errors: list[str] = []
    for c in _comparisons(cond):
        f = form.field(c.field)
        at = f"{where}: condition on '{c.field}'"
        if f is None:
            errors.append(f"{at}: no such field in form '{key}'")
            continue
        if c.op in NO_VALUE_OPS:
            if c.value is not None:
                errors.append(f"{at}: '{c.op}' takes no value")
            continue
        if c.value is None:
            errors.append(f"{at}: '{c.op}' needs a value")
            continue
        if c.op in LIST_OPS and not isinstance(c.value, list):
            errors.append(f"{at}: '{c.op}' needs a list value")
        if c.op not in LIST_OPS and isinstance(c.value, list):
            errors.append(f"{at}: '{c.op}' needs a single value")
        if c.op in ORDER_OPS and f.type not in NUMERIC_TYPES | {"date"}:
            errors.append(f"{at}: '{c.op}' only works on numeric or date fields")
        if c.op == "contains" and f.type != "select_multiple":
            errors.append(f"{at}: 'contains' only works on select_multiple fields")
        if f.type in SELECT_TYPES:
            allowed = {o.value for o in f.options}
            values = c.value if isinstance(c.value, list) else [c.value]
            bad = [v for v in values if str(v) not in allowed]
            if bad:
                errors.append(f"{at}: {bad} not among the options {sorted(allowed)}")
    return errors


def validate_definition(defn: Definition, forms: Mapping[str, FormSchema]) -> list[str]:
    """Problems of a definition against the given forms (by key); empty means it can be computed."""
    errors: list[str] = []
    for path, block in _sources(defn):
        form = forms.get(block.form)
        if form is None:
            errors.append(f"{path}: form '{block.form}' does not exist")
            continue
        if isinstance(block, CountBlock):
            if block.unit == "entity" and not form.entity_key_field:
                errors.append(
                    f"{path}: unit 'entity' needs form '{block.form}' to have an entity_key_field"
                )
            errors += _check_condition(block.where, block.form, form, path)
        elif isinstance(block, ValueBlock):
            f = form.field(block.field)
            if f is None:
                errors.append(f"{path}: no field '{block.field}' in form '{block.form}'")
            elif f.type not in NUMERIC_TYPES:
                errors.append(f"{path}: field '{block.field}' is {f.type}, not numeric")
            errors += _check_condition(block.where, block.form, form, path)
        else:
            errors += _check_condition(block.achieved_when, block.form, form, path)
    if defn.scale is not None and defn.scale <= 0:
        errors.append("scale must be positive")
    for dim in defn.disaggregate_by:
        for key in forms_used(defn):
            form = forms.get(key)
            if form is None:
                continue
            f = form.field(dim)
            if f is None:
                errors.append(f"disaggregate_by '{dim}': not a field of form '{key}'")
            elif f.type != "select_one":
                errors.append(f"disaggregate_by '{dim}': must be a select_one field")
            elif f.pii:
                errors.append(f"disaggregate_by '{dim}': pii fields cannot be used")
    if len(set(defn.disaggregate_by)) != len(defn.disaggregate_by):
        errors.append("disaggregate_by has duplicates")
    return errors
