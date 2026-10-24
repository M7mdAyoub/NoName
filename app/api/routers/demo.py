"""Pages: the Arabic frontend (`/app/`, built from outputs/impactos-frontend), the English demo
page (`/classic`), `GET /` sending people to whichever exists, and, in development only,
`POST /demo/seed` for the demo page's seed button."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

if TYPE_CHECKING:
    from os import stat_result

from app.api.deps import DbDep
from app.config import Settings
from app.services import seed

ROOT = Path(__file__).resolve().parents[3]
PAGE = Path(__file__).resolve().parents[2] / "static" / "index.html"
FRONTEND_PATH = "/app"

router = APIRouter(tags=["demo"])
dev_router = APIRouter(tags=["demo"])


def frontend_dir(settings: Settings) -> Path | None:
    """The build folder, or None when turned off (FRONTEND_DIST empty)."""
    path = settings.frontend_dist
    if path is None:
        return None
    return path if path.is_absolute() else ROOT / path


def servable(directory: Path | None) -> bool:
    """Only a build folder is served: it must hold index.html and must not be the repository or a
    folder containing it, so a misconfigured FRONTEND_DIST can never expose source, .env or data."""
    if directory is None or not (directory / "index.html").is_file():
        return False
    resolved = directory.resolve()
    return resolved != ROOT and resolved not in ROOT.parents


class FrontendFiles(StaticFiles):
    """The built frontend. The folder is looked for on each request, so building it needs no
    restart; until then /app/ answers 404 with how to build it (StaticFiles would answer 500)."""

    def __init__(self, directory: Path | None) -> None:
        self.folder = directory
        super().__init__(directory=directory or ROOT / "missing", html=True, check_dir=False)

    def lookup_path(self, path: str) -> tuple[str, stat_result | None]:
        # Names Windows refuses (<, >, ?, *, |, ") raise OSError in os.stat: that is "not found",
        # not a server error.
        try:
            return super().lookup_path(path)
        except OSError:
            return "", None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not servable(self.folder):
            hint = PlainTextResponse(
                "The frontend is not built. Run: cd outputs/impactos-frontend && npm install"
                " && npm run build",
                status_code=404,
            )
            await hint(scope, receive, send)
            return
        await super().__call__(scope, receive, send)


def frontend_files(settings: Settings) -> StaticFiles:
    return FrontendFiles(frontend_dir(settings))


@router.get("/", include_in_schema=False)
def home(request: Request) -> Response:
    if servable(frontend_dir(request.app.state.settings)):
        return RedirectResponse(f"{FRONTEND_PATH}/", status_code=307)
    return FileResponse(PAGE, media_type="text/html")


@router.get("/classic", include_in_schema=False)
def classic() -> FileResponse:
    return FileResponse(PAGE, media_type="text/html")


@dev_router.post("/demo/seed")
def seed_demo(
    db: DbDep,
    per_form: int = Query(30, ge=1, le=500),
    seed_value: int = Query(7, alias="seed"),
) -> dict[str, Any]:
    return {"added": seed.seed(db, per_form, seed_value)}
