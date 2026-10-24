"""`POST /upload` (files -> parsed IR -> AI extraction in the background), `GET /upload/{id}`
and `POST /upload/{id}/extract` to run the extraction again (docs/MVP.md API)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.api.deps import DbDep, SettingsDep
from app.api.errors import ApiError
from app.services import extraction
from app.services import uploads as service

router = APIRouter(tags=["upload"])


def _summary(upload: dict[str, Any], include_ir: bool) -> dict[str, Any]:
    ir = upload["ir"] or {"files": []}
    body = {
        "id": upload["id"],
        "status": upload["status"],
        "error": upload["error"],
        "files": [
            {"filename": f["filename"], "size_bytes": f["size_bytes"]} for f in upload["files"]
        ],
        "parsed": [
            {"filename": f["source"]["filename"], "stats": f["stats"], "warnings": f["warnings"]}
            for f in ir["files"]
        ],
        "extraction": upload["extraction"],
        "created_at": upload["created_at"],
        "updated_at": upload["updated_at"],
    }
    if include_ir:
        body["ir"] = upload["ir"]
    return body


@router.post("/upload", status_code=201)
def upload(
    db: DbDep,
    settings: SettingsDep,
    background: BackgroundTasks,
    files: Annotated[list[UploadFile], File()],
    extract: bool = True,
) -> dict[str, Any]:
    incoming = [
        service.IncomingFile(filename=f.filename or "file", content=f.file.read()) for f in files
    ]
    try:
        upload_id = service.upload_and_parse(db, settings, incoming)
    except ValueError as exc:
        raise ApiError(422, "validation_failed", str(exc)) from exc
    skipped = None
    if extract and (service.get(db, upload_id) or {}).get("status") == "parsed":
        try:
            extraction.start(db, upload_id)
        except extraction.NotExtractable as exc:
            skipped = str(exc)
        else:
            background.add_task(extraction.run, db, settings, upload_id)
    result = service.get(db, upload_id)
    assert result is not None
    body = _summary(result, include_ir=True)
    if skipped:
        body["extraction_skipped"] = skipped
    return body


@router.post("/upload/{upload_id}/extract", status_code=202)
def extract_upload(
    upload_id: str, db: DbDep, settings: SettingsDep, background: BackgroundTasks
) -> dict[str, Any]:
    try:
        extraction.start(db, upload_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="upload not found") from exc
    except extraction.NotExtractable as exc:
        raise ApiError(409, "conflict", str(exc)) from exc
    background.add_task(extraction.run, db, settings, upload_id)
    result = service.get(db, upload_id)
    assert result is not None
    return _summary(result, include_ir=False)


@router.get("/upload/{upload_id}")
def get_upload(upload_id: str, db: DbDep, ir: bool = True) -> dict[str, Any]:
    result = service.get(db, upload_id)
    if result is None:
        raise HTTPException(status_code=404, detail="upload not found")
    return _summary(result, include_ir=ir)
