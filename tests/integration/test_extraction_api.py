"""M2 end to end: POST /upload -> background extraction (mock LLM) -> draft in the DB -> GET /draft."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.db.connection import Database
from app.main import create_app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, db)) as test_client:
        yield test_client


def _upload(client: TestClient, name: str, content: bytes | None = None) -> dict:  # type: ignore[type-arg]
    data = content if content is not None else (FIXTURES / name).read_bytes()
    response = client.post("/upload", files=[("files", (name, data))])
    assert response.status_code == 201, response.text
    return response.json()


def test_upload_extracts_a_complete_draft(client: TestClient, db: Database) -> None:
    body = _upload(client, "sample_logframe.xlsx")
    assert body["status"] == "extracting"  # the extraction runs as a background task

    upload = client.get(f"/upload/{body['id']}", params={"ir": False}).json()
    assert upload["status"] == "extracted", upload["error"]
    extraction = upload["extraction"]
    assert extraction["mode"] == "mock"
    assert extraction["counts"] == {"results": 6, "indicators": 7, "forms": 7, "definitions": 7,
                                    "invalid_definitions": 0, "open_questions": 1}  # fmt: skip

    draft = client.get("/draft").json()
    assert len(draft["results"]) == 6 and len(draft["indicators"]) == 7
    results = {r["id"]: r for r in draft["results"]}
    roots = [r for r in draft["results"] if r["parent_id"] is None]
    assert [r["level_name"] for r in roots] == ["Impact"]
    assert all(i["result_id"] in results and i["status"] == "draft" for i in draft["indicators"])
    assert {d["indicator_id"] for d in draft["definitions"]} == {
        i["id"] for i in draft["indicators"]
    }
    assert all(d["valid"] and d["status"] == "draft" for d in draft["definitions"])
    assert all(f["status"] == "draft" and f["schema"]["fields"] for f in draft["forms"])
    assert draft["open_questions"][0]["indicator_id"] in {i["id"] for i in draft["indicators"]}
    milestone = next(i for i in draft["indicators"] if i["kind"] == "milestone")
    assert (milestone["baseline"], milestone["target"]) == (0, 1)

    # Running the extraction again replaces the draft instead of adding to it
    again = client.post(f"/upload/{body['id']}/extract")
    assert again.status_code == 202
    assert client.get("/draft").json()["indicators"].__len__() == 7
    with db.read_tx() as conn:
        assert conn.execute(text("SELECT count(*) FROM result")).scalar_one() == 6


def test_extraction_without_a_framework_fails_with_a_reason(client: TestClient) -> None:
    body = _upload(client, "risks.csv", b"Assumption;Risk level\nStable;Low\nFunding;Medium\n")
    upload = client.get(f"/upload/{body['id']}").json()
    assert upload["status"] == "failed"
    assert "no results framework table" in upload["error"]
    assert client.get("/draft").json()["indicators"] == []


def test_extraction_is_refused_once_something_is_published(
    client: TestClient, db: Database
) -> None:
    body = _upload(client, "sample_logframe.csv")
    with db.write_tx() as conn:
        conn.execute(text("UPDATE form SET status = 'published'"))
    response = client.post(f"/upload/{body['id']}/extract")
    assert response.status_code == 409 and "published" in response.json()["error"]["message"]
    assert client.post("/upload/missing/extract").status_code == 404
    skipped = _upload(client, "sample_logframe.docx")
    assert skipped["status"] == "parsed" and "published" in skipped["extraction_skipped"]


def test_upload_can_skip_extraction(client: TestClient) -> None:
    response = client.post(
        "/upload",
        params={"extract": False},
        files=[("files", ("f.csv", (FIXTURES / "sample_logframe.csv").read_bytes()))],
    )
    assert response.json()["status"] == "parsed"
