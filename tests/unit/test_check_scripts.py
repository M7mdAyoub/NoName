from __future__ import annotations

from pathlib import Path

import check_no_hard_delete
import check_routes_scoped
from fastapi import Depends, FastAPI

from app.config import Settings
from app.main import create_app


def test_repo_has_no_forbidden_hard_deletes() -> None:
    assert check_no_hard_delete.scan() == []


def test_hard_delete_scan_flags_non_exempt_tables_only(tmp_path: Path) -> None:
    root = tmp_path / "app"
    root.mkdir()
    (root / "bad.py").write_text(
        'SQL = "DELETE FROM submission WHERE id = 1"\n'
        'OK = "delete from job where id = 1"\n'
        'OK2 = "DELETE FROM membership_component WHERE x = 1"\n'
        "from sqlalchemy import delete\n"
    )
    monkey_root = check_no_hard_delete.ROOT
    check_no_hard_delete.ROOT = tmp_path
    try:
        problems = check_no_hard_delete.scan(root)
    finally:
        check_no_hard_delete.ROOT = monkey_root
    assert len(problems) == 2
    assert "hard DELETE on submission" in problems[0]
    assert "SQLAlchemy delete()" in problems[1]


def test_current_routes_pass_with_only_the_documented_warnings() -> None:
    violations, warnings = check_routes_scoped.find_violations(create_app(Settings(app_env="test")))
    assert violations == []
    assert len(warnings) == 2 and all("L-21" in w for w in warnings)


def test_new_unscoped_route_is_a_violation_and_scoped_route_passes() -> None:
    def get_project_scope() -> str:
        return "scope"

    app = FastAPI()

    @app.get("/projects/{project_id}/things")
    def scoped(scope: str = Depends(get_project_scope)) -> str:
        return scope

    @app.get("/projects/{project_id}/leaky")
    def leaky() -> str:
        return "no scope"

    violations, _ = check_routes_scoped.find_violations(app)
    assert violations == [
        "GET /projects/{project_id}/leaky is neither project-scoped nor allow-listed"
    ]
