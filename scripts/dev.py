"""`make dev`: migrate, then run the API (with reload) and the worker until Ctrl+C.

python scripts/dev.py              # API on http://127.0.0.1:8000 (built frontend at /app/)
python scripts/dev.py --frontend   # also the frontend dev server on http://127.0.0.1:5173
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "outputs" / "impactos-frontend"


def _stop(proc: subprocess.Popen[bytes]) -> None:
    """Stop a process and its children (uvicorn --reload runs the server in a child process)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()


def frontend_dev_server() -> subprocess.Popen[bytes] | None:
    """Vite with hot reload; it proxies the API to :8000. Needs Node.js and `npm install` once."""
    npm = shutil.which("npm")
    if npm is None:
        print("--frontend: npm not found; install Node.js 20+ first")
        return None
    if not (FRONTEND / "node_modules").is_dir():
        subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=FRONTEND, check=True)
    return subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND)


def main() -> int:
    py = sys.executable
    subprocess.run([py, str(ROOT / "scripts" / "migrate.py")], cwd=ROOT, check=True)
    procs = [
        subprocess.Popen(
            [
                py,
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--reload",
                "--reload-dir",
                "app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
        ),
        subprocess.Popen([py, "-m", "app.jobs.worker"], cwd=ROOT),
    ]
    try:  # inside the try: a failed `npm install` must still stop the API and the worker
        if "--frontend" in sys.argv[1:] and (vite := frontend_dev_server()) is not None:
            procs.append(vite)
        while all(p.poll() is None for p in procs):
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                _stop(p)
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
