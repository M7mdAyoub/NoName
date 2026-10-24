"""`GET /dashboard`: every published indicator (KPI) with baseline, target, actual, breakdowns,
the forms that feed it and a tracking status, plus a summary of those statuses.

Values are computed on request by the engine from all submissions; nothing is stored.
Tracking status: `achieved` (progress >= 100 %, or a milestone done), `in_progress` (some
progress), `not_started` (none yet), `no_target` (computed, but no target to compare with) or
`not_computable` (the engine could not compute it; `reason` says why).
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.db.connection import Database
from app.engine.calc import Calculation, Outcome, Record, calculate
from app.repositories import draft as draft_repo
from app.repositories import submissions as repo
from app.schemas.definition import Definition, forms_used
from app.schemas.form import FormSchema

WHOLE_KINDS = frozenset({"count", "milestone"})


def _number(value: float | None, kind: str | None) -> float | int | None:
    if value is not None and kind in WHOLE_KINDS and float(value).is_integer():
        return int(value)
    return value


def _progress(actual: float | None, baseline: float | None, target: float | None) -> float | None:
    """Share of the way from baseline to target, in percent (can be below 0 or above 100)."""
    if actual is None or target is None:
        return None
    start = baseline or 0.0
    if target == start:
        return None
    return round((actual - start) / (target - start) * 100, 1)


TRACKS = ("achieved", "in_progress", "not_started", "no_target", "not_computable")


def _track(out: Outcome, kind: str | None, progress: float | None) -> str:
    if out.status != "ok":
        return "not_computable"
    if kind == "milestone":
        return "achieved" if out.value else "not_started"
    if progress is None:
        return "no_target"
    if progress >= 100:
        return "achieved"
    return "in_progress" if progress > 0 else "not_started"


def _forms_of(raw: dict[str, Any] | None) -> list[str]:
    try:
        return forms_used(Definition.model_validate(raw)) if raw else []
    except ValidationError:
        return []


def get(db: Database) -> dict[str, Any]:
    with db.read_tx() as conn:
        draft = draft_repo.read(conn)
        submissions = repo.by_form(conn)
    forms = {
        f["key"]: FormSchema.model_validate(f["schema"])
        for f in draft["forms"]
        if f["status"] == "published"
    }
    records = {
        key: [Record(row["data"], row["entity_key"]) for row in rows]
        for key, rows in submissions.items()
    }
    definitions = {d["indicator_id"]: d["definition"] for d in draft["definitions"]}
    form_info = {f["key"]: f for f in draft["forms"]}
    results = {r["id"]: r for r in draft["results"]}
    rows = []
    for ind in draft["indicators"]:
        if ind["status"] != "published":
            continue
        calc = _calculate(definitions.get(ind["id"]), forms, records)
        out = calc.outcome
        kind = definitions.get(ind["id"], {}).get("kind") or ind["kind"]
        result = results.get(ind["result_id"])
        progress = _progress(out.value, ind["baseline"], ind["target"])
        feeding = [
            {"key": key, "title": form_info[key]["title"], "submissions": len(records.get(key, [])),
             "origin": form_info[key]["schema"].get("origin")}
            for key in _forms_of(definitions.get(ind["id"])) if key in form_info
        ]  # fmt: skip
        rows.append({
            "indicator_id": ind["id"],
            "code": ind["code"],
            "name": ind["name"],
            "result": {k: result[k] for k in ("id", "level_name", "code", "statement")}
            if result else None,
            "kind": kind,
            "unit": ind["unit"],
            "frequency": ind["frequency"],
            "data_source": ind["data_source"],
            "baseline": ind["baseline"],
            "target": ind["target"],
            "actual": _number(out.value, kind),
            "progress_pct": progress,
            "track": _track(out, kind, progress),
            "forms": feeding,
            "status": out.status,
            "reason": out.reason,
            "records": out.records,
            "components": out.components or None,
            "breakdowns": [
                {"dimension": b.dimension, "label": b.label,
                 "values": [{**v, "actual": _number(v["actual"], kind)} for v in b.values]}
                for b in calc.breakdowns
            ],  # fmt: skip
        })  # fmt: skip
    return {
        "published": bool(rows),
        "results": draft["results"],
        "summary": {"total": len(rows), **{t: sum(r["track"] == t for r in rows) for t in TRACKS}},
        "indicators": rows,
        "submissions": {key: len(rows_) for key, rows_ in submissions.items()},
    }


def _calculate(
    raw: dict[str, Any] | None, forms: dict[str, FormSchema], records: Any
) -> Calculation:
    if raw is None:
        return Calculation(Outcome("not_computable", reason="indicator has no definition"))
    try:
        defn = Definition.model_validate(raw)
    except ValidationError as exc:
        return Calculation(Outcome("not_computable", reason=f"definition does not parse: {exc}"))
    return calculate(defn, forms, records)
