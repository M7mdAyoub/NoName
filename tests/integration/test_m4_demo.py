"""M4: the demo script end to end, CSV export, qualitative themes and the demo page."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.mock import propose_themes
from app.config import Settings
from app.db.connection import Database
from app.main import create_app
from app.qualitative.themes import ThemesProposal, check_themes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, db)) as test_client:
        yield test_client


def _publish_sample(client: TestClient) -> None:
    client.post(
        "/upload", files=[("files", ("f.xlsx", (FIXTURES / "sample_logframe.xlsx").read_bytes()))]
    ).raise_for_status()
    client.post("/publish").raise_for_status()


def test_demo_script_runs_the_whole_flow(client: TestClient) -> None:
    import demo  # scripts/ is on sys.path (tests/conftest.py)

    lines: list[str] = []
    dashboard = demo.run(client, [demo.SAMPLE], per_form=20, say=lines.append, poll_seconds=0)
    rows = dashboard["indicators"]
    assert len(rows) == 7 and all(r["status"] == "ok" for r in rows), rows
    assert dashboard["submissions"] and set(dashboard["submissions"].values()) == {20}
    # every count/sum/average/ratio indicator is broken down by the added location question
    for row in rows:
        dims = [b["dimension"] for b in row["breakdowns"]]
        assert dims == ([] if row["kind"] == "milestone" else ["location"]), row["name"]
    sessions = next(r for r in rows if r["name"] == "Number of training sessions held")
    by_location = sessions["breakdowns"][0]["values"]
    assert sum(v["actual"] for v in by_location) == sessions["actual"] == 20
    assert any(line.startswith("6. Qualitative") for line in lines)
    assert client.get("/draft").json()["open_questions"][0]["answer"]
    # a second run refuses: the framework is published
    with pytest.raises(demo.DemoError, match="already published"):
        demo.run(client, [demo.SAMPLE], say=lines.append)


def test_export_csv_has_one_row_per_indicator_and_breakdown(client: TestClient) -> None:
    _publish_sample(client)
    for amount in (1000, 2500.5):
        client.post("/forms/market_sales_records/submissions",
                    json={"data": {"sales_through_cooperative_markets": amount}})  # fmt: skip
    for who, sex in (("R1", "female"), ("R1", "female"), ("R2", "male")):
        client.post("/forms/training_attendance_records/submissions",
                    json={"data": {"respondent_id": who, "sex": sex}})  # fmt: skip
    response = client.get("/export.csv")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 7  # the sample's rules have no breakdowns
    sales = next(r for r in rows if r["indicator"] == "Total sales through cooperative markets")
    assert (sales["actual"], sales["baseline"], sales["target"], sales["status"]) == (
        "3500.5", "12000.0", "50000.0", "ok"
    )  # fmt: skip
    women = next(r for r in rows if r["indicator"].startswith("Number of women"))
    assert (women["actual"], women["records"]) == ("1", "2")  # R1's two rows; R2 is male
    kits = next(r for r in rows if r["indicator"].startswith("Number of start-up kits"))
    assert kits["actual"] == "0" and kits["dimension"] == ""
    assert "R1" not in response.text  # aggregates only, never answers

    # with a breakdown, each option gets its own row
    draft = client.get("/draft").json()
    ind = next(i for i in draft["indicators"] if i["name"].startswith("Number of women"))
    defn = next(d for d in draft["definitions"] if d["indicator_id"] == ind["id"])["definition"]
    defn["disaggregate_by"] = ["sex"]
    client.put(f"/draft/definitions/{ind['id']}", json={"definition": defn}).raise_for_status()
    rows = list(csv.DictReader(io.StringIO(client.get("/export.csv").text)))
    split = [(r["dimension_value"], r["actual"]) for r in rows
             if r["indicator"] == ind["name"] and r["dimension"]]  # fmt: skip
    assert split == [("Female", "1"), ("Male", "0")]


def test_qualitative_themes_from_open_text(client: TestClient) -> None:
    assert client.post("/qualitative", json={}).json()["fields"] == []  # nothing published
    _publish_sample(client)
    notes = ["Transport was difficult after the rain.", "Transport costs too high.",
             "Materials arrived late.", "Not enough materials for everyone.",
             "Materials and transport both lacking.", "Fine."]  # fmt: skip
    for note in notes:
        client.post("/forms/session_reports/submissions", json={"data": {"notes": note}})
    client.post("/forms/training_attendance_records/submissions",
                json={"data": {"respondent_id": "Secret Name", "sex": "female"}})  # fmt: skip

    body = client.post("/qualitative", json={"form": "session_reports"}).json()
    [field] = body["fields"]
    assert body["llm"]["mode"] == "mock"
    assert (field["field"], field["answers"], field["analysed"]) == ("notes", 6, 6)
    # greedy mock: 'material' is in 3 answers, then 'transport' in the 2 left; 'Fine.' unthemed
    assert [(t["name"], t["count"], t["share_pct"]) for t in field["themes"]] == [
        ("Material", 3, 50.0), ("Transport", 2, 33.3)
    ]  # fmt: skip
    assert field["unthemed"] == 1
    assert field["themes"][1]["quotes"] == notes[:2]  # verbatim from the data

    everything = client.post("/qualitative").json()
    assert "Secret Name" not in str(everything)  # pii fields are never read
    assert {f["field"] for f in everything["fields"]} == {"notes"}
    missing = client.post("/qualitative", json={"form": "household_survey"})
    assert missing.status_code == 404


def test_theme_checks_reject_unknown_ids_and_duplicates() -> None:
    check = check_themes(3)
    bad = ThemesProposal.model_validate({"themes": [
        {"name": "A", "answers": [0, 5]}, {"name": "a", "answers": [1]}]})  # fmt: skip
    assert check(bad) == ["theme names must be unique", "theme 'A': unknown answer ids [5]"]
    assert check(ThemesProposal()) == []  # no shared theme is a valid answer
    mock = propose_themes({"answers": [{"id": 0, "text": "x"}, {"id": 1, "text": "y"}]})
    assert mock == {"themes": []}  # nothing shared: the mock proposes no theme


def test_demo_page_and_seed_button(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200 and "<title>M&amp;E Platform</title>" in page.text
    assert client.post("/demo/seed").json() == {"added": {}}
    _publish_sample(client)
    added = client.post("/demo/seed", params={"per_form": 5}).json()["added"]
    assert len(added) == 7 and set(added.values()) == {5}
