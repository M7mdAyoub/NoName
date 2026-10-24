from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db.connection import Database
from app.jobs import worker
from app.main import create_app


@pytest.fixture
def client(settings: Settings, db: Database) -> Iterator[TestClient]:
    with TestClient(create_app(settings, db)) as test_client:
        yield test_client


@pytest.fixture
def running_worker(settings: Settings, db: Database) -> Iterator[None]:
    stop = threading.Event()
    thread = threading.Thread(target=worker.run_forever, args=(db, settings, stop, "test-worker"))
    thread.start()
    yield
    stop.set()
    thread.join(5)


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_readyz_reports_database_migrations_and_llm(client: TestClient) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {
        "database": "ok",
        "migrations": "ok",
        "delete_protection": "ok",
        "llm": "not_configured",
    }


def test_readyz_is_503_when_migrations_are_pending(settings: Settings, empty_db: Database) -> None:
    with TestClient(create_app(settings, empty_db)) as test_client:
        response = test_client.get("/readyz")
    assert response.status_code == 503
    assert response.json()["checks"]["migrations"] == "pending: [1]"


def test_request_id_is_generated_echoed_and_sanitised(client: TestClient) -> None:
    generated = client.get("/healthz").headers["x-request-id"]
    assert len(generated) == 36
    assert (
        client.get("/healthz", headers={"X-Request-ID": "caller-id-0001"}).headers["x-request-id"]
        == "caller-id-0001"
    )
    assert client.get("/healthz", headers={"X-Request-ID": "bad id!"}).headers["x-request-id"] != (
        "bad id!"
    )


def test_errors_use_the_single_error_shape(client: TestClient) -> None:
    missing = client.get("/api/v1/jobs/nope")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {"code": "not_found", "message": "job not found", "details": []}
    }
    invalid = client.post("/api/v1/dev/jobs", json={"type": "unknown"})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_failed"
    assert invalid.json()["error"]["details"][0]["loc"] == ["body", "type"]
    assert "x-request-id" in invalid.headers


def test_unhandled_exception_returns_json_500_with_request_id(
    settings: Settings, db: Database
) -> None:
    app = create_app(settings, db)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internals")

    with TestClient(app, raise_server_exceptions=False) as test_client:
        response = test_client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "secret" not in response.text
    assert response.headers["x-request-id"]


def test_dev_job_route_is_not_mounted_in_production(db: Database, settings: Settings) -> None:
    production = Settings(
        app_env="production",
        secret_key="a" * 32,
        identity_hmac_key="b" * 32,
        database_path=settings.database_path,
    )
    with TestClient(create_app(production, db)) as test_client:
        assert test_client.post("/api/v1/dev/jobs", json={"type": "noop"}).status_code == 404


def test_job_runs_end_to_end_with_progress_and_sse(
    client: TestClient, running_worker: None
) -> None:
    created = client.post(
        "/api/v1/dev/jobs", json={"type": "sleep", "payload": {"seconds": 0.8, "steps": 4}}
    )
    assert created.status_code == 202
    job_id = created.json()["id"]

    events: list[tuple[str, dict]] = []  # type: ignore[type-arg]
    with client.stream("GET", f"/api/v1/jobs/{job_id}/events") as stream:
        assert stream.headers["content-type"].startswith("text/event-stream")
        name = ""
        for line in stream.iter_lines():
            if line.startswith("event: "):
                name = line.removeprefix("event: ")
            elif line.startswith("data: "):
                events.append((name, json.loads(line.removeprefix("data: "))))
                if name == "done":
                    break

    assert events[-1][0] == "done" and events[-1][1]["status"] == "succeeded"
    progress_values = [e[1]["progress"] for e in events if e[0] == "progress"]
    assert progress_values == sorted(progress_values)
    assert any(0 < value < 1 for value in progress_values), progress_values
    final = client.get(f"/api/v1/jobs/{job_id}").json()
    assert final["status"] == "succeeded" and final["progress"] == 1
    assert final["result"] == {"slept": 0.8, "steps": 4}
    assert "payload" not in final and "locked_by" not in final


def test_sse_for_unknown_job_is_404(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/missing/events").status_code == 404


def test_noop_job_polling(client: TestClient, running_worker: None) -> None:
    job_id = client.post("/api/v1/dev/jobs", json={"type": "noop"}).json()["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] == "succeeded":
            break
        time.sleep(0.05)
    assert job["status"] == "succeeded" and job["result"] == {"ok": True}
