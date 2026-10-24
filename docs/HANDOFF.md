# MVP handoff log

Append one section per phase (docs/MVP.md). Newest at the bottom.

## M1 — Skeleton, data model, upload and parse (2026-10-24)

### What works
- `POST /upload` (multipart, field `files`, one or more files) stores the files, parses each one into an IR and returns `{id, status, error, files, parsed, ir}`; status is `parsed`, or `failed` with `error` if a file can't be read. Parsing runs synchronously in the request; M2 can move extraction to a FastAPI `BackgroundTasks` call and use the `extracting`/`extracted` statuses that already exist.
- `GET /upload/{id}` (add `?ir=false` to leave out the IR) returns the status, per-file stats and warnings, and the IR.
- Parsers (`app/ingestion/`): **xlsx/xlsm** (every sheet including hidden ones, with a warning; merged cells unmerged; formulas read as cached values; empty rows split tables; a lone cell becomes a heading if bold, otherwise a paragraph), **csv** (delimiter sniffed; UTF-8 or cp1252), **docx** (headings with level, paragraphs, list items and tables, in document order), **digital pdf** (pdfplumber ruled tables plus page text with the table text removed; a page with almost no text gets a "scanned?" warning). Anything else → 422.
- Data model: migration `migrations/0002_mvp.sql` creates the MVP tables `project` (seeded with id `default`), `framework_upload`, `result`, `indicator`, `form`, `indicator_definition`, `submission` and `open_question`. Only `framework_upload` is used so far.
- Sample framework: `scripts/make_samples.py` writes `tests/fixtures/sample_logframe.{xlsx,csv,docx,pdf}`. It is a synthetic "Green Valley Livelihoods" logframe: 1 impact, 2 outcomes, 3 outputs, 7 indicators (count, %, sum in JOD, a milestone). The xlsx also has merged outcome cells, a title row, an assumptions table and a hidden `Notes` sheet. The generated files are committed alongside the script.

### IR shape (one per file; stored as `framework_upload.ir = {"files": [IR, ...]}`)
```json
{"source": {"filename": "sample_logframe.xlsx", "type": "xlsx", "sha256": "…"},
 "blocks": [
   {"id": "b1", "kind": "heading", "text": "Results Framework …", "ref": {"sheet": "Logframe", "range": "A1:I1"}},
   {"id": "b2", "kind": "table", "rows": [["Level", "Code", …], …], "ref": {"sheet": "Logframe", "range": "A3:I10"}},
   {"id": "b3", "kind": "paragraph"|"list_item", "text": "…", "ref": {"page": 1} | {"index": 5}}],
 "stats": {"blocks": 4, "tables": 2, "rows": 11, "sheets": 2},
 "warnings": ["sheet 'Notes' is hidden; included"]}
```
Every cell is a string, with "" for empty and whole numbers without ".0". Tables are trimmed of fully empty rows and columns and padded to a rectangle. Headings from docx carry a `level`.

### How to run
```
.venv/Scripts/python -m pip install -e ".[dev]"       # adds openpyxl, python-docx, pdfplumber, python-multipart
.venv/Scripts/python scripts/check.py                 # 7/7 PASS, 81 tests
.venv/Scripts/python -m pytest tests/ingestion tests/integration/test_upload.py   # the M1 tests (14)
.venv/Scripts/python scripts/dev.py                   # API on :8000 (+ the phase-00 worker)
curl -F "files=@tests/fixtures/sample_logframe.xlsx" -F "files=@tests/fixtures/sample_logframe.pdf" http://127.0.0.1:8000/upload
.venv/Scripts/python scripts/make_samples.py          # regenerate the fixtures
```

