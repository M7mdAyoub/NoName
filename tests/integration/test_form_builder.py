"""Form builder endpoints and the KPI view of the dashboard (forms per KPI, tracking status)."""

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
        name = "sample_logframe_with_forms.xlsx"
        test_client.post(
            "/upload", files=[("files", (name, (FIXTURES / name).read_bytes()))]
        ).raise_for_status()
        yield test_client


def _form(client: TestClient, key: str) -> dict[str, Any]:
    return next(f for f in client.get("/draft").json()["forms"] if f["key"] == key)


def test_build_edit_and_delete_forms(client: TestClient) -> None:
    created = client.post("/draft/forms", json={"title": "Site visit checklist"})
    assert created.status_code == 201
    form = created.json()
    assert (form["key"], form["status"], form["schema"]["origin"]) == (
        "site_visit_checklist", "draft", "manual")  # fmt: skip
    assert [f["id"] for f in form["schema"]["fields"]] == ["question_1"]
    again = client.post("/draft/forms", json={"title": "Site visit checklist"}).json()
    assert again["key"] == "site_visit_checklist_2"
    assert client.post("/draft/forms", json={"title": " "}).status_code == 422

    schema = {**form["schema"], "origin": "document", "source": "made up", "fields": [
        {"id": "visited_on", "type": "date", "label": "Visit date", "required": True},
        {"id": "condition", "type": "select_one", "label": "Condition", "section": "Site",
         "options": [{"value": "good", "label": "Good"}, {"value": "poor", "label": "Poor"}]}]}  # fmt: skip
    edited = client.patch("/draft/forms/site_visit_checklist", json={"schema": schema}).json()
    assert [f["id"] for f in edited["schema"]["fields"]] == ["visited_on", "condition"]
    assert edited["schema"]["origin"] == "manual" and edited["schema"]["source"] is None  # kept
    bad = {**schema, "fields": [{"id": "x", "type": "select_one", "label": "X", "options": []}]}
    refused = client.patch("/draft/forms/site_visit_checklist", json={"schema": bad})
    assert refused.status_code == 422
    assert "field 'x': select_one needs at least two options" in refused.json()["error"]["details"]

    # a form from the document keeps where it came from when edited
    survey = _form(client, "follow_up_survey")
    survey["schema"]["fields"][0]["label"] = "Participant national ID"
    kept = client.patch("/draft/forms/follow_up_survey", json={"schema": survey["schema"]}).json()
    assert kept["schema"]["origin"] == "document" and kept["schema"]["source"].endswith("survey")

    assert client.request("DELETE", "/draft/forms/site_visit_checklist_2").status_code == 204
    in_use = client.request("DELETE", "/draft/forms/follow_up_survey")
    assert in_use.status_code == 409 and "used by the calculation rule" in in_use.text
    assert client.request("DELETE", "/draft/forms/nope").status_code == 404

    # a rule can be dropped: the indicator is then published without one
    draft = client.get("/draft").json()
    sales = next(i for i in draft["indicators"] if i["name"].startswith("Total sales"))
    assert client.request("DELETE", f"/draft/definitions/{sales['id']}").status_code == 204
    published = client.post("/publish").json()
    assert published["without_definition"] == [sales["id"]]
    assert client.request("DELETE", "/draft/forms/site_visit_checklist").status_code == 409
    assert client.request("DELETE", f"/draft/definitions/{sales['id']}").status_code == 409

    # forms built after publishing are published by publishing again
    late = client.post("/draft/forms", json={"title": "Late form"}).json()
    assert late["status"] == "draft"
    client.post("/publish").raise_for_status()
    assert _form(client, "late_form")["status"] == "published"


def _submit(client: TestClient, key: str, *rows: dict[str, Any]) -> None:
    for row in rows:
        client.post(f"/forms/{key}/submissions", json={"data": row}).raise_for_status()


def test_dashboard_tracks_kpis_and_names_their_forms(client: TestClient) -> None:
    client.post("/publish").raise_for_status()
    _submit(client, "follow_up_survey",
            {"respondent_id": "R1", "sex": "female",
             "since_the_training_have_you_applied_the": "yes_sometimes"},
            {"respondent_id": "R2", "sex": "female",
             "since_the_training_have_you_applied_the": "no"})  # fmt: skip
    _submit(client, "market_sales_records", {"sales_through_cooperative_markets": 60000})
    _submit(client, "project_reports", {"market_platform_operational": "no"})
    dashboard = client.get("/dashboard").json()
    rows = {r["name"]: r for r in dashboard["indicators"]}

    ratio = rows["% of trained women applying new practices"]
    assert ratio["forms"] == [{"key": "follow_up_survey", "title": "Follow-up survey",
                               "submissions": 2, "origin": "document"}]  # fmt: skip
    assert (ratio["actual"], ratio["progress_pct"], ratio["track"]) == (50, 83.3, "in_progress")
    sales = rows["Total sales through cooperative markets"]
    assert sales["forms"][0]["origin"] == "ai" and sales["track"] == "achieved"  # 60000 >= 50000
    assert rows["Market platform operational"]["track"] == "not_started"
    assert rows["Number of start-up kits distributed"]["track"] == "not_started"  # 0 so far
    income = rows["Average monthly household income"]
    assert income["track"] == "not_computable" and income["reason"]  # no answers to average
    assert rows["Number of women completing agri-food training"]["forms"][0]["key"] == (
        "training_attendance_records")  # fmt: skip
    assert dashboard["summary"] == {"total": 7, "achieved": 1, "in_progress": 1,
                                    "not_started": 4, "no_target": 0,
                                    "not_computable": 1}  # fmt: skip
