"""Parsed upload -> AI extraction -> draft in the database (docs/MVP.md M2).

Status: parsed -> extracting -> extracted | failed. The LLM work runs with no transaction open;
the draft is written in one short transaction at the end.
"""

from __future__ import annotations

import logging
from typing import Any

from app.ai import pipeline
from app.ai.llm import LLM, make_llm
from app.ai.steps import PROMPT_VERSION
from app.config import Settings
from app.db.connection import Database
from app.db.ids import new_id, utc_now
from app.repositories import draft as draft_repo
from app.repositories import uploads as upload_repo

log = logging.getLogger(__name__)
EXTRACTABLE = ("parsed", "extracted", "failed")


class NotExtractable(ValueError):
    pass


def start(db: Database, upload_id: str) -> None:
    """Mark the upload as extracting, or raise NotExtractable (missing IR, busy, published)."""
    with db.write_tx() as conn:
        upload = upload_repo.get(conn, upload_id)
        if upload is None:
            raise LookupError(upload_id)
        if upload["ir"] is None or upload["status"] not in EXTRACTABLE:
            raise NotExtractable(f"upload is '{upload['status']}', not ready for extraction")
        if draft_repo.has_published(conn):
            raise NotExtractable("a framework is already published; extraction would replace it")
        upload_repo.set_status(conn, upload_id, "extracting", utc_now())


def run(db: Database, settings: Settings, upload_id: str, llm: LLM | None = None) -> None:
    """Run the pipeline for an upload already marked 'extracting' (see `start`). Never raises."""
    try:
        with db.read_tx() as conn:
            upload = upload_repo.get(conn, upload_id)
        assert upload is not None and upload["ir"] is not None
        llm = llm or make_llm(settings)
        draft = pipeline.extract(llm, upload["ir"], settings.llm_max_concurrency)
        summary = _summary(draft, llm)
        with db.write_tx() as conn:
            if draft_repo.has_published(conn):
                raise pipeline.ExtractionError("a framework was published during extraction")
            draft_repo.clear(conn)
            _store(conn, upload_id, draft)
            upload_repo.set_status(conn, upload_id, "extracted", utc_now(), extraction=summary)
    except Exception as exc:
        log.exception("extraction failed", extra={"upload_id": upload_id})
        stats = llm.stats() if llm is not None else None
        with db.write_tx() as conn:
            upload_repo.set_status(conn, upload_id, "failed", utc_now(),
                                   error=f"extraction failed: {exc}", extraction=stats)  # fmt: skip


def extract(db: Database, settings: Settings, upload_id: str, llm: LLM | None = None) -> None:
    start(db, upload_id)
    run(db, settings, upload_id, llm)


def _summary(draft: pipeline.Draft, llm: LLM) -> dict[str, Any]:
    return {
        **llm.stats(),
        "prompt_version": PROMPT_VERSION,
        "tables": draft.tables,
        "counts": {
            "results": len(draft.results),
            "indicators": len(draft.indicators),
            "forms": len(draft.forms),
            "definitions": sum(i.definition is not None for i in draft.indicators),
            "invalid_definitions": sum(bool(i.definition_errors) for i in draft.indicators),
            "open_questions": len(draft.questions),
        },
        "problems": draft.problems,
    }


def _store(conn: Any, upload_id: str, draft: pipeline.Draft) -> None:
    now = utc_now()
    result_ids = {r.key: new_id() for r in draft.results}
    for r in draft.results:
        draft_repo.insert_result(conn, {
            "id": result_ids[r.key], "upload_id": upload_id,
            "parent_id": result_ids[r.parent_key] if r.parent_key else None,
            "level_name": r.level_name, "code": r.code, "statement": r.statement,
            "sort_order": r.sort_order, "created_at": now,
        })  # fmt: skip
    indicator_ids = {i.ref: new_id() for i in draft.indicators}
    for i in draft.indicators:
        draft_repo.insert_indicator(conn, {
            "id": indicator_ids[i.ref], "result_id": result_ids[i.result_key], "code": None,
            "name": i.name, "unit": i.unit, "kind": i.kind, "baseline": i.baseline,
            "target": i.target, "frequency": i.frequency, "data_source": i.data_source,
            "created_at": now,
        })  # fmt: skip
    for form in draft.forms:
        draft_repo.insert_form(conn, new_id(), form.key, form.title,
                               form.form_schema().model_dump(mode="json"), now)  # fmt: skip
    for i in draft.indicators:
        if i.definition is not None:
            draft_repo.insert_definition(conn, new_id(), indicator_ids[i.ref],
                                         i.definition.model_dump(mode="json", exclude_none=True),
                                         now)  # fmt: skip
    for ref, question in draft.questions:
        draft_repo.insert_question(conn, new_id(), indicator_ids[ref] if ref else None, question,
                                   now)  # fmt: skip
