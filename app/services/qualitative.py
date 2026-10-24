"""`POST /qualitative`: themes in the open-text answers of published forms.

Only text fields marked `qualitative` and not `pii` are read. Each field's answers go to the LLM
(or the mock) in one call; the result is computed on request and not stored.
"""

from __future__ import annotations

from typing import Any

from app.ai.llm import LLM, LLMError, make_llm
from app.config import Settings
from app.db.connection import Database
from app.qualitative.themes import PROPOSE_THEMES, STEP, ThemesProposal, check_themes
from app.repositories import draft as draft_repo
from app.repositories import submissions as repo
from app.schemas.form import FormSchema
from app.services.review import NotFound

MAX_ANSWERS = 200  # the most recent ones, to keep one prompt small
QUOTES = 3


def _fields(forms: list[dict[str, Any]], form_key: str | None, field_id: str | None) -> list[Any]:
    found = []
    for form in forms:
        if form["status"] != "published" or form_key not in (None, form["key"]):
            continue
        schema = FormSchema.model_validate(form["schema"])
        for f in schema.fields:
            if f.type == "text" and f.qualitative and not f.pii and field_id in (None, f.id):
                found.append((form["key"], f))
    if (form_key or field_id) and not found:
        raise NotFound("no published qualitative text field matches")
    return found


def analyse(
    db: Database,
    settings: Settings,
    form_key: str | None = None,
    field_id: str | None = None,
    llm: LLM | None = None,
) -> dict[str, Any]:
    with db.read_tx() as conn:
        forms = draft_repo.read(conn)["forms"]
        submissions = repo.by_form(conn)
    targets = _fields(forms, form_key, field_id)
    llm = llm or make_llm(settings)
    out = []
    for key, field in targets:  # no transaction is open during the LLM calls
        answers = [
            value.strip()
            for row in submissions.get(key, [])
            if isinstance(value := row["data"].get(field.id), str) and value.strip()
        ]
        recent = answers[-MAX_ANSWERS:]
        item: dict[str, Any] = {"form": key, "field": field.id, "label": field.label,
                                "answers": len(answers), "analysed": len(recent),
                                "themes": [], "unthemed": len(recent), "error": None}  # fmt: skip
        if recent:
            try:
                proposal = llm.run(
                    STEP,
                    PROPOSE_THEMES,
                    {
                        "question": field.label,
                        "answers": [{"id": i, "text": t} for i, t in enumerate(recent)],
                    },  # fmt: skip
                    ThemesProposal,
                    check_themes(len(recent)),
                )
            except LLMError as exc:
                item["error"] = str(exc)
            else:
                item.update(_summarise(proposal, recent))
        out.append(item)
    return {"fields": out, "llm": llm.stats()}


def _summarise(proposal: ThemesProposal, answers: list[str]) -> dict[str, Any]:
    themed: set[int] = set()
    themes: list[dict[str, Any]] = []
    for theme in proposal.themes:
        ids = sorted(set(theme.answers))
        themed.update(ids)
        quotes = list(dict.fromkeys(answers[i] for i in ids))[:QUOTES]
        themes.append({"name": theme.name, "description": theme.description, "count": len(ids),
                       "share_pct": round(len(ids) / len(answers) * 100, 1),
                       "quotes": quotes})  # fmt: skip
    themes.sort(key=lambda t: -int(t["count"]))
    return {"themes": themes, "unthemed": len(answers) - len(themed)}
