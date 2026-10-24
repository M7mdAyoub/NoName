# Session 10 — Qualitative analysis

**Kickoff prompt:** `This is session 10 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-09-handoff.md and docs/phases/10-qualitative.md, then do the start-of-session steps before writing code.`

## Goal
Thematic analysis of open-text responses: selection with PII protection, coding, consolidation, assignment with verbatim quotes, summaries, editable themes.

## Read
PLAN §14, §5.8 (qualitative tables), §7 (`qualitative`, `pii` flags), §18 (analysis endpoints), §22 phase 7.

## Verify from session 09
`make check`; LLM client and MockLLM usable; the published-project end-to-end test passes.

## Logic items to settle first
L-15 applies (mock-first). Re-check L-13 (pii handling) for free text.

## Scope
1. Migration `0008_qualitative_reports.sql` (§5.8). The `report` table is created now; its use is session 11.
2. `qualitative` job: select (forms, fields, periods, filters), exclude `pii` fields, mask phone/ID/email patterns in free text, batch open coding (~30), consolidate into ≤ N themes, assign 0–3 themes per response with a quote that must be an exact substring (drop otherwise), counts and breakdowns via entity attributes, narrative summaries in the project's default language.
3. Endpoints: create/list/get analyses, rename/merge/split themes (audited); viewers see themes and counts but not quotes (permission test).
4. `kind: qualitative` indicators can point to a saved analysis; dashboard shows its themes (extend session 06 response, record the change).
5. Mock-based tests; multilingual input test (Arabic + English mixed) with the mock.

## Out of scope
Reports export (session 11).

## Done when
Quote-substring check enforced (test with a fabricated quote); PII never appears in the model prompt (test captures prompts); viewer role can't read quotes; theme edits are audited. A user-run real-model checklist for judging theme quality is in the handoff.

## Handoff must include
Analysis JSON shapes, how themes feed the dashboard, masking patterns implemented, and known limits.