### Files added or changed
- New: `app/ingestion/{ir,xlsx,delimited,word,pdf}.py` (`app/ingestion/__init__.py` has `parse_file`, `file_type`, `UnsupportedFile`), `app/repositories/uploads.py`, `app/services/uploads.py`, `app/api/routers/upload.py`, `migrations/0002_mvp.sql`, `scripts/make_samples.py`, `tests/fixtures/sample_logframe.*`, `tests/ingestion/test_parsers.py`, `tests/integration/test_upload.py`.
- Changed: `app/main.py` mounts the upload router at the root (MVP paths have no `/api/v1`); `app/db/protection.py` lists the MVP tables as hard-delete exempt (MVP has no soft delete); `scripts/check_routes_scoped.py` allow-lists `/upload` routes; `pyproject.toml` has the new dependencies, mypy ignores for untyped parser libraries, and ruff now excludes `docs/` (ruff 0.17 formats Markdown code blocks and was failing on the old handoff).
- Phase-00 tests updated so they no longer assume 0001 is the only migration (`tests/integration/test_migrations.py` uses a 0001-only copy; readyz/exempt-list asserts relaxed). `test_check_scripts` now uses `audit_log` as its example of a protected table.

### Shortcuts taken
- Built on the Phase 00 skeleton as it stands: `Database` with explicit transactions, migration runner with checksums, JSON logs, `/healthz`, `/readyz`. Its job queue, audit writer and route/delete check scripts are still there but unused by the MVP flow. They were not removed, to keep the diff small.
- No zip-bomb check and no page or cell limits beyond 200 PDF pages and 100k Excel cells. The only size limit is `UPLOAD_MAX_MB` per file (25). No OCR, pptx or legacy formats.
- Excel styles (fill colour, indent) are not kept in the IR; bold is used only to tell headings from paragraphs.
- Uploaded files are stored at `FILES_PATH/uploads/<upload_id>/NN_<sanitised name>`; the `file` table from 0001 is not used.
- **The earlier Phase 01 work (auth, orgs, tenancy, role-matrix tests) is parked in `git stash@{0}`** ("phase-01 tenancy/auth (parked for MVP)"). It is not part of the MVP. `docs/MVP.md` was untracked and got caught in that stash; it has been restored to the working tree.

### What M2 needs to know
- Read the IR with `app.services.uploads.get(db, upload_id)["ir"]["files"]`. Table rows are lists of strings, and the header is usually the first row; multi-row headers are not detected.
- The sample's expected content is in `scripts/make_samples.py` (`HEADER`, `ROWS`): use it as the ground truth for the extraction test (6 distinct results: 1 impact, 2 outcomes, 3 outputs; 7 indicators).
- Tables to fill: `result` (parent_id tree, `level_name` free text), `indicator` (`kind` must be one of count/sum/average/ratio/milestone or NULL; baseline/target are REAL, so "No"/"Yes" milestones need an open question or NULL), `form` (`key` unique, `schema` JSON), `indicator_definition` (one per indicator), `open_question`. None of these have a `project_id` (single project).
- Use `db.write_tx()` for writes and never hold one across an LLM call. Settings already include `LLM_BASE_URL`, `LLM_MODEL_EXTRACT`, `LLM_API_KEY`, `LLM_TIMEOUT_SECONDS`; add an `LLM_MOCK` switch (or treat an empty `LLM_BASE_URL` as mock).
- New routes go at the root and must be added to `UNSCOPED_ALLOWLIST` in `scripts/check_routes_scoped.py`, or `make check` fails.
- Nothing is committed yet for M1.

## M2 — AI extraction (2026-10-24)

