"""FastAPI dependencies. Handlers are plain `def`, so they run in the threadpool (decision D-02)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import Connection

from app.config import Settings
from app.db.connection import Database


def get_db(request: Request) -> Database:
    db: Database = request.app.state.db
    return db


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def read_conn(db: Annotated[Database, Depends(get_db)]) -> Iterator[Connection]:
    """One read-only snapshot connection per request. For writes use `db.write_tx()` in a service."""
    with db.read_tx() as conn:
        yield conn


DbDep = Annotated[Database, Depends(get_db)]
ReadConn = Annotated[Connection, Depends(read_conn)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]
