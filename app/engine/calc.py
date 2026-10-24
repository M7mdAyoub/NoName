"""The deterministic calculation engine (docs/MVP.md): definition + submissions -> one number.

Pure functions, no I/O. Everything is cumulative over all submissions and computed on request.
The engine never guesses: when a value cannot be computed it says so with a reason
(`Outcome.status == "not_computable"`), it never returns a silent zero.

Rules:
- A missing or empty answer only matches `is_empty`; every other comparison on it is false.
- On a select_multiple answer (a list), `eq`/`contains` mean "includes the value", `neq` the
  opposite, `in` means "includes any of", `not_in` "includes none of".
- count/record counts matching submissions; count/entity counts distinct non-empty entity keys.
- sum of no values is 0; average of no values is not computable; a zero denominator is not
  computable; milestone is 1 if any submission matches `achieved_when`, else 0.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from app.schemas.definition import (
    AllOf,
    AnyOf,
    Comparison,
    Condition,
    CountBlock,
    Definition,
    Measure,
    ValueBlock,
    forms_used,
    validate_definition,
)
from app.schemas.form import FormSchema


@dataclass(frozen=True)
class Record:
    """One submission as the engine sees it."""

    data: Mapping[str, Any]
    entity_key: str | None = None


@dataclass
class Outcome:
    status: str  # "ok" | "not_computable"
    value: float | None = None
    reason: str | None = None
    records: int = 0  # submissions that went into the value (after filters)
    components: dict[str, float] = field(default_factory=dict)  # ratio numerator / denominator


class NotComputable(Exception):
    pass


# -- conditions ---------------------------------------------------------------------------


def _empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return str(a).lower() == str(b).lower()
    if isinstance(a, int | float) or isinstance(b, int | float):
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            return False
    return str(a) == str(b)


def _order(a: Any, b: Any) -> tuple[Any, Any] | None:
    """Comparable pair: numbers as floats, anything else (ISO dates) as strings."""
    try:
        return float(a), float(b)
    except (TypeError, ValueError):
        return (a, b) if isinstance(a, str) and isinstance(b, str) else None


def _compare(c: Comparison, data: Mapping[str, Any]) -> bool:
    actual = data.get(c.field)
    if c.op == "is_empty":
        return _empty(actual)
    if c.op == "is_not_empty":
        return not _empty(actual)
    if _empty(actual):
        return False
    wanted = c.value if isinstance(c.value, list) else [c.value]
    if isinstance(actual, list):
        hits = [w for w in wanted if any(_same(a, w) for a in actual)]
        if c.op in ("eq", "contains", "in"):
            return bool(hits)
        if c.op in ("neq", "not_in"):
            return not hits
        return False  # ordering a list makes no sense
    if c.op in ("eq", "contains"):
        return _same(actual, c.value)
    if c.op == "neq":
        return not _same(actual, c.value)
    if c.op == "in":
        return any(_same(actual, w) for w in wanted)
    if c.op == "not_in":
        return not any(_same(actual, w) for w in wanted)
    pair = _order(actual, c.value)
    if pair is None:
        return False
    a, b = pair
    return bool({"gt": a > b, "gte": a >= b, "lt": a < b, "lte": a <= b}[c.op])


def matches(cond: Condition | None, data: Mapping[str, Any]) -> bool:
    if cond is None:
        return True
    if isinstance(cond, AllOf):
        return all(matches(c, data) for c in cond.all)
    if isinstance(cond, AnyOf):
        return any(matches(c, data) for c in cond.any)
    return _compare(cond, data)


# -- measures -----------------------------------------------------------------------------

Records = Mapping[str, Sequence[Record]]  # form key -> its submissions


def _rows(
    records: Records, form: str, where: Condition | None, only: Condition | None
) -> list[Record]:
    return [r for r in records.get(form, ()) if matches(where, r.data) and matches(only, r.data)]


def _count(block: CountBlock, records: Records, only: Condition | None) -> tuple[float, int]:
    rows = _rows(records, block.form, block.where, only)
    if block.unit == "record":
        return float(len(rows)), len(rows)
    return float(len({r.entity_key for r in rows if not _empty(r.entity_key)})), len(rows)


def _values(block: ValueBlock, records: Records, only: Condition | None) -> list[float]:
    values: list[float] = []
    for r in _rows(records, block.form, block.where, only):
        v = r.data.get(block.field)
        if _empty(v):
            continue
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise NotComputable(f"'{block.field}' has a non-numeric answer: {v!r}")
        values.append(float(v))
    return values


def _measure(m: Measure, records: Records, only: Condition | None) -> tuple[float, int]:
    if m.count is not None:
        return _count(m.count, records, only)
    assert m.sum is not None
    values = _values(m.sum, records, only)
    return sum(values), len(values)


def _round(value: float) -> float:
    return round(value, 6)


def _compute(defn: Definition, records: Records, only: Condition | None) -> Outcome:
    try:
        if defn.kind == "count":
            assert defn.count is not None
            value, n = _count(defn.count, records, only)
            return Outcome("ok", value, records=n)
        if defn.kind in ("sum", "average"):
            assert defn.value is not None
            values = _values(defn.value, records, only)
            if defn.kind == "sum":
                return Outcome("ok", _round(sum(values)), records=len(values))
            if not values:
                return Outcome("not_computable", reason="no values to average yet")
            return Outcome("ok", _round(sum(values) / len(values)), records=len(values))
        if defn.kind == "ratio":
            assert defn.numerator is not None and defn.denominator is not None
            num, num_n = _measure(defn.numerator, records, only)
            den, den_n = _measure(defn.denominator, records, only)
            parts = {"numerator": _round(num), "denominator": _round(den)}
            if den == 0:
                return Outcome("not_computable", reason="denominator is zero", records=den_n,
                               components=parts)  # fmt: skip
            scale = defn.scale if defn.scale is not None else 100
            return Outcome("ok", _round(num / den * scale), records=max(num_n, den_n),
                           components=parts)  # fmt: skip
        assert defn.milestone is not None
        rows = _rows(records, defn.milestone.form, defn.milestone.achieved_when, only)
        return Outcome("ok", 1.0 if rows else 0.0, records=len(rows))
    except NotComputable as exc:
        return Outcome("not_computable", reason=str(exc))


@dataclass
class Breakdown:
    dimension: str
    label: str
    values: list[dict[str, Any]]


@dataclass
class Calculation:
    outcome: Outcome
    breakdowns: list[Breakdown] = field(default_factory=list)


def calculate(defn: Definition, forms: Mapping[str, FormSchema], records: Records) -> Calculation:
    """The indicator's actual value plus one breakdown per `disaggregate_by` dimension."""
    errors = validate_definition(defn, forms)
    if errors:
        return Calculation(Outcome("not_computable", reason="; ".join(errors)))
    total = _compute(defn, records, None)
    breakdowns: list[Breakdown] = []
    for dim in defn.disaggregate_by:
        f = forms[forms_used(defn)[0]].field(dim)
        assert f is not None  # validate_definition checked it
        values = []
        for option in f.options:
            part = _compute(defn, records, Comparison(field=dim, op="eq", value=option.value))
            values.append({"value": option.value, "label": option.label, "actual": part.value,
                           "status": part.status, "reason": part.reason,
                           "records": part.records})  # fmt: skip
        breakdowns.append(Breakdown(dim, f.label, values))
    return Calculation(total, breakdowns)
