"""Engine calculations against hand-computed values, one small dataset for all five kinds."""

from __future__ import annotations

from typing import Any

import pytest

from app.engine.calc import Record, calculate, matches
from app.schemas.definition import Comparison, Definition
from app.schemas.form import FormSchema, validate_submission

SURVEY = FormSchema.model_validate({
    "title": "Survey",
    "entity_key_field": "person",
    "fields": [
        {"id": "person", "type": "text", "label": "Person", "pii": True},
        {"id": "sex", "type": "select_one", "label": "Sex",
         "options": [{"value": "female", "label": "Female"}, {"value": "male", "label": "Male"}]},
        {"id": "applies", "type": "select_one", "label": "Applies?",
         "options": [{"value": "yes", "label": "Yes"}, {"value": "no", "label": "No"}]},
        {"id": "income", "type": "decimal", "label": "Income"},
        {"id": "crops", "type": "select_multiple", "label": "Crops",
         "options": [{"value": "olive", "label": "Olive"}, {"value": "wheat", "label": "Wheat"},
                     {"value": "tomato", "label": "Tomato"}]},
        {"id": "visit", "type": "date", "label": "Visit"},
    ],
})  # fmt: skip
FORMS = {"survey": SURVEY}

#        person sex       applies income crops               visit
ROWS = [
    ("A", "female", "yes", 100.0, ["olive"], "2026-01-10"),
    ("A", "female", "yes", 300.0, ["olive", "wheat"], "2026-03-01"),  # same person again
    ("B", "female", "no", 200.0, ["tomato"], "2026-02-15"),
    ("C", "male", "yes", 600.0, [], "2026-05-20"),
    ("D", "male", "no", None, ["wheat"], "2026-06-01"),  # income not answered
]
RECORDS = {
    "survey": [
        Record(
            {
                k: v
                for k, v in zip(
                    ("person", "sex", "applies", "income", "crops", "visit"), row, strict=True
                )
                if v not in (None, [])
            },
            row[0],
        )  # fmt: skip
        for row in ROWS
    ]
}


def calc(body: dict[str, Any], records: Any = RECORDS) -> Any:
    return calculate(Definition.model_validate(body), FORMS, records)


def test_count_records_and_distinct_entities() -> None:
    records = calc({"kind": "count", "count": {"form": "survey", "unit": "record"}})
    assert (records.outcome.status, records.outcome.value) == ("ok", 5)
    entities = calc({"kind": "count", "count": {"form": "survey", "unit": "entity"}})
    assert entities.outcome.value == 4  # A, B, C, D
    women = calc({"kind": "count", "count": {"form": "survey", "unit": "entity",
                  "where": {"field": "sex", "op": "eq", "value": "female"}}})  # fmt: skip
    assert women.outcome.value == 2  # A (twice) and B


def test_sum_and_average_skip_unanswered_values() -> None:
    total = calc({"kind": "sum", "value": {"form": "survey", "field": "income"}})
    assert total.outcome.value == 1200  # 100 + 300 + 200 + 600; D did not answer
    assert total.outcome.records == 4
    avg = calc({"kind": "average", "value": {"form": "survey", "field": "income",
                "where": {"field": "sex", "op": "eq", "value": "female"}}})  # fmt: skip
    assert avg.outcome.value == 200  # (100 + 300 + 200) / 3


def test_ratio_of_entities() -> None:
    body = {
        "kind": "ratio",
        "numerator": {"count": {"form": "survey", "unit": "entity", "where": {"all": [
            {"field": "sex", "op": "eq", "value": "female"},
            {"field": "applies", "op": "eq", "value": "yes"}]}}},
        "denominator": {"count": {"form": "survey", "unit": "entity",
                                  "where": {"field": "sex", "op": "eq", "value": "female"}}},
    }  # fmt: skip
    out = calc(body).outcome
    assert out.value == 50  # 1 of 2 women (A) applies the practices
    assert out.components == {"numerator": 1, "denominator": 2}


def test_ratio_of_sums_with_custom_scale() -> None:
    body = {
        "kind": "ratio", "scale": 1,
        "numerator": {"sum": {"form": "survey", "field": "income",
                              "where": {"field": "sex", "op": "eq", "value": "male"}}},
        "denominator": {"sum": {"form": "survey", "field": "income"}},
    }  # fmt: skip
    assert calc(body).outcome.value == 0.5  # 600 / 1200


