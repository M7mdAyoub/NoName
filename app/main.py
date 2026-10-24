"""FastAPI app factory: `uvicorn app.main:create_app --factory`."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_error_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.routers import dashboard, draft, forms, health, jobs, review, upload
from app.config import DEV_ENVS, Settings, get_settings
from app.db.connection import Database
from app.logging_setup import configure_logging

log = logging.getLogger("app")
API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None, db: Database | None = None) -> FastAPI:
    settings = settings or get_settings()
    owns_db = db is None

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if owns_db:
            configure_logging(settings.log_level)
        app.state.settings = settings
        app.state.db = db or Database(
            settings.database_path,
            busy_timeout_ms=settings.sqlite_busy_timeout_ms,
            begin_retries=settings.sqlite_begin_retries,
        )
        log.info("api started", extra={"env": settings.app_env})
        try:
            yield
        finally:
            if owns_db:
                app.state.db.close()

    app = FastAPI(title="M&E Platform", version="0.1.0", lifespan=lifespan)
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)  # outermost: sees every request, sets the id

    app.include_router(health.router)
    app.include_router(upload.router)  # MVP routes sit at the root, as docs/MVP.md lists them
    app.include_router(draft.router)
    app.include_router(review.router)
    app.include_router(forms.router)
    app.include_router(dashboard.router)
    api = APIRouter(prefix=API_PREFIX)
    api.include_router(jobs.router)
    if settings.app_env in DEV_ENVS:
        api.include_router(jobs.dev_router)
    app.include_router(api)
    return app
