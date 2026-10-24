"""Fail if application code issues a hard DELETE on a table that is not exempt (plan §20.8, D-03)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.db.protection import EXEMPT  # noqa: E402

DELETE_SQL = re.compile(r"\bDELETE\s+FROM\s+[\"`]?(\w+)", re.IGNORECASE)
SA_DELETE = re.compile(r"\bfrom\s+sqlalchemy(?:\.\w+)*\s+import\s+[^\n]*\bdelete\b|\.delete\(")


def scan(root: Path = ROOT / "app") -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in DELETE_SQL.finditer(line):
                if match.group(1).lower() not in EXEMPT:
                    problems.append(
                        f"{path.relative_to(ROOT)}:{number}: hard DELETE on {match.group(1)}"
                    )
            if SA_DELETE.search(line):
                problems.append(
                    f"{path.relative_to(ROOT)}:{number}: SQLAlchemy delete() is not allowed"
                )
    return problems


def main() -> int:
    problems = scan()
    for problem in problems:
        print(f"FAIL: {problem}")
    if not problems:
        print("no forbidden hard deletes")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
