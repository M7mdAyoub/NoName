"""`make check`: lint + types + tests + migration/route/delete checks. Exit 1 if anything fails."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable

STEPS: list[tuple[str, list[str]]] = [
    ("ruff lint", [PY, "-m", "ruff", "check", "."]),
    ("ruff format", [PY, "-m", "ruff", "format", "--check", "."]),
    ("mypy", [PY, "-m", "mypy"]),
    ("pytest", [PY, "-m", "pytest"]),
    ("migrations", [PY, "scripts/check_migrations.py"]),
    ("routes scoped", [PY, "scripts/check_routes_scoped.py"]),
    ("no hard delete", [PY, "scripts/check_no_hard_delete.py"]),
]

TARGETS = {
    "lint": ("ruff lint", "ruff format", "mypy"),
    "test": ("pytest",),
}


def main(argv: list[str]) -> int:
    wanted = TARGETS.get(argv[0]) if argv else None
    results: list[tuple[str, bool, float]] = []
    for name, cmd in STEPS:
        if wanted is not None and name not in wanted:
            continue
        print(f"\n=== {name}: {' '.join(cmd[1:])}", flush=True)
        started = time.monotonic()
        ok = subprocess.run(cmd, cwd=ROOT).returncode == 0
        results.append((name, ok, time.monotonic() - started))
    print("\n=== summary")
    for name, ok, seconds in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<16} {seconds:5.1f}s")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
