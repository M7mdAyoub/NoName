"""Fill every published form with fake submissions so the dashboard has something to show.

    python scripts/seed.py                 # 30 submissions per published form, seed 7
    python scripts/seed.py --per-form 100 --seed 1

Answers are random but valid (see `app/services/seed.py`). Writes straight to DATABASE_PATH;
with the API running, the dashboard's "Seed demo data" button (`POST /demo/seed`) does the same.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import get_settings  # noqa: E402
from app.db.connection import Database  # noqa: E402
from app.db.migrate import migrate  # noqa: E402
from app.services.seed import seed  # noqa: E402

__all__ = ["seed"]


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
