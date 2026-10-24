# Session 06 — Engine workflow and dashboard

**Kickoff prompt:** `This is session 06 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-05-handoff.md and docs/phases/06-engine-workflow-dashboard.md, then do the start-of-session steps before writing code.`

## Goal
Definitions can be drafted, previewed and approved by humans; values are persisted and kept fresh automatically; the dashboard answers with statuses and reasons.

## Read
PLAN §8.5, §9.3, §9.4, §18 (framework objects, dashboard), §22 phase 4.

## Verify from session 05
`make check`; run the benchmark test; confirm 0006 and 0007 are applied and tables exist.

## Logic items to settle first
L-07 (`not_due` for coarser-frequency indicators, if not settled in 02).

## Scope
1. Definition version endpoints: create draft, preview (computes without saving), approve (runs validator + preview, writes `indicator_field_link`, supersedes previous approved, marks dirty), explain (plain-language rendering of an approved definition).
2. Dirty tracking: the submission/register write paths from sessions 03–04 now mark dirty via `indicator_field_link`; enqueue a deduped `recalculate` job (+30 s). Replace any stubs left earlier.
3. `recalculate` job: dirty indicators × open periods × scopes × breakdowns; one short write transaction per indicator; clears only flags set before start; locked periods untouched; nightly full recalculation scheduled.
4. Manual indicators: dashboard merges `manual_value`; statuses `ok|no_data|not_computable|manual|not_due`; reason strings in plain language.
5. `GET /projects/{id}/dashboard?period=` (per component and whole project, honouring component restriction), `GET /indicators/{id}/values?breakdown=`, `POST /projects/{id}/recalculate`.
6. Wire `verification-gaps` to counted records (session 04 stub).
7. End-to-end integration test: build a project by API → publish form → submit → approve definition → dashboard shows the correct number and breakdowns.

## Out of scope
AI, ingestion.

## Done when
End-to-end test passes; a burst of 100 submissions yields a single recalculation job; locked periods keep their values after new data (test); not-computable cases show reasons; role matrix and route walker green.

## Handoff must include
Dashboard response shape (this is the front-end contract), job names and dedupe keys, how to trigger/inspect recalculation, and the final status/reason catalogue.
