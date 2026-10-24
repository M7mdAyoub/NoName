"""Fill every published form with fake submissions so the dashboard has something to show.

    python scripts/seed.py                 # 30 submissions per published form, seed 7
    python scripts/seed.py --per-form 100 --seed 1

Answers are random but valid: each one goes through the same validation as
`POST /forms/{key}/submissions`. Entity keys come from a pool smaller than the number of
submissions, so distinct counts are lower than record counts, as in real data.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db.connection import Database  # noqa: E402
from app.db.migrate import migrate  # noqa: E402
from app.schemas.form import FormField, FormSchema  # noqa: E402
from app.services import submissions  # noqa: E402

NOTES = [
    "Session went well, participants asked for more practical work.",
    "Low attendance because of the harvest.",
    "Materials arrived late; the trainer improvised.",
    "Participants requested follow-up visits.",
    "Good engagement from the cooperative members.",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--per-form", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    settings = get_settings()
    db = Database(settings.database_path)
    try:
        migrate(db)
        added = seed(db, args.per_form, args.seed)
    finally:
        db.close()
    if not added:
        print("no published forms: upload a framework and POST /publish first")
        return 1
    for key, n in added.items():
        print(f"{key}: +{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
