"""Fake but valid submissions for every published form, so the dashboard has something to show.

Used by `scripts/seed.py` and the dev-only `POST /demo/seed`. Each answer goes through the same
validation as `POST /forms/{key}/submissions`. Entity keys come from a pool smaller than the
number of submissions, so distinct counts are lower than record counts, as in real data.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from app.db.connection import Database
from app.schemas.form import FormField, FormSchema
from app.services import submissions

# Open-text answers for `qualitative` fields; recurring topics give the theme analysis something
# to find. Deliberately generic (no project or place names).
NOTES = [
    "Session went well, participants asked for more practical work.",
    "Low attendance because of the harvest season.",
    "Materials arrived late; the trainer improvised with what was available.",
    "Participants requested follow-up visits to their farms.",
    "Good engagement from the cooperative members.",
    "Attendance dropped in the afternoon, many participants had to collect children.",
    "Training materials were too few for the group, people had to share.",
    "The trainer asked for more time on practical demonstrations.",
    "Several women said transport costs make it hard to attend.",
    "Participants want follow-up support after the training ends.",
    "Cooperative members shared their own experience, engagement was high.",
    "Transport to the venue was difficult after the rain.",
]


def fake_answer(f: FormField, rng: random.Random, pool: list[str], key_field: str | None) -> Any:
    if f.id == key_field or (f.type == "text" and f.pii):
        return rng.choice(pool)
    if f.type == "text":
        return rng.choice(NOTES) if f.qualitative else f"sample {f.label.lower()}"
    if f.type in ("integer", "decimal"):
        lo = f.constraints.min if f.constraints and f.constraints.min is not None else 0.0
        hi = f.constraints.max if f.constraints and f.constraints.max is not None else lo + 1000
        return (
            rng.randint(int(lo), int(hi)) if f.type == "integer" else round(rng.uniform(lo, hi), 2)
        )
    if f.type == "select_one":
        return rng.choice(f.options).value
    if f.type == "select_multiple":
        return [o.value for o in rng.sample(f.options, rng.randint(1, len(f.options)))]
    return (datetime.now(UTC).date() - timedelta(days=rng.randint(0, 365))).isoformat()


def fake_submission(form: FormSchema, rng: random.Random, pool: list[str]) -> dict[str, Any]:
    return {
        f.id: fake_answer(f, rng, pool, form.entity_key_field)
        for f in form.fields
        if f.required or f.id == form.entity_key_field or rng.random() < 0.8
    }


def seed(db: Database, per_form: int = 30, seed_value: int = 7) -> dict[str, int]:
    """Add `per_form` submissions to every published form; returns how many went into each."""
    rng = random.Random(seed_value)  # noqa: S311 - fake data, not security
    pool = [f"P{n:03d}" for n in range(1, max(2, int(per_form * 0.8)) + 1)]
    now = datetime.now(UTC)
    added: dict[str, int] = {}
    for item in submissions.list_forms(db):
        if item["status"] != "published":
            continue
        form = FormSchema.model_validate(submissions.get_form(db, item["key"])["schema"])
        for _ in range(per_form):
            when = (now - timedelta(days=rng.randint(0, 180))).isoformat()
            submissions.submit(db, item["key"], fake_submission(form, rng, pool), when)
        added[item["key"]] = per_form
    return added
