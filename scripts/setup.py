"""One-time setup after cloning: Python packages, .env, database and the frontend build.

    python scripts/setup.py                  # Python 3.12+; Node.js 20+ for the frontend
    python scripts/setup.py --skip-frontend  # backend only

Creates .venv (if missing) and installs requirements.txt into it, copies .env.example to .env (if
missing), applies the database migrations, and builds outputs/impactos-frontend with npm. Safe to
run again: it only redoes what is missing or out of date.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "outputs" / "impactos-frontend"
VENV = ROOT / ".venv"


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def run(*args: str | Path, cwd: Path = ROOT) -> None:
    print("$", " ".join(str(a) for a in args))
    subprocess.run([str(a) for a in args], cwd=cwd, check=True)


def main() -> int:
    if sys.version_info < (3, 12):  # noqa: UP036 - runs on whatever Python the user has
        print(f"Python 3.12 or newer is needed (this is {sys.version.split()[0]}).")
        return 1
    if not venv_python().exists():
        run(sys.executable, "-m", "venv", VENV)
    py = venv_python()
    run(py, "-m", "pip", "install", "--quiet", "--upgrade", "pip")
    run(py, "-m", "pip", "install", "--quiet", "-r", "requirements.txt")
    run(py, "-m", "pip", "install", "--quiet", "--no-deps", "-e", ".")

    env = ROOT / ".env"
    if not env.exists():
        shutil.copyfile(ROOT / ".env.example", env)
        print("created .env from .env.example (no model configured: the app uses built-in rules)")
    run(py, "scripts/migrate.py")

    if "--skip-frontend" not in sys.argv[1:]:
        npm = shutil.which("npm")
        if npm is None:
            print("\nNode.js was not found, so the frontend was not built. Install Node.js 20+")
            print("(https://nodejs.org) and run this again, or use --skip-frontend.")
            return 1
        run(npm, "ci", "--no-audit", "--no-fund", cwd=FRONTEND)
        run(npm, "run", "build", cwd=FRONTEND)

    shown = py.relative_to(ROOT)
    print("\nDone. Start the app with:")
    print(f"    {shown} scripts/dev.py")
    print("and open http://127.0.0.1:8000/  (a language model is optional: see docs/VLLM.md)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
