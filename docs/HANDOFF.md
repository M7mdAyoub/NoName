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