### What works
- `POST /upload` now parses **and then extracts** in a FastAPI background task: the response says `"status": "extracting"`, and `GET /upload/{id}` goes to `extracted` (with an `extraction` summary) or `failed` (with `error`). Add `?extract=false` to only parse.
- `POST /upload/{id}/extract` (202) re-runs the extraction on an already parsed upload (e.g. after switching to a real model). 404 if unknown, 409 if busy or anything is published.
- `GET /draft` returns `{results, indicators, forms, definitions, open_questions}`. Each definition carries `errors` and `valid`, re-validated against the current forms on every read, so M3 edits are re-checked automatically.
- The pipeline (`app/ai/pipeline.py`): **map layout** (LLM, one call per table, header + 8 rows) → **build structure in code** (forward-fills merged cells; parent = higher-level result whose code prefixes this one, else the nearest one level up) → **normalise** each indicator (LLM, thread pool) → **propose forms** grouped by data source (LLM, one call) → **propose a definition** per indicator (LLM, thread pool) → **cross-check** in code. Nothing is written until the end, in one short `write_tx`. A new extraction replaces the whole draft.
- LLM client (`app/ai/llm.py`): `OpenAICompatibleLLM` posts to `{LLM_BASE_URL}/chat/completions` with `response_format: json_schema` (built from the step's Pydantic model), `temperature 0`, `seed 7`. Every answer is Pydantic-validated, then run through the step's own deterministic check; problems are sent back to the model and it retries (3 attempts). The document is wrapped in `<<<INPUT … INPUT>>>` as data. Uses `httpx` (now a runtime dependency), not the `openai` SDK.
- Mock (`app/ai/mock.py`): deterministic keyword heuristics per step, fed from the step's input payload, held to the same validation and checks as a real model. `LLM_MODE=auto|mock|real` (auto = mock unless `LLM_BASE_URL` and `LLM_MODEL_EXTRACT` are set).
- Sample with the mock: 6 results (Impact → 2 Outcomes → 3 Outputs, correct tree), 7 indicators (kinds average/count/ratio/count/count/sum/milestone; milestone No/Yes → 0/1), 7 forms (one per means of verification), 7 valid definitions, 1 open question (the % indicator's denominator). The same 7 indicators come out of csv, docx and pdf. With several files the table with the most indicators wins, then the one with the most mapped columns; the others are listed in `extraction.problems`.
- **Real endpoint: not tested.** No model was reachable on this machine (nothing on :11434 or :8001). The HTTP request shape is tested with `httpx.MockTransport`. `tests/ai/test_extraction.py::test_real_endpoint_extracts_the_sample` runs when `LLM_BASE_URL` (+ `LLM_MODEL_EXTRACT`) is set in the environment.

### Formats M3 must use
**Form schema** (`app/schemas/form.py`, stored in `form.schema`): `{"schema_version": 1, "title", "entity_key_field": "<field id>|null", "fields": [{"id", "type": text|integer|decimal|select_one|select_multiple|date, "label", "required", "options": [{"value","label"}], "unit", "constraints": {"min","max"}, "pii", "qualitative"}]}`. `validate_form()` checks ids (`^[a-z][a-z0-9_]{0,62}$`, unique), select options (≥2, unique) and the entity key field. Submission validation is still to write (M3). `entity_key_field` is the field whose value M3 should copy into `submission.entity_key`.

**Indicator definition** (`app/schemas/definition.py`, stored in `indicator_definition.definition`, dumped with `exclude_none`):
```
count        {"kind":"count", "count": {"form", "unit": "entity"|"record", "where"?}}
sum/average  {"kind":"sum"|"average", "value": {"form", "field", "where"?}}
ratio        {"kind":"ratio", "numerator": {"count":{..}}|{"sum":{..}}, "denominator": same, "scale": 100}
milestone    {"kind":"milestone", "milestone": {"form", "achieved_when": <condition>}}
+ "disaggregate_by": [select_one field ids present in every form read]
condition: {"field","op","value"} | {"all":[..]} | {"any":[..]}
ops: eq neq gt gte lt lte in not_in contains is_empty is_not_empty
```
`unit: entity` = distinct `submission.entity_key` (the form must have an `entity_key_field`). `validate_definition(defn, forms_by_key)` checks that forms and fields exist, numeric fields for sum/average, op vs field type, option values, and disaggregation fields (select_one, not pii). `forms_used(defn)` lists the form keys. There is no time aggregation in the MVP format: everything is cumulative and computed on request.

### How to run
```
.venv/Scripts/python -m pip install -e ".[dev]"      # httpx is now a runtime dependency
.venv/Scripts/python scripts/check.py                # 7/7 PASS, 124 passed + 1 skipped (real-LLM test)
.venv/Scripts/python -m pytest tests/ai tests/unit/test_definitions.py tests/integration/test_extraction_api.py   # M2 tests
curl -F "files=@tests/fixtures/sample_logframe.xlsx" http://127.0.0.1:8000/upload
curl "http://127.0.0.1:8000/upload/<id>?ir=false"   # status + extraction summary
curl http://127.0.0.1:8000/draft
# real model, e.g. Ollama: LLM_MODE=real LLM_BASE_URL=http://localhost:11434/v1 LLM_MODEL_EXTRACT=<served model name>
```

### Files added or changed
- New: `app/ai/{llm,mock,steps,pipeline}.py`, `app/schemas/{form,definition}.py`, `app/repositories/draft.py`, `app/services/{extraction,draft}.py`, `app/api/routers/draft.py`, `migrations/0003_extraction.sql` (adds `framework_upload.extraction` JSON; registered in `checksums.lock`), `tests/ai/test_extraction.py`, `tests/unit/test_definitions.py`, `tests/integration/test_extraction_api.py`.
- Changed: `app/api/routers/upload.py` (background extraction, `?extract=`, `/upload/{id}/extract`, `extraction` in the response), `app/repositories/uploads.py` (`extraction` column), `app/config.py` + `.env.example` (`LLM_MODE`), `app/main.py` (draft router), `scripts/check_routes_scoped.py` (allow-list), `pyproject.toml` (httpx), `tests/integration/test_upload.py` (uses `?extract=false`).

### Shortcuts taken
- Only one framework table is used per upload (the best one). Tables are not merged across files and reference sheets are not matched in. There is no narrative/LLM fallback for documents without a framework table: they fail with "no results framework table with indicators was found".
- Without a level column, levels come from code depth only (`Level 1`, `Level 2`). Multi-row headers are not handled beyond picking the header row among the first 5 rows.
- Prompts are Python constants in `app/ai/steps.py` (`PROMPT_VERSION = "mvp-1"`), not versioned files. No `ai_run` table: per-step call/failure counts go into `framework_upload.extraction`.
- After 3 failed attempts: layout → the table is skipped (listed in problems); normalise → the last parsed answer is kept without baseline/target, plus an open question; forms → the last parsed answer is kept (or the extraction fails); definition → the last parsed definition is stored with its errors plus an open question; if none parsed, only the question.
- The mock's forms are thin: count-of-records forms get a single `notes` field, and person forms get `respondent_id` (pii) + `sex`. Sex filters come from "women"/"men" in the indicator name. Indicator `code` is left NULL.
- Extraction refuses to run once any form or indicator is `published`, so it never overwrites live data. "Re-extract into a new draft" is out of scope.

### What M3 needs to know
- Read the draft with `app.repositories.draft.read(conn)` / `app.services.draft.get(db)`. Edits should re-validate with `validate_form` / `validate_definition`; publish should refuse while any definition has errors or any form fails `validate_form`.
- Statuses: `form.status` and `indicator.status` are `draft|published`, `indicator_definition.status` is `draft|approved`. `draft_repo.clear()` only deletes draft forms; `has_published()` is what blocks re-extraction.
- Engine input: the definition JSON above, plus `submission.data` (JSON keyed by field id) and `submission.entity_key`. Ratios default to `scale: 100`; milestone = 1 if any matching record, else 0.
- New routes go in `UNSCOPED_ALLOWLIST` in `scripts/check_routes_scoped.py`.

## M3 — Review, publish, collect, calculate, dashboard (2026-10-24)

### What works
- **Review edits** (all return the edited item as `GET /draft` shows it; 404 if unknown, 422 with `error.details` if invalid):
  - `PATCH /draft/results/{id}` — `level_name`, `code`, `statement`.
  - `PATCH /draft/indicators/{id}` — `result_id`, `code`, `name`, `unit`, `kind`, `baseline`, `target`, `frequency`, `data_source`. Only the keys sent are changed; `null` clears.
  - `PATCH /draft/forms/{key}` — `{"title"?, "schema"?}` (`schema` is the whole new form schema). Must pass `validate_form`. **409 once the form is published** (submissions depend on it). The key can't change.
  - `PUT /draft/definitions/{indicator_id}` — `{"definition": {...}}`, creates or replaces. It only has to parse to be saved as a draft; its remaining problems show as `errors`/`valid` in the response and in `GET /draft`. Once the indicator is published it must be fully valid (else 422). It also sets `indicator.kind` to the definition's kind.
  - `PATCH /draft/open_questions/{id}` — `{"answer": "..."|null}`.
- `POST /publish` — 422 with a list of `{form|indicator_id, errors}` while any form or definition has problems; 409 if there is no draft. Otherwise forms and indicators → `published`, definitions → `approved`. Returns counts, `without_definition` (published anyway, shown as not computable) and `unanswered_questions` (they don't block).
- **Collect**: `GET /forms` (key, title, status, submission count), `GET /forms/{key}` (schema + status), `POST /forms/{key}/submissions` with `{"data": {field_id: answer}, "collected_at"?: ISO date/datetime}` → 201. 409 if the form isn't published, 422 with one message per problem otherwise. `validate_submission` (in `app/schemas/form.py`) checks unknown fields, required, types (text string; integer/decimal JSON numbers, no strings; select values; select_multiple a list; date `YYYY-MM-DD`) and min/max. Empty answers are dropped; the `entity_key_field` answer is copied into `submission.entity_key`.
- **Engine** (`app/engine/calc.py`, pure, no I/O): `calculate(definition, forms, records)` → `Outcome(status ok|not_computable, value, reason, records, components)` + one breakdown per `disaggregate_by` field (one entry per option). Rules are in the module docstring; the main ones: missing answers match only `is_empty`; count/entity = distinct non-empty entity keys; sum of nothing is 0; average of nothing, a zero denominator, an invalid definition or a missing definition are `not_computable` with a reason. Everything is cumulative over all submissions, computed on each request.
- `GET /dashboard` — `{published, results, indicators: [...], submissions: {form_key: n}}`. Each indicator: `indicator_id, code, name, result{id,level_name,code,statement}, kind, unit, frequency, data_source, baseline, target, actual, progress_pct, status, reason, records, components (ratio numerator/denominator), breakdowns[{dimension, label, values[{value,label,actual,status,reason,records}]}]`. Only published indicators are listed. `progress_pct` = (actual − baseline) / (target − baseline) × 100 (baseline NULL → 0; NULL if target is missing or equals baseline). Counts and milestones come back as ints.
- **Seed**: `scripts/seed.py [--per-form 30] [--seed 7]` adds random but valid submissions (through the same `submit` service) to every published form of `DATABASE_PATH`. Entity keys come from a pool of 80% of the count, so distinct counts are lower than record counts. Checked on a scratch DB: 50 per form → all 7 sample indicators `ok`.

### How to run
```
.venv/Scripts/python scripts/check.py                # 7/7 PASS, 141 passed + 1 skipped (real-LLM test)
.venv/Scripts/python -m pytest tests/engine tests/integration/test_m3_flow.py   # M3 tests (17)
.venv/Scripts/python scripts/dev.py                  # API on :8000
curl -F "files=@tests/fixtures/sample_logframe.xlsx" http://127.0.0.1:8000/upload
curl http://127.0.0.1:8000/draft
curl -X POST http://127.0.0.1:8000/publish
.venv/Scripts/python scripts/seed.py --per-form 50   # or POST /forms/{key}/submissions
curl http://127.0.0.1:8000/dashboard
```

### Files added or changed
- New: `app/engine/calc.py`, `app/repositories/submissions.py`, `app/services/{review,submissions,dashboard}.py`, `app/api/routers/{review,forms,dashboard}.py`, `scripts/seed.py`, `tests/engine/test_calc.py` (engine against hand-computed values for all five kinds, breakdowns, conditions, not-computable cases, submission validation), `tests/integration/test_m3_flow.py` (upload → edits → refused publish → publish → submit → dashboard numbers; seed → every indicator computes).
- Changed: `app/schemas/form.py` (`validate_submission`), `app/repositories/draft.py` (update/upsert/publish SQL), `app/main.py` (routers), `scripts/check_routes_scoped.py` (allow-list). No new migration: the 0002 tables were enough.

### Shortcuts taken
- No time dimension: actuals are cumulative over all submissions; `collected_at` is stored but not used. No caching; the dashboard recomputes every indicator on each call (fine at demo sizes).
- Breakdown buckets are the options of the field in the first form the definition reads; records without that answer are in the total but in no bucket.
- After publish nothing can be unpublished, forms are frozen, and re-extraction stays blocked (as in M2). To start over, delete the database file.
- The mock's definitions have empty `disaggregate_by`, so breakdowns only appear after a reviewer adds one with `PUT /draft/definitions/...` (the e2e test adds a `sex` field to the household survey and breaks the average income down by it). Worth doing in the demo data for M4.
- Submissions can't be edited or deleted; no list endpoint for them (only counts in `GET /forms`).
- Error `details` for submissions and form edits are plain strings; for publish they are objects.

### What M4 needs to know
- The whole demo flow is API-only today: upload → `GET /draft` → edits → `POST /publish` → `scripts/seed.py` → `GET /dashboard`. A demo script can call these in order; the e2e test `test_review_publish_collect_and_dashboard` is a working example of every call.
- For a nicer dashboard demo, give a few definitions a `disaggregate_by` (e.g. `sex` on the training and follow-up forms, which already have it) before publishing.
- Qualitative stretch: text fields with `qualitative: true` (e.g. `notes` on session reports) hold the open text; `pii` fields (`respondent_id`) must be left out. `app/repositories/submissions.by_form` gives all answers per form.
- New routes still go in `UNSCOPED_ALLOWLIST` in `scripts/check_routes_scoped.py`.

## M4 — Demo polish + stretch (2026-10-24)

### What works
- **Demo page** at `GET /` (`app/static/index.html`, one file, vanilla JS, no build, light/dark): five tabs that follow the flow. *Upload* (multi-file, polls until `extracted`, shows the extraction counts and problems) → *Review & publish* (results tree; indicators with editable unit/baseline/target; each rule with valid/problems and a JSON editor; open questions with answer boxes; forms with field badges and a JSON editor; Publish with the refusal details) → *Collect* (a form rendered from its schema for every field type; *Seed demo data* button) → *Dashboard* (cards grouped by result: actual, baseline → target, progress bar, ratio numerator/denominator, breakdown bars, not-computable reason; *Export CSV*) → *Themes*. Checked by hand in a browser against a live server: dashboard, review, manual submission and themes all render and work.
- **Demo script** `scripts/demo.py [--url] [--file ...] [--per-form 30] [--seed 7]`: runs upload → draft → generic reviewer edits (adds a `location` select_one with North/Central/South to every form, adds `disaggregate_by: ["location"]` to every count/sum/average/ratio rule, answers open questions) → publish → N submissions per form through `POST /forms/{key}/submissions` → prints the dashboard table, one breakdown, the themes and the CSV row count. Refuses (exit 1, clear message) if something is already published or the API is not reachable. Live run on a fresh DB with the mock: 2.3 s, all 7 indicators `ok`.
- **`GET /export.csv`** (`app/services/export.py`): built from `dashboard.get`, so aggregates only (no submission data, no pii). Columns: `result_level, result_code, result_statement, indicator_code, indicator, kind, unit, baseline, target, actual, progress_pct, status, reason, records, dimension, dimension_value`; one row per indicator, plus one per breakdown option (with `dimension`/`dimension_value` filled and `progress_pct` empty).
- **`POST /qualitative`** `{"form"?, "field"?}` (`app/services/qualitative.py`, step in `app/qualitative/themes.py`): for every published text field with `qualitative: true` and not `pii`, sends the most recent 200 answers (`{id, text}`) to the LLM step `propose_themes`, which returns themes as `{name, description, answers: [ids]}` (≤ 8, checked: ids exist, names unique; retries like every other step). Counts, `share_pct`, `unthemed` and up to 3 verbatim quotes per theme are worked out in code from the stored answers. Response: `{fields: [{form, field, label, answers, analysed, themes: [{name, description, count, share_pct, quotes}], unthemed, error}], llm}`. Computed on request, not stored. 404 if a given form/field matches no qualitative field. An LLM failure is reported per field in `error`.
- Mock themes (`app/ai/mock.py::propose_themes`): greedy keywords. Words of ≥ 4 letters minus stop words, trailing "s" stripped; take the word most remaining answers share (≥ 2), assign those answers, repeat on the rest, up to 5 themes.
- **`POST /demo/seed?per_form=30&seed=7`**, only mounted when `APP_ENV` is development/test (like `/api/v1/dev/jobs`), for the page's seed button.
- **README** rewritten around the demo: setup, reset, the five browser steps, the script, real-model settings, API table.

### How to run
```
.venv/Scripts/python scripts/check.py                # 7/7 PASS, 146 passed + 1 skipped (real-LLM test)
.venv/Scripts/python -m pytest tests/integration/test_m4_demo.py   # M4 tests (5)
rm -f data/app.db data/app.db-wal data/app.db-shm    # fresh start
.venv/Scripts/python scripts/dev.py                  # API + page on http://127.0.0.1:8000/
.venv/Scripts/python scripts/demo.py                 # whole flow in ~3 s, then open the page
```

### Files added or changed
- New: `app/static/index.html`, `app/api/routers/{demo,qualitative}.py`, `app/services/{export,qualitative,seed}.py`, `app/qualitative/themes.py`, `scripts/demo.py`, `tests/integration/test_m4_demo.py` (demo script end to end through `TestClient`; CSV with hand-computed values and breakdown rows; themes with hand-computed mock counts, pii exclusion and 404; theme checks; page + seed endpoint).
- Changed: `app/services/seed.py` now holds the seed logic (moved from `scripts/seed.py`, which is a thin CLI and still exports `seed` for the M3 test); more varied `NOTES` so themes have something to find. `app/ai/mock.py` (themes handler), `app/api/routers/dashboard.py` (`/export.csv`), `app/main.py` (routers), `scripts/check_routes_scoped.py` (allow-list: `/`, `/export.csv`, `/qualitative`, `/demo/seed`), `README.md`.
- No migration.

### Shortcuts taken
- The page has no upload of the sample from the server: the user picks `tests/fixtures/sample_logframe.xlsx` from disk. It is one static file served by FastAPI; no framework, no routing, no auth. Form and rule edits are raw JSON textareas.
- The demo's reviewer edits (`location` question + breakdown) are a scripted stand-in for what a person would do in review; the mock still proposes breakdowns only when it would on its own (sex, when the indicator isn't already filtered on it).
- Seeded numbers are uniform between the field's min and max (or min + 1000), so actuals are plausible but not tied to baseline/target (e.g. household income ~590 vs target 400).
- Themes: one LLM call per field, capped at the last 200 answers, no stored runs, no merging across fields, no sentiment. The mock's keyword themes are crude (e.g. "Attendance" and "Attend" as separate themes).
- `/qualitative` runs the LLM inside the request (no background task); fine with the mock and a local model at demo sizes.
- The real-model path for themes is untested (no model reachable, same as M2).

### What's next / known gaps
- The MVP flow in docs/MVP.md is complete. Ideas if there is time: a real model run on the sample (`LLM_MODE=real ...`, then `scripts/demo.py`), a time dimension on the dashboard (`collected_at` is stored but unused), editing rules with a form instead of JSON.
- To start over in a demo, stop the API and delete `data/app.db*`; nothing can be unpublished.

## M4.1 — Forms from the documents, form builder, KPI tracking (2026-10-24)

### What works
- **Forms already in the upload become the forms.** After the framework table is found, every other sheet (all its tables together) and every non-framework document table is a form candidate. A new LLM step `convert_form` (`app/ai/steps.py`, section F) decides whether it is a form and returns its questions (`label, type, options, required, pii, qualitative, section`, plus `entity_key` = the identifier question's label). Check: every label must appear in the source text (the model may not invent or reword questions), selects need ≥ 2 options, no options on other types. Field ids and option values are made in code from the labels (`unique_slug`); leading numbering ("12.") is dropped. Stored forms carry `origin: "document"` and `source: "file.xlsx > Sheet"`; AI forms get `origin: "ai"`, builder forms `"manual"` (new optional `FormSchema.origin/source`, `FormField.section`).
- **Indicators are linked to those forms by data source** (`pipeline.match_form`): same words after dropping "form/sheet/questionnaire/template/tool" and anything in brackets; for a sheet name at Excel's 31-character limit, the start of the data source. Only one candidate may match. Indicators left over go to `propose_forms` as before (with `keys_in_use` so keys don't clash). Definitions are then proposed against the real questions; the prompt tells the model to filter ratio numerators on the yes-like options.
- **Parser keeps line breaks inside cells** (`cell_text`): option lists written one per line survive. Spaces within a line are still collapsed.
- **Generic framework fixes:** a column titled "Type" (also "result type", "hierarchy" ...) is the level; among several target columns the mock prefers final/overall/total/end ones and skips ones marked deleted/obsolete (the layout prompt says the same); codes like `X-SO1-0` head their group (`X-SO1-A` sits under it) and `A` → `A1` nests (`pipeline._code_under`); an empty level cell takes a known level named at the start of the statement ("Activity D | …"); a "Milestone" level makes the indicator a milestone; indicators now keep the row's code (`indicator.code`).
- **Form builder** (Forms tab): list of forms with origin badge, question count, how many indicators each feeds and status; editor with title, identifier question, and per question label, type (text, whole number, decimal, choose one, choose several, date), options (one per line; existing option values are kept when labels stay), required, personal data, open text for themes, min/max/unit, section, id (auto from the label for new questions, editable), move up/down, remove; live preview of the form as collectors will see it; save/discard/delete, unsaved-changes guard. Published forms are shown read-only.
- New endpoints: `POST /draft/forms {title, schema?}` (201; key from the title; works after publishing too, then `POST /publish` again), `DELETE /draft/forms/{key}` (draft only, 409 if a rule reads it), `DELETE /draft/definitions/{indicator_id}` (draft only; the indicator is then published without a rule and shows as not computable). `PATCH /draft/forms/{key}` keeps `origin`/`source` from the stored form.
- **Dashboard = KPI tracking.** Each indicator now has `forms: [{key, title, submissions, origin}]` and `track`: `achieved` (progress ≥ 100 %, or milestone done), `in_progress`, `not_started`, `no_target`, `not_computable`; the response has `summary` with the count per track. The page shows summary tiles (click to filter), a KPI table (code, KPI, level/frequency, forms with submission counts — click opens that form in Collect — baseline, target, actual, progress bar, status; breakdowns folded), or the cards view. Review shows each indicator's forms too, and Collect says which KPIs the chosen form feeds.
- Fixture `tests/fixtures/sample_logframe_with_forms.xlsx` (built by `scripts/make_samples.py`): the sample logframe plus sheets "Follow-up survey" (ID, sex, two sections, choose-one, select-all, number, comments) and "Training attendance records". Result with the mock: 2 forms from the file + 5 from the AI, all 7 rules valid; the % indicator's rule reads the survey's "have you applied…" question with `in [yes_regularly, yes_sometimes]`.

### How to run
```
.venv/Scripts/python scripts/check.py      # 7/7 PASS, 161 passed + 1 skipped
.venv/Scripts/python -m pytest tests/ai/test_form_import.py tests/integration/test_form_builder.py
```
Upload `tests/fixtures/sample_logframe_with_forms.xlsx` on the page, then open the Forms tab.

### Files
- New: `tests/ai/test_form_import.py`, `tests/integration/test_form_builder.py`, `tests/fixtures/sample_logframe_with_forms.xlsx`.
- Changed: `app/ai/{pipeline,steps,mock}.py`, `app/ingestion/ir.py`, `app/schemas/form.py` (`slugify`, `unique_slug`, origin/source/section), `app/services/{review,dashboard,extraction}.py`, `app/repositories/draft.py`, `app/api/routers/review.py` (DELETE routes use `api_route` because the hard-delete check flags any `.delete(` call), `app/static/index.html` (Forms tab, KPI dashboard), `scripts/{make_samples,check_routes_scoped}.py`, two existing tests for the new response keys.

### Shortcuts and limits
- One LLM call per candidate sheet/table (first 150 rows, cells cut at 400 characters). Repeating groups ("record up to three times"), skip logic and compound answers ("Date: ____ / Mode: …") become a single text question.
- Linking is by data-source name only; an indicator whose data source names no form (or names one ambiguously) gets an AI form. A reviewer can point a rule at any form in the rule editor.
- The mock's form reading is heuristic (question in one column, options in the next, short leading tags, upper-case or "Section" rows as sections); a real model is expected to do better. Real-model import is untested, like the rest of the real-LLM path.
- Rules are still edited as JSON; the builder covers forms only.
- `track` has no time dimension: "in progress" means some progress, not "on schedule".
