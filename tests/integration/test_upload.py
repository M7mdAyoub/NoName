"""M1 end to end: POST /upload with every supported type -> IR with tables and text."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.connection import Database
from app.main import create_app

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SAMPLES = [f"sample_logframe.{s}" for s in ("xlsx", "csv", "docx", "pdf")]


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, db)) as test_client:
        yield test_client


def _files(*names: str) -> list[tuple[str, tuple[str, bytes]]]:
    return [("files", (name, (FIXTURES / name).read_bytes())) for name in names]


def test_upload_parses_every_supported_type(client: TestClient, settings: Settings) -> None:
    response = client.post("/upload", files=_files(*SAMPLES))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "parsed" and body["error"] is None
    assert [f["filename"] for f in body["files"]] == SAMPLES
    irs = body["ir"]["files"]
    assert [ir["source"]["type"] for ir in irs] == ["xlsx", "csv", "docx", "pdf"]
    for ir in irs:
        assert ir["stats"]["tables"] >= 1
    assert any(b["kind"] in ("heading", "paragraph") for ir in irs for b in ir["blocks"])
    stored = list((settings.files_path / "uploads" / body["id"]).iterdir())
    assert len(stored) == 4

    again = client.get(f"/upload/{body['id']}")
    assert again.status_code == 200 and again.json()["ir"] == body["ir"]
    light = client.get(f"/upload/{body['id']}", params={"ir": False}).json()
    assert "ir" not in light and light["parsed"][0]["stats"]["sheets"] == 2


def test_unsupported_or_empty_uploads_are_rejected(client: TestClient) -> None:
    bad = client.post("/upload", files=[("files", ("deck.pptx", b"x"))])
    assert bad.status_code == 422 and "unsupported" in bad.json()["error"]["message"]
    assert client.post("/upload").status_code == 422


def test_a_broken_file_marks_the_upload_failed(client: TestClient) -> None:
    response = client.post("/upload", files=[("files", ("broken.xlsx", b"not a zip"))])
    assert response.status_code == 201
    assert response.json()["status"] == "failed"
    assert response.json()["error"].startswith("parse failed")


def test_unknown_upload_is_404(client: TestClient) -> None:
    assert client.get("/upload/nope").status_code == 404


def test_file_names_cannot_escape_the_upload_folder(client: TestClient, settings: Settings) -> None:
    content = (FIXTURES / "sample_logframe.csv").read_bytes()
    response = client.post("/upload", files=[("files", ("../../evil.csv", content))])
    folder = settings.files_path / "uploads" / response.json()["id"]
    assert [p.name for p in folder.iterdir()] == ["00_evil.csv"]
