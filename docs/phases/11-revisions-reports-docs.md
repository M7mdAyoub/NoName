# Session 11 — Revisions, reports and generated documentation

**Kickoff prompt:** `This is session 11 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-10-handoff.md and docs/phases/11-revisions-reports-docs.md, then do the start-of-session steps before writing code.`

## Goal
Framework revisions produce reviewable update/create/retire change sets; donor reports export from locked or open periods; indicator sheets and data dictionary are generated.

## Read
PLAN §15, §16, §12, §18 (reports, docs), §22 phase 8.

## Verify from session 10
`make check`; analysis and publish flows pass; the `report` table exists (0008).

## Logic items to settle first
L-17 (content-identical, not byte-identical).

## Scope
1. `revision_diff` job: run steps A–J on the new version, match to existing items (exact code → rapidfuzz ≥ 85 → LLM tie-break via the mock-able client), emit `update`/`create`/`retire` suggestions; forms get new draft versions only; affected definitions get new drafts plus open questions when fields vanish or change type. Change set kind `revision`.
2. Past data stays tied to its form version; locked periods keep their values (tests).
3. Report builder: xlsx (summary, indicator table, per-breakdown sheets, open questions, qualitative) and csv; "provisional" label for open periods; `POST/GET /projects/{id}/reports`, download. Locked-period reports regenerate with identical content.
4. Generated indicator reference sheets and data dictionary (xlsx and Markdown), built from published data only.
5. Tests: revision scenarios (target change, new indicator, removed indicator, renamed field type change); report content vs dashboard numbers; documentation covers every published indicator and field.

## Out of scope
Donor-specific report templates.

## Done when
Revision tests pass; report numbers equal dashboard numbers; locked-period report content identical across two generations; docs cover 100 % of published indicators/fields (test).

## Handoff must include
Report/sheet layouts, revision matching thresholds, and any unmatched-case handling.
