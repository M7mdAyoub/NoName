"""Upload -> store files -> parse to IR (docs/MVP.md M1). Parsing runs outside any transaction."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import Settings
from app.db.connection import Database
from app.db.ids import new_id, utc_now
from app.ingestion import file_type, parse_file
from app.repositories import uploads as repo

log = logging.getLogger(__name__)
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]+")


@dataclass(frozen=True)
class IncomingFile:
    filename: str
    content: bytes


def safe_name(filename: str) -> str:
    name = _UNSAFE.sub("_", Path(filename.replace("\\", "/")).name).strip(" .")
    return name or "file"


def check(files: list[IncomingFile], settings: Settings) -> None:
    """Raise ValueError before anything is stored: no files, wrong type, too large."""
    if not files:
        raise ValueError("no files uploaded")
    limit = settings.upload_max_mb * 1024 * 1024
    for item in files:
        file_type(item.filename)  # UnsupportedFile is a ValueError
        if len(item.content) > limit:
            raise ValueError(f"{item.filename}: larger than {settings.upload_max_mb} MB")


def upload_and_parse(db: Database, settings: Settings, files: list[IncomingFile]) -> str:
    check(files, settings)
    upload_id = new_id()
    folder = settings.files_path / "uploads" / upload_id
    folder.mkdir(parents=True, exist_ok=True)
    stored: list[dict[str, Any]] = []
    for index, item in enumerate(files):
        path = folder / f"{index:02d}_{safe_name(item.filename)}"
        path.write_bytes(item.content)
        stored.append(
            {
                "filename": item.filename,
                "path": str(path),
                "size_bytes": len(item.content),
                "sha256": hashlib.sha256(item.content).hexdigest(),
            }
        )
    with db.write_tx() as conn:
        repo.create(conn, upload_id, stored, utc_now())
        repo.set_status(conn, upload_id, "parsing", utc_now())
    parse_upload(db, upload_id, stored)
    return upload_id


def parse_upload(db: Database, upload_id: str, stored: list[dict[str, Any]]) -> None:
    try:
        irs = [parse_file(Path(f["path"]), f["filename"]) for f in stored]
    except Exception as exc:  # a broken file must not leave the upload stuck in 'parsing'
        log.exception("parse failed", extra={"upload_id": upload_id})
        with db.write_tx() as conn:
            repo.set_status(conn, upload_id, "failed", utc_now(), error=f"parse failed: {exc}")
        return
    with db.write_tx() as conn:
        repo.set_status(conn, upload_id, "parsed", utc_now(), ir={"files": irs})


def get(db: Database, upload_id: str) -> dict[str, Any] | None:
    with db.read_tx() as conn:
        return repo.get(conn, upload_id)
