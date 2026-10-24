"""Every route must be project-scoped or explicitly allow-listed (plan §3.4, §20.8).

Skeleton from session 00; enforced from session 01, when `ProjectScope` exists. The rule is
default-deny: a route that neither depends on `get_project_scope` nor appears in the allow-list
fails the check, so a new unscoped route cannot slip in unnoticed.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI  # noqa: E402
from fastapi.routing import APIRoute  # noqa: E402

SCOPE_DEPENDENCY = "get_project_scope"  # defined in session 01 (app/auth/scope.py)

# (HTTP method or "*", exact path). Routes that never touch project data.
UNSCOPED_ALLOWLIST: set[tuple[str, str]] = {
    ("GET", "/healthz"),
    ("GET", "/readyz"),
    ("POST", "/api/v1/dev/jobs"),  # only mounted when APP_ENV is development or test
    ("GET", "/docs"),
    ("GET", "/redoc"),
    ("GET", "/openapi.json"),
    ("GET", "/docs/oauth2-redirect"),
    # MVP (docs/MVP.md): one implicit project, no tenancy
    ("POST", "/upload"),
    ("GET", "/upload/{upload_id}"),
    ("POST", "/upload/{upload_id}/extract"),
    ("GET", "/draft"),
    ("PATCH", "/draft/results/{result_id}"),
    ("PATCH", "/draft/indicators/{indicator_id}"),
    ("PATCH", "/draft/forms/{key}"),
    ("PUT", "/draft/definitions/{indicator_id}"),
    ("PATCH", "/draft/open_questions/{question_id}"),
    ("POST", "/publish"),
    ("GET", "/forms"),
    ("GET", "/forms/{key}"),
    ("POST", "/forms/{key}/submissions"),
    ("GET", "/dashboard"),
}
# Routes that must leave this list in the named session. The check prints a warning for each.
TEMPORARY_ALLOWLIST: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/jobs/{job_id}"): "L-21, session 01",
    ("GET", "/api/v1/jobs/{job_id}/events"): "L-21, session 01",
}


def _depends_on_scope(dependant: Any) -> bool:
    for dep in getattr(dependant, "dependencies", []):
        if getattr(dep.call, "__name__", "") == SCOPE_DEPENDENCY or _depends_on_scope(dep):
            return True
    return False


def iter_api_routes(routes: Iterable[Any]) -> Iterator[Any]:
    """Yield every API route with its full path, including routers added with include_router.

    Recent FastAPI versions keep included routers as lazy wrappers, so look inside them."""
    for route in routes:
        if hasattr(route, "effective_route_contexts"):
            yield from route.effective_route_contexts()
        elif isinstance(route, APIRoute):
            yield route


def find_violations(app: FastAPI) -> tuple[list[str], list[str]]:
    violations: list[str] = []
    warnings: list[str] = []
    seen: set[tuple[str, str]] = set()
    for route in iter_api_routes(app.routes):
        for method in sorted(route.methods or ()):
            key = (method, route.path)
            seen.add(key)
            if key in TEMPORARY_ALLOWLIST:
                warnings.append(f"{method} {route.path} unscoped until {TEMPORARY_ALLOWLIST[key]}")
            elif key in UNSCOPED_ALLOWLIST or _depends_on_scope(route.dependant):
                continue
            else:
                violations.append(
                    f"{method} {route.path} is neither project-scoped nor allow-listed"
                )
    # Self-check: the walk above must have found every route that OpenAPI documents,
    # otherwise a framework change could make this guard silently look at nothing.
    for path, operations in app.openapi().get("paths", {}).items():
        for method in operations:
            if (method.upper(), path) not in seen:
                violations.append(f"guard could not inspect {method.upper()} {path}")
    return violations, warnings


def main() -> int:
    os.environ.setdefault("APP_ENV", "test")
    from app.config import Settings
    from app.main import create_app

    violations, warnings = find_violations(create_app(Settings(app_env="test")))
    for warning in warnings:
        print(f"WARN: {warning}")
    for violation in violations:
        print(f"FAIL: {violation}")
    if not violations:
        print("routes ok")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
