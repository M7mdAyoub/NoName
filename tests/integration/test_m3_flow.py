"""M3 end to end: upload -> review edits -> publish -> submit -> dashboard with hand-computed values."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.connection import Database
from app.main import create_app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, db)) as test_client:
        body = test_client.post(
            "/upload",
            files=[("files", ("f.xlsx", (FIXTURES / "sample_logframe.xlsx").read_bytes()))],
        ).json()
        assert test_client.get(f"/upload/{body['id']}").json()["status"] == "extracted"
        yield test_client


def _indicator(draft: dict[str, Any], name_part: str) -> dict[str, Any]:
    return next(i for i in draft["indicators"] if name_part in i["name"])


def _submit(client: TestClient, key: str, *rows: dict[str, Any]) -> None:
    for row in rows:
        response = client.post(f"/forms/{key}/submissions", json={"data": row})
        assert response.status_code == 201, response.text


def test_review_publish_collect_and_dashboard(client: TestClient) -> None:
    draft = client.get("/draft").json()
    income = _indicator(draft, "household income")

    # -- review: edit a form, a definition, an indicator, a result and answer the question
    survey = next(f for f in draft["forms"] if f["key"] == "household_survey")["schema"]
    survey["fields"].append({"id": "sex", "type": "select_one", "label": "Sex of head",
                             "options": [{"value": "female", "label": "Female"},
                                         {"value": "male", "label": "Male"}]})  # fmt: skip
    edited = client.patch("/draft/forms/household_survey", json={"schema": survey})
    assert edited.status_code == 200 and len(edited.json()["schema"]["fields"]) == 2
    bad_form = client.patch(
        "/draft/forms/household_survey", json={"schema": {"title": "x", "fields": []}}
    )
    assert (
        bad_form.status_code == 422 and "form has no fields" in bad_form.json()["error"]["details"]
    )

    average = {"kind": "average", "disaggregate_by": ["sex"],
               "value": {"form": "household_survey", "field": "monthly_household_income"}}  # fmt: skip
    broken = {**average, "value": {"form": "household_survey", "field": "nope"}}
    saved = client.put(f"/draft/definitions/{income['id']}", json={"definition": broken}).json()
    assert saved["valid"] is False  # a draft may be saved with problems...
    refused = client.post("/publish")
    assert refused.status_code == 422  # ...but not published
    assert refused.json()["error"]["details"][0]["indicator_id"] == income["id"]
    fixed = client.put(f"/draft/definitions/{income['id']}", json={"definition": average})
    assert fixed.json()["valid"] is True

    sessions = _indicator(draft, "training sessions")
    response = client.patch(
        f"/draft/indicators/{sessions['id']}", json={"target": 90, "code": "1.1a"}
    )
    assert (response.json()["target"], response.json()["code"]) == (90, "1.1a")
    assert client.patch("/draft/indicators/missing", json={"name": "x"}).status_code == 404
    result_id = draft["results"][0]["id"]
    assert client.patch(f"/draft/results/{result_id}", json={"code": "IMP"}).json()["code"] == "IMP"
    question = draft["open_questions"][0]
    answered = client.patch(
        f"/draft/open_questions/{question['id']}", json={"answer": "Women trained"}
    )
    assert answered.json()["answer"] == "Women trained"

    # -- nothing can be collected before publishing
    early = client.post("/forms/session_reports/submissions", json={"data": {}})
    assert early.status_code == 409

    published = client.post("/publish").json()
    assert published["published"] and published["forms"] == 7 and published["indicators"] == 7
    assert published["unanswered_questions"] == 0 and published["without_definition"] == []
    assert client.patch("/draft/forms/household_survey", json={"title": "x"}).status_code == 409
    form = client.get("/forms/household_survey").json()
    assert form["status"] == "published" and form["schema"]["fields"][1]["id"] == "sex"

    # -- collect
    invalid = client.post("/forms/household_survey/submissions",
                          json={"data": {"monthly_household_income": -5, "sex": "x"}})  # fmt: skip
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"] == [
        "'monthly_household_income': must be at least 0", "'sex': must be one of ['female', 'male']"
    ]  # fmt: skip
    _submit(client, "household_survey",
            {"monthly_household_income": 300, "sex": "female"},
            {"monthly_household_income": 500, "sex": "male"},
            {"monthly_household_income": 400, "sex": "female"})  # fmt: skip
    _submit(client, "training_attendance_records",
            {"respondent_id": "R1", "sex": "female"}, {"respondent_id": "R1", "sex": "female"},
            {"respondent_id": "R2", "sex": "female"}, {"respondent_id": "R3", "sex": "male"})  # fmt: skip
    _submit(client, "follow_up_survey",
            {"respondent_id": "R1", "sex": "female", "trained_women_applying_new_practices": "yes"},
            {"respondent_id": "R2", "sex": "female", "trained_women_applying_new_practices": "no"},
            {"respondent_id": "R3", "sex": "female", "trained_women_applying_new_practices": "yes"},
            {"respondent_id": "R4", "sex": "male", "trained_women_applying_new_practices": "yes"})  # fmt: skip
    _submit(client, "session_reports", {}, {"notes": "ok"}, {})
    _submit(client, "market_sales_records",
            {"sales_through_cooperative_markets": 1000},
            {"sales_through_cooperative_markets": 2500.5})  # fmt: skip
    _submit(client, "project_reports", {"market_platform_operational": "no"})

    # -- dashboard
    dashboard = client.get("/dashboard").json()
    assert dashboard["published"] is True
    rows = {r["name"]: r for r in dashboard["indicators"]}
    assert len(rows) == 7 and all(r["status"] == "ok" for r in rows.values())

    income_row = rows["Average monthly household income"]
    assert income_row["actual"] == 400  # (300 + 500 + 400) / 3
    assert income_row["progress_pct"] == 100  # baseline 310, target 400
    [by_sex] = income_row["breakdowns"]
    assert [(v["value"], v["actual"]) for v in by_sex["values"]] == [("female", 350), ("male", 500)]
    assert rows["Number of women completing agri-food training"]["actual"] == 2  # R1, R2
    ratio = rows["% of trained women applying new practices"]
    assert ratio["actual"] == pytest.approx(66.666667)  # R1, R3 of R1-R3
    assert ratio["components"] == {"numerator": 2, "denominator": 3}
    assert rows["Number of training sessions held"]["actual"] == 3
    assert rows["Number of training sessions held"]["target"] == 90
    assert rows["Number of start-up kits distributed"]["actual"] == 0
    assert rows["Total sales through cooperative markets"]["actual"] == 3500.5
    assert rows["Market platform operational"]["actual"] == 0
    assert income_row["result"]["code"] == "IMP"

    _submit(client, "project_reports", {"market_platform_operational": "yes"})
    milestone = {r["name"]: r for r in client.get("/dashboard").json()["indicators"]}
    assert milestone["Market platform operational"]["actual"] == 1
    # A published indicator only accepts a valid definition
    bad = client.put(f"/draft/definitions/{income['id']}", json={"definition": broken})
    assert bad.status_code == 422


def test_seed_fills_every_published_form(client: TestClient, db: Database) -> None:
    import seed  # scripts/ is on sys.path (tests/conftest.py)

    assert client.get("/dashboard").json() == {
        "published": False, "results": client.get("/draft").json()["results"],
        "summary": {"total": 0, "achieved": 0, "in_progress": 0, "not_started": 0,
                    "no_target": 0, "not_computable": 0},
        "indicators": [], "submissions": {},
    }  # fmt: skip
    assert seed.seed(db, per_form=0) == {}  # nothing published yet
    client.post("/publish").raise_for_status()
    added = seed.seed(db, per_form=20, seed_value=3)
    assert len(added) == 7 and set(added.values()) == {20}
    assert all(f["submissions"] == 20 for f in client.get("/forms").json())
    rows = client.get("/dashboard").json()["indicators"]
    assert all(r["status"] == "ok" and r["actual"] is not None for r in rows), rows
    sessions = next(r for r in rows if r["name"] == "Number of training sessions held")
    assert sessions["actual"] == 20
