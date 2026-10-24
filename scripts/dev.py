"""`make dev`: migrate, then run the API (with reload) and the worker until Ctrl+C."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _stop(proc: subprocess.Popen[bytes]) -> None:
    """Stop a process and its children (uvicorn --reload runs the server in a child process)."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()


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
    try:
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
