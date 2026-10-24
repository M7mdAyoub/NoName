"""Form and indicator-definition validation (docs/MVP.md: tests for definition validation)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.definition import Definition, forms_used, validate_definition
from app.schemas.form import FormSchema, validate_form

YES_NO = [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]
FORMS = {
    "attendance": FormSchema.model_validate(
        {
            "title": "Attendance",
            "entity_key_field": "person_id",
            "fields": [
                {"id": "person_id", "type": "text", "label": "ID", "pii": True},
                {
                    "id": "sex",
                    "type": "select_one",
                    "label": "Sex",
                    "options": [{"value": "female", "label": "F"}, {"value": "male", "label": "M"}],
                },
                {"id": "completed", "type": "select_one", "label": "Completed?", "options": YES_NO},
                {
                    "id": "topics",
                    "type": "select_multiple",
                    "label": "Topics",
                    "options": [{"value": "a", "label": "A"}, {"value": "b", "label": "B"}],
                },
                {"id": "hours", "type": "decimal", "label": "Hours"},
                {"id": "comment", "type": "text", "label": "Comment"},
            ],
        }
    ),  # fmt: skip
    "sales": FormSchema.model_validate(
        {
            "title": "Sales",
            "fields": [
                {"id": "amount", "type": "decimal", "label": "Amount", "unit": "JOD"},
                {"id": "done", "type": "select_one", "label": "Done?", "options": YES_NO},
            ],
        }
    ),  # fmt: skip
}


def _check(raw: dict[str, Any]) -> list[str]:
    return validate_definition(Definition.model_validate({"schema_version": 1, **raw}), FORMS)


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "count", "count": {"form": "attendance", "unit": "entity",
                                    "where": {"all": [{"field": "sex", "op": "eq", "value": "female"},
                                                      {"field": "completed", "op": "eq", "value": "yes"}]}},
         "disaggregate_by": ["sex"]},
        {"kind": "count", "count": {"form": "sales"}},
        {"kind": "sum", "value": {"form": "sales", "field": "amount",
                                  "where": {"field": "amount", "op": "gt", "value": 0}}},
        {"kind": "average", "value": {"form": "attendance", "field": "hours"}},
        {"kind": "ratio",
         "numerator": {"count": {"form": "attendance", "unit": "entity",
                                 "where": {"field": "topics", "op": "contains", "value": "a"}}},
         "denominator": {"count": {"form": "attendance", "unit": "entity"}}},
        {"kind": "ratio", "numerator": {"sum": {"form": "sales", "field": "amount"}},
         "denominator": {"count": {"form": "sales"}}, "scale": 1},
        {"kind": "milestone", "milestone": {"form": "sales", "achieved_when":
                                            {"any": [{"field": "done", "op": "in", "value": ["yes"]},
                                                     {"field": "amount", "op": "is_not_empty"}]}}},
    ],
)  # fmt: skip
def test_valid_definitions_have_no_errors(raw: dict[str, Any]) -> None:
    assert _check(raw) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ({"kind": "count", "count": {"form": "nope"}}, "form 'nope' does not exist"),
        ({"kind": "count", "count": {"form": "sales", "unit": "entity"}}, "entity_key_field"),
        ({"kind": "sum", "value": {"form": "sales", "field": "missing"}}, "no field 'missing'"),
        ({"kind": "sum", "value": {"form": "attendance", "field": "sex"}}, "not numeric"),
        ({"kind": "count", "count": {"form": "attendance",
                                     "where": {"field": "sex", "op": "eq", "value": "f"}}},
         "not among the options"),
        ({"kind": "count", "count": {"form": "attendance",
                                     "where": {"field": "comment", "op": "gt", "value": 1}}},
         "only works on numeric or date"),
        ({"kind": "count", "count": {"form": "attendance",
                                     "where": {"field": "sex", "op": "contains", "value": "female"}}},
         "only works on select_multiple"),
        ({"kind": "count", "count": {"form": "attendance",
                                     "where": {"field": "sex", "op": "in", "value": "female"}}},
         "needs a list value"),
        ({"kind": "count", "count": {"form": "attendance",
                                     "where": {"field": "sex", "op": "is_empty", "value": "x"}}},
         "takes no value"),
        ({"kind": "count", "count": {"form": "attendance",
                                     "where": {"field": "ghost", "op": "eq", "value": "x"}}},
         "no such field in form 'attendance'"),
        ({"kind": "count", "count": {"form": "attendance"}, "disaggregate_by": ["hours"]},
         "must be a select_one"),
        ({"kind": "count", "count": {"form": "sales"}, "disaggregate_by": ["sex"]},
         "not a field of form 'sales'"),
        ({"kind": "ratio", "numerator": {"count": {"form": "sales"}},
          "denominator": {"count": {"form": "sales"}}, "scale": 0}, "scale must be positive"),
    ],
)  # fmt: skip
def test_invalid_definitions_are_reported(raw: dict[str, Any], expected: str) -> None:
    errors = _check(raw)
    assert any(expected in e for e in errors), errors


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "count"},  # block missing
        {"kind": "sum", "value": {"form": "sales", "field": "amount"},
         "count": {"form": "sales"}},  # extra block
        {"kind": "ratio", "numerator": {"count": {"form": "s"}, "sum": {"form": "s", "field": "x"}},
         "denominator": {"count": {"form": "s"}}},  # two measures on one side
        {"kind": "index", "count": {"form": "sales"}},  # unknown kind
        {"kind": "count", "count": {"form": "sales", "sql": "DROP TABLE x"}},  # closed key set
        {"kind": "count", "count": {"form": "sales", "where": {"field": "a", "op": "like",
                                                               "value": "%"}}},  # unknown op
        {"kind": "count", "count": {"form": "sales"}, "scale": 100},  # scale only for ratio
    ],
)  # fmt: skip
def test_malformed_definitions_do_not_parse(raw: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Definition.model_validate(raw)


def test_ratio_scale_defaults_to_100_and_forms_used_lists_every_source() -> None:
    defn = Definition.model_validate({
        "kind": "ratio", "numerator": {"sum": {"form": "sales", "field": "amount"}},
        "denominator": {"count": {"form": "attendance"}},
    })  # fmt: skip
    assert defn.scale == 100
    assert forms_used(defn) == ["attendance", "sales"]


def test_form_validator() -> None:
    assert [validate_form(f) for f in FORMS.values()] == [[], []]
    bad = FormSchema.model_validate({
        "title": "Bad",
        "entity_key_field": "who",
        "fields": [
            {"id": "Bad-Id", "type": "text", "label": "x"},
            {"id": "dup", "type": "integer", "label": "x"},
            {"id": "dup", "type": "integer", "label": "x"},
            {"id": "one", "type": "select_one", "label": "x", "options": [{"value": "a", "label": "A"}]},
            {"id": "txt", "type": "text", "label": "x", "options": YES_NO},
        ],
    })  # fmt: skip
    errors = " | ".join(validate_form(bad))
    for expected in ("must match", "duplicate id", "at least two options",
                     "only allowed on select", "entity_key_field 'who'"):  # fmt: skip
        assert expected in errors
