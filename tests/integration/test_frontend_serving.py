"""The built Arabic frontend is served at /app/, `/` sends people to it, and its dev server may
call the API from either local name."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.connection import Database
from app.main import create_app


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, db)) as test_client:
        yield test_client


def _build(dist: Path) -> None:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html lang="ar" dir="rtl"><script src="./assets/app.js"></script></html>',
        encoding="utf-8",
    )
    (dist / "assets" / "app.js").write_text("console.log('qiyas')", encoding="utf-8")


def test_without_a_build_the_demo_page_is_served(client: TestClient) -> None:
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200 and "<title>M&amp;E Platform</title>" in home.text
    missing = client.get("/app/")
    assert missing.status_code == 404 and "npm run build" in missing.text
    assert client.get("/classic").status_code == 200


def test_a_build_is_served_at_app_without_a_restart(client: TestClient, settings: Settings) -> None:
    _build(settings.frontend_dist)
    home = client.get("/", follow_redirects=False)
    assert (home.status_code, home.headers["location"]) == (307, "/app/")
    page = client.get("/app/")
    assert page.status_code == 200 and 'dir="rtl"' in page.text
    asset = client.get("/app/assets/app.js")
    assert asset.status_code == 200 and "qiyas" in asset.text
    assert client.get("/app/assets/nope.js").status_code == 404
    assert "M&amp;E Platform" in client.get("/classic").text  # the English page stays reachable
    assert client.get("/draft").status_code == 200  # the API is not shadowed by the mount


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_the_frontend_dev_server_may_call_the_api(client: TestClient, origin: str) -> None:
    preflight = client.options(
        "/draft", headers={"Origin": origin, "Access-Control-Request-Method": "PATCH"}
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    refused = client.options(
        "/draft", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in refused.headers


def test_an_empty_setting_turns_the_frontend_off(settings: Settings, db: Database) -> None:
    off = settings.model_copy(
        update={"frontend_dist": Settings.model_validate({"frontend_dist": ""}).frontend_dist}
    )
    assert off.frontend_dist is None  # "" must not become Path("."), the repository itself
    with TestClient(create_app(off, db)) as client:
        for path in ("/app/", "/app/CLAUDE.md", "/app/.env.example", "/app/app/config.py"):
            assert client.get(path).status_code == 404, path
        assert "M&amp;E Platform" in client.get("/").text


def test_only_a_build_folder_is_ever_served(tmp_path: Path) -> None:
    from app.api.routers import demo

    assert not demo.servable(demo.ROOT)  # the repository, even if it had an index.html
    assert not demo.servable(demo.ROOT.parent)  # nor any folder that contains it
    assert not demo.servable(tmp_path)  # a folder without index.html
    assert not demo.servable(None)
    _build(tmp_path / "dist")
    assert demo.servable(tmp_path / "dist")


def test_odd_file_names_are_not_found_not_server_errors(
    client: TestClient, settings: Settings
) -> None:
    _build(settings.frontend_dist)
    for path in ("/app/%3C", "/app/a%3Fb", "/app/a%2A", "/app/a%7Cb", "/app/a%22"):
        assert client.get(path).status_code == 404, path  # Windows' os.stat raises OSError
