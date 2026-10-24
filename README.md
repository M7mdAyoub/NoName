# AI-powered M&E platform (MVP)

Upload a project's results framework (logframe) and get a working monitoring system:
the AI drafts the results, indicators, data-collection forms and calculation rules, a person
reviews and publishes them, field data comes in through the forms, and a deterministic engine
computes every indicator for the dashboard. **The AI proposes, a person approves, the engine
calculates**: no published number ever comes from the model.

Python 3.12 · FastAPI · SQLite · an OpenAI-compatible LLM (Qwen via vLLM/Ollama), with a built-in
mock so everything runs without a model. Scope and rules: [docs/MVP.md](docs/MVP.md). Build
notes per phase: [docs/HANDOFF.md](docs/HANDOFF.md).

## Setup (once)
```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # macOS/Linux: .venv/bin/python
```

## 5-minute demo
Start from an empty database (stop the API first if it is running; on Windows use `del`):
```bash
rm -f data/app.db data/app.db-wal data/app.db-shm
```
```bash
.venv/Scripts/python scripts/dev.py
```
The API is now on http://127.0.0.1:8000 (migrations run on start). Then either click through
the browser page or run the script.

### In the browser: http://127.0.0.1:8000/
1. **Upload**: pick `tests/fixtures/sample_logframe.xlsx` (a synthetic logframe: 1 impact,
   2 outcomes, 3 outputs, 7 indicators; `.csv`, `.docx` and `.pdf` versions sit beside it) and
   click *Upload and extract*. The file is parsed and the AI drafts everything in a second or two.
2. **Review & publish**: the results tree, each indicator with its kind, baseline and target
   (editable), its calculation rule (valid / problems, editable as JSON), the open questions the
   AI could not settle, and the generated forms. Answer the open question, then *Publish*.
   Publish is refused while any form or rule has problems.
3. **Collect**: pick a form and submit an answer (validated against the form), or click
   *Seed demo data* for 30 random valid submissions per form.
4. **Dashboard**: every indicator grouped by result, with actual vs baseline and target, progress,
   breakdowns and, when a value can't be computed, the reason. *Export CSV* downloads the table.
5. **Themes**: click *Analyse* to group the open-text answers (e.g. session notes) into themes,
   with counts and verbatim quotes.

To show breakdowns, edit a rule before publishing and add `"disaggregate_by": ["sex"]` (any
`select_one` field that every form the rule reads has). The script below does this for you.

### Or as a script (about 3 seconds)
With the API running on an empty database:
```bash
.venv/Scripts/python scripts/demo.py
```
It runs the same flow through the API and prints each step: upload → AI draft → reviewer edits
(adds a *Location* question to every form, breaks each rule down by it, answers the open
question) → publish → 30 submissions per form → the dashboard table → themes → CSV export.
Then open http://127.0.0.1:8000/ to see the result in the browser. Options: `--file` (repeat for
several files), `--per-form`, `--seed`, `--url`.

## Using a real model
The mock is used unless a model is configured. For Ollama or vLLM, set in `.env` (see
`.env.example`):
```
LLM_MODE=real
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_EXTRACT=qwen2.5:14b-instruct
```
Every model answer is checked against a JSON schema and deterministic rules and retried with the
errors (3 attempts); the result is only a draft until a person publishes it.

## API
| Method | Path | What |
|---|---|---|
| POST | `/upload` | multipart `files`; parses, then extracts in the background |
| GET | `/upload/{id}` | status (`extracting` → `extracted` / `failed`) and summary; `?ir=false` |
| POST | `/upload/{id}/extract` | re-run the extraction (before anything is published) |
| GET | `/draft` | results, indicators, forms, definitions (with `valid`/`errors`), open questions |
| PATCH | `/draft/results/{id}`, `/draft/indicators/{id}`, `/draft/forms/{key}`, `/draft/open_questions/{id}` | review edits |
| PUT | `/draft/definitions/{indicator_id}` | replace a calculation rule |
| POST | `/publish` | publish forms and indicators (422 with the problems if any) |
| GET | `/forms`, `/forms/{key}` | published forms and their schema |
| POST | `/forms/{key}/submissions` | `{"data": {field_id: answer}, "collected_at"?}` |
| GET | `/dashboard` | every published indicator: baseline, target, actual, progress, breakdowns, status/reason |
| GET | `/export.csv` | the dashboard as a flat table (one row per indicator and breakdown value) |
| POST | `/qualitative` | themes in open-text answers; optional `{"form", "field"}` |
| POST | `/demo/seed` | development only: `?per_form=30` random submissions per published form |

Interactive docs at http://127.0.0.1:8000/docs. Form and rule formats are described in
[docs/HANDOFF.md](docs/HANDOFF.md) (M2, "Formats M3 must use").

## Development
```bash
.venv/Scripts/python scripts/check.py         # lint, format, mypy, tests, migration and route checks
.venv/Scripts/python scripts/seed.py          # seed DATABASE_PATH directly (API not needed)
.venv/Scripts/python scripts/make_samples.py  # regenerate the sample frameworks
```
`docs/phases/` and `docs/handoff/` hold the original 14-session plan for the full platform; the
MVP in `docs/MVP.md` overrides them.
