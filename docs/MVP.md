# MVP scope (hackathon) — THIS FILE OVERRIDES EVERYTHING ELSE

Ignore `docs/phases/`, `_session-protocol.md`, `LOGIC_REVIEW.md` and the old CLAUDE.md rules. Use `docs/plan/BACKEND_IMPLEMENTATION_PLAN.md` only as a reference for: form schema (§7), indicator definition format (§8), compilation ideas (§9.2), parsing (§10), AI steps (§11). Take the simplest version of each.

## The only flow
Upload framework → parse → AI extracts results + indicators → AI proposes forms + calculation rules → human reviews/edits and publishes → fill forms (submit data) → KPIs calculated → dashboard.

## Cut (do NOT build)
Auth/users/roles, organizations, tenancy, components, memberships, audit log, soft-delete triggers, offline sync/idempotency, registers, entity resolution/merge, evidence, manual values, reporting periods/locking, public portal, revisions, reports/docs generation, backups, rate limits, job queue (use a background task or run synchronously with a status field), multi-language/RTL, Docker/ops.

## Keep
- One project at a time (single implicit project; no project_id plumbing needed beyond a `project` table if convenient).
- Python + FastAPI + SQLite (plain `sqlite3`/SQLAlchemy Core, JSON columns). Simple numbered SQL or `create_all` is fine.
- Parsers: xlsx, csv, docx, digital pdf (pdfplumber). Skip OCR, pptx, legacy formats.
- LLM through an OpenAI-compatible client (Qwen via vLLM/Ollama), JSON-schema output, validate with Pydantic, retry with errors. Include a mock LLM mode so everything runs without a model.
- Human review: AI output is a draft; user can edit and publish.
- AI never computes numbers; a deterministic engine does.

## Minimal data model
`project` · `result` (id, parent_id, level_name, code, statement) · `indicator` (id, result_id, code, name, unit, kind, baseline, target, frequency, data_source, status) · `form` (id, key, title, schema JSON, status draft/published) · `indicator_definition` (indicator_id, definition JSON, status draft/approved) · `submission` (id, form_id, data JSON, entity_key nullable, collected_at) · `open_question` (indicator_id, question, answer) · `framework_upload` (files, IR JSON, status).

## Minimal definition format
kinds: `count` (distinct `entity_key` or records), `sum`, `average`, `ratio` (percentage of numerator over denominator), `milestone`. Conditions: field/op/value with all/any. Optional `disaggregate_by` (form fields). Computed on request (no dirty tracking or stored values needed; cache optional).

## API (small)
- `POST /upload` (files) → parse + extract (async or sync with status) · `GET /upload/{id}` status
- `GET /draft` (results, indicators, forms, definitions, open questions) · `PATCH` for edits · `POST /publish`
- `GET /forms/{key}` schema · `POST /forms/{key}/submissions`
- `GET /dashboard` (indicator, baseline, target, actual, breakdowns, status/reason)
- Extra (stretch): `POST /qualitative` themes for open-text fields; `GET /export.csv`.

## Phases (one chat each)
**M1 — Skeleton, data model, upload and parse.** Repo, config, DB, tables above, parsers → IR, upload endpoint, a sample framework fixture (create a synthetic xlsx logframe). Done when: upload of xlsx/docx/pdf/csv returns an IR with tables and text.

**M2 — AI extraction.** LLM client + mock. Steps: map table layout → build results tree and raw indicators in code → normalise indicators (kind, unit, baseline, target, open questions) → propose forms (grouped by data source) → propose indicator definitions linked to form field ids → validate (every definition references real form fields). Done when: synthetic framework produces a complete draft (results, indicators, forms, definitions, open questions) in the DB, with mock and with a real endpoint if available.

**M3 — Review, publish, collect, calculate, dashboard.** Draft edit endpoints, publish, form submission with validation against the schema, engine for the five kinds with breakdowns, dashboard endpoint with status/reason for not-computable indicators, seed script that generates fake submissions. Done when: upload → publish → submit/seed data → dashboard shows correct numbers (tests with hand-computed values).

**M4 — Demo polish (+ stretch).** Minimal front-end or API demo script, demo data, README with the demo flow; stretch: qualitative themes, CSV export. Done when: a clean end-to-end demo can be run from the README in under 5 minutes.

## Working rules
- Keep it small and working. Prefer the simplest thing that demos well.
- Tests only for: parsers, definition validation, engine calculations, and one end-to-end test.
- At the end of each chat, append to `docs/HANDOFF.md`: what works, how to run it, files/endpoints added, shortcuts taken, what the next phase needs to know. At the start of each chat, read it and run the tests.
- No scope creep: if it isn't in the flow above, don't build it.