def test_milestone() -> None:
    reached = {"kind": "milestone", "milestone": {"form": "survey", "achieved_when":
               {"field": "income", "op": "gte", "value": 600}}}  # fmt: skip
    assert calc(reached).outcome.value == 1
    not_reached = {"kind": "milestone", "milestone": {"form": "survey", "achieved_when":
                   {"field": "income", "op": "gt", "value": 600}}}  # fmt: skip
    assert calc(not_reached).outcome.value == 0


def test_breakdowns_by_select_one_field() -> None:
    body = {"kind": "sum", "value": {"form": "survey", "field": "income"},
            "disaggregate_by": ["sex"]}  # fmt: skip
    calculation = calc(body)
    assert calculation.outcome.value == 1200
    [by_sex] = calculation.breakdowns
    assert by_sex.dimension == "sex" and by_sex.label == "Sex"
    assert [(v["value"], v["actual"]) for v in by_sex.values] == [("female", 600), ("male", 600)]
    ratio = calc({
        "kind": "ratio", "disaggregate_by": ["sex"],
        "numerator": {"count": {"form": "survey", "unit": "record",
                                "where": {"field": "applies", "op": "eq", "value": "yes"}}},
        "denominator": {"count": {"form": "survey", "unit": "record"}},
    })  # fmt: skip
    assert ratio.outcome.value == 60  # 3 of 5 records
    female, male = ratio.breakdowns[0].values
    assert female["actual"] == pytest.approx(66.666667)  # 2 of 3
    assert male["actual"] == 50  # 1 of 2


def test_not_computable_cases_never_return_zero() -> None:
    empty: dict[str, list[Record]] = {"survey": []}
    avg = calc({"kind": "average", "value": {"form": "survey", "field": "income"}}, empty)
    assert (avg.outcome.status, avg.outcome.value) == ("not_computable", None)
    assert "no values" in (avg.outcome.reason or "")
    ratio = calc({"kind": "ratio",
                  "numerator": {"count": {"form": "survey", "unit": "record"}},
                  "denominator": {"count": {"form": "survey", "unit": "record"}}}, empty)  # fmt: skip
    assert (
        ratio.outcome.status == "not_computable" and ratio.outcome.reason == "denominator is zero"
    )
    broken = calc({"kind": "sum", "value": {"form": "survey", "field": "missing"}})
    assert broken.outcome.status == "not_computable" and "no field 'missing'" in (
        broken.outcome.reason or ""
    )
    # With no data, a count and a sum are honestly zero
    assert calc({"kind": "count", "count": {"form": "survey"}}, empty).outcome.value == 0
    assert (
        calc({"kind": "sum", "value": {"form": "survey", "field": "income"}}, empty).outcome.value
        == 0
    )


@pytest.mark.parametrize(
    ("cond", "expected"),
    [
        ({"field": "crops", "op": "contains", "value": "olive"}, [True, True, False, False, False]),
        ({"field": "crops", "op": "in", "value": ["wheat", "tomato"]}, [False, True, True, False, True]),
        ({"field": "crops", "op": "is_empty"}, [False, False, False, True, False]),
        ({"field": "income", "op": "neq", "value": 100}, [False, True, True, True, False]),
        ({"field": "sex", "op": "not_in", "value": ["male"]}, [True, True, True, False, False]),
        ({"field": "visit", "op": "lt", "value": "2026-03-01"}, [True, False, True, False, False]),
        ({"any": [{"field": "person", "op": "eq", "value": "B"},
                  {"field": "income", "op": "is_empty"}]}, [False, False, True, False, True]),
    ],
)  # fmt: skip
def test_conditions(cond: dict[str, Any], expected: list[bool]) -> None:
    body = Definition.model_validate(
        {"kind": "milestone", "milestone": {"form": "survey", "achieved_when": cond}}
    )
    assert body.milestone is not None
    assert [matches(body.milestone.achieved_when, r.data) for r in RECORDS["survey"]] == expected
    assert not matches(Comparison(field="income", op="gt", value=0), {})  # missing never matches


def test_submission_validation() -> None:
    clean, errors = validate_submission(
        SURVEY,
        {"person": "A", "sex": "female", "income": 10, "crops": ["olive"], "visit": "2026-01-01"},
    )
    assert errors == [] and clean["income"] == 10
    _, errors = validate_submission(
        SURVEY, {"sex": "other", "income": "ten", "crops": "olive", "visit": "01/02/2026", "x": 1}
    )
    assert errors == [
        "'x': not a field of the form",
        "'sex': must be one of ['female', 'male']",
        "'income': must be a number",
        "'crops': must be a list of option values",
        "'visit': must be a date (YYYY-MM-DD)",
    ]
