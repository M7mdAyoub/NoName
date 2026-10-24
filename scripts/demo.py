"""Run the whole MVP flow against a running API and print what each step returns.

    python scripts/dev.py                          # in one terminal (fresh database)
    python scripts/demo.py                         # in another
    python scripts/demo.py --url http://host:8000 --file my_logframe.docx --per-form 50

Steps: upload -> wait for the AI draft -> reviewer edits -> publish -> collect -> dashboard ->
qualitative themes -> CSV export. The reviewer edits are generic (they work for any framework):
every draft form gets a `location` question and every count/sum/average/ratio rule is broken
down by it, so the dashboard shows breakdowns; open questions get an answer. Submissions are
random but valid answers, sent one by one to `POST /forms/{key}/submissions`.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.schemas.form import FormSchema  # noqa: E402
from app.services.seed import fake_submission  # noqa: E402

SAMPLE = ROOT / "tests" / "fixtures" / "sample_logframe.xlsx"
LOCATION = {"id": "location", "type": "select_one", "label": "Location", "required": True,
            "options": [{"value": "north", "label": "North"}, {"value": "central", "label": "Central"},
                        {"value": "south", "label": "South"}]}  # fmt: skip
BREAKDOWN_KINDS = ("count", "sum", "average", "ratio")


class DemoError(Exception):
    pass


def _ok(response: httpx.Response) -> Any:
    if response.is_error:
        raise DemoError(f"{response.request.method} {response.request.url.path}: "
                        f"{response.status_code} {response.text}")  # fmt: skip
    return response.json()


def run(
    client: httpx.Client,
    files: list[Path],
    per_form: int = 30,
    seed: int = 7,
    say: Callable[[str], None] = print,
    poll_seconds: float = 0.5,
) -> dict[str, Any]:
    """The demo flow; returns the final dashboard. `client` has the API as its base URL."""
    if any(f["status"] == "published" for f in _ok(client.get("/forms"))):
        raise DemoError("a framework is already published: stop the API, delete the database "
                        "file (DATABASE_PATH, default data/app.db) and start again")  # fmt: skip

    say(f"1. Upload {', '.join(f.name for f in files)}")
    upload = _ok(client.post("/upload", files=[("files", (f.name, f.read_bytes())) for f in files]))
    while upload["status"] == "extracting":
        time.sleep(poll_seconds)
        upload = _ok(client.get(f"/upload/{upload['id']}", params={"ir": "false"}))
    if upload["status"] != "extracted":
        raise DemoError(f"extraction {upload['status']}: {upload['error']}")
    summary = upload["extraction"]
    counts = summary["counts"]
    say(f"   AI draft ({summary['mode']} LLM): {counts['results']} results, "
        f"{counts['indicators']} indicators, {counts['forms']} forms, "
        f"{counts['definitions']} rules, {counts['open_questions']} open questions")  # fmt: skip

    say("2. Review: add a 'location' question to every form, break rules down by it, "
        "answer open questions")  # fmt: skip
    draft = _ok(client.get("/draft"))
    for form in draft["forms"]:
        schema = form["schema"]
        if all(f["id"] != LOCATION["id"] for f in schema["fields"]):
            schema["fields"].append(LOCATION)
            _ok(client.patch(f"/draft/forms/{form['key']}", json={"schema": schema}))
    for d in draft["definitions"]:
        defn = d["definition"]
        if defn.get("kind") in BREAKDOWN_KINDS and LOCATION["id"] not in defn.get(
            "disaggregate_by", []
        ):
            defn["disaggregate_by"] = [*defn.get("disaggregate_by", []), LOCATION["id"]]
            saved = _ok(client.put(f"/draft/definitions/{d['indicator_id']}",
                                   json={"definition": defn}))  # fmt: skip
            if not saved["valid"]:
                say(f"   rule of {d['indicator_id']} still has problems: {saved['errors']}")
    for q in draft["open_questions"]:
        say(f"   Q: {q['question']}")
        _ok(client.patch(f"/draft/open_questions/{q['id']}",
                         json={"answer": "Checked in review: the proposed rule is right."}))  # fmt: skip

    published = _ok(client.post("/publish"))
    say(f"3. Published {published['forms']} forms and {published['indicators']} indicators")

    say(f"4. Collect {per_form} submissions per form")
    rng = random.Random(seed)  # noqa: S311 - fake data, not security
    pool = [f"P{n:03d}" for n in range(1, max(2, int(per_form * 0.8)) + 1)]
    for item in _ok(client.get("/forms")):
        form = FormSchema.model_validate(_ok(client.get(f"/forms/{item['key']}"))["schema"])
        for _ in range(per_form):
            body = {"data": fake_submission(form, rng, pool)}
            _ok(client.post(f"/forms/{item['key']}/submissions", json=body))

    dashboard: dict[str, Any] = _ok(client.get("/dashboard"))
    say("5. Dashboard (computed by the engine, not the AI)")
    say(f"   {'indicator':<46} {'baseline':>9} {'target':>9} {'actual':>9} {'progress':>9}")
    for ind in dashboard["indicators"]:
        actual = ind["actual"] if ind["status"] == "ok" else f"n/a ({ind['reason']})"
        progress = "" if ind["progress_pct"] is None else f"{ind['progress_pct']}%"
        say(f"   {ind['name'][:46]:<46} {_n(ind['baseline']):>9} {_n(ind['target']):>9} "
            f"{_n(actual):>9} {progress:>9}")  # fmt: skip
    example = next((i for i in dashboard["indicators"] if i["breakdowns"]), None)
    if example:
        b = example["breakdowns"][0]
        parts = ", ".join(f"{v['label']} {_n(v['actual'])}" for v in b["values"])
        say(f"   e.g. '{example['name']}' by {b['label']}: {parts}")

    themes = _ok(client.post("/qualitative", json={}))
    say("6. Qualitative themes in open-text answers")
    for field in themes["fields"]:
        top = ", ".join(f"{t['name']} ({t['count']})" for t in field["themes"]) or "none"
        say(f"   {field['form']}.{field['field']}: {top}")

    csv_text = client.get("/export.csv").text
    say(f"7. GET /export.csv: {len(csv_text.splitlines()) - 1} rows")
    return dashboard


def _n(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    return "-" if value is None else str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--file", type=Path, action="append", dest="files",
                        help=f"framework file(s) to upload (default {SAMPLE.name})")  # fmt: skip
    parser.add_argument("--per-form", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=args.url, timeout=300) as client:
            run(client, args.files or [SAMPLE], args.per_form, args.seed)
    except httpx.ConnectError:
        print(f"cannot reach {args.url}: start the API first (python scripts/dev.py)")
        return 1
    except DemoError as exc:
        print(f"demo stopped: {exc}")
        return 1
    print(f"\nOpen {args.url}/ to see the same data in the browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
