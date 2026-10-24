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
