# Session 04 — Entities, registers, evidence, manual values

**Kickoff prompt:** `This is session 04 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-03-handoff.md and docs/phases/04-entities-registers-evidence.md, then do the start-of-session steps before writing code.`

## Goal
Submissions link to real entities (de-duplicated by hashed identity); register forms support edit history and linked records; evidence and manual values work; devices can fetch a collector bundle.

## Read
PLAN §13.3, §13.4, §13.5, §5.4 (entity tables), §5.5 (links, revisions, evidence, manual_value), §18, §22 phase 3.

## Verify from session 03
`make check`; submit + sync tests pass; migration 0005 contains submission_revision, submission_link, evidence, manual_value (verify by inspecting the DB).

## Logic items to settle first
L-20 (merge validation); review L-04 for entity ids.

## Scope
1. Entity resolution in the submission path: normalise identity fields, HMAC hash, existing match → reuse + `entity_alias`; no match → create; copy `entity_attribute` fields. Raw identity numbers are never stored in `entity`.
2. Duplicate candidate listing; merge endpoint (`merged_into_id`, re-point earlier merges, same project/type check).
3. Registers: list with `list: true` columns, detail with links both ways, `PATCH` with revision capture and link rebuild; surveys remain non-editable.
4. `record_ref` / `entity_ref` validation (target exists, same project, right form) and `submission_link` writes.
5. Evidence endpoints; `verification-gaps` endpoint (needs `indicator.evidence_required`; counted-record logic will be wired to the engine in session 06 — implement the query against form/field links if available, otherwise stub with a clear TODO and record it).
6. Manual values CRUD (period-locked rules: no edit in locked periods).
7. `GET /projects/{id}/collector-bundle` with ETag/304.

## Out of scope
Calculation, public portal.

## Done when
Same national ID submitted twice yields one entity; offline-created entity id is aliased; merge keeps submissions counted once (data-level test); register edit creates a revision and rebuilds links; evidence attach/list works; bundle returns 304 when unchanged; all routes pass the route walker and role matrix.

## Handoff must include
Entity API for the engine (columns it should read), how merged entities are represented, the register record shape, and any stubs left for session 06.
