"""Check the language model the app will use (reads .env exactly as the API does).

    python scripts/check_llm.py

Sends one small structured request through the app's own client and reports the result, or what
to fix: no model configured, server unreachable, wrong model name, wrong key.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.ai.llm import LLMError, OpenAICompatibleLLM  # noqa: E402
from app.config import get_settings  # noqa: E402


class Sum(BaseModel):
    answer: int


def served_models(base_url: str, key: str) -> list[str]:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/models",
                             headers={"Authorization": f"Bearer {key or 'none'}"}, timeout=10)  # fmt: skip
        return [m["id"] for m in response.json().get("data", [])]
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return []


def main() -> int:
    settings = get_settings()
    if settings.llm_use_mock:
        print("No model configured: LLM_BASE_URL is empty (or LLM_MODE=mock), so the app uses its")
        print("built-in rules. To use vLLM, set LLM_BASE_URL in .env (see docs/VLLM.md).")
        return 1
    print(f"Model server: {settings.llm_base_url}  model: {settings.llm_model_extract}")
    llm = OpenAICompatibleLLM(settings)
    started = time.monotonic()
    try:
        out = llm.run("check", "Add the two numbers. Answer with JSON only.", {"a": 2, "b": 3},
                      Sum, lambda s: [] if s.answer == 5 else ["2 + 3 is 5"])  # fmt: skip
    except httpx.ConnectError:
        print(f"FAILED: cannot reach {settings.llm_base_url}. Is vLLM running, and is the port")
        print("open (or an SSH tunnel up)? See docs/VLLM.md.")
        return 1
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        print(f"FAILED: the server answered {status}: {exc.response.text[:300]}")
        if status == 401:
            print("Set LLM_API_KEY in .env to the API_KEY vLLM was started with.")
        elif status == 404:
            names = served_models(settings.llm_base_url, settings.llm_api_key)
            print(f"LLM_MODEL_EXTRACT must be one of the served names: {names or 'unknown'}")
        return 1
    except LLMError as exc:
        print(f"FAILED: the model answered, but not with valid JSON: {exc}")
        return 1
    finally:
        llm.close()
    seconds = time.monotonic() - started
    print(f"OK: the model answered {out.answer} in {seconds:.1f} s. Restart the app to use it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
