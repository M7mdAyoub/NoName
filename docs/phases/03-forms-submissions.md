# Session 03 — Forms, submissions and sync

**Kickoff prompt:** `This is session 03 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-02-handoff.md and docs/phases/03-forms-submissions.md, then do the start-of-session steps before writing code.`

## Goal
Forms can be authored, validated and published as immutable versions; submissions are validated, stored and synced idempotently with files.

## Read
PLAN §5.5, §7, §8.3 (conditions), §13.1, §13.2, §19 (uploads, PII), §18 (Forms, entities and submissions).

## Verify from session 02
`make check`; migrations 0001–0004; two-component project fixture exists; `breakdown_key` and period helpers import and pass tests.

## Logic items to settle first
L-04 (id collisions across projects), L-05 (`collected_on` in project timezone: amend migration 0005 before applying), L-11 (public form needs component), L-13 (pii masking in audit, `redact`), L-19 (single Condition model).

## Scope
1. Migration `0005_forms_submissions.sql` (§5.5, amended per L-05). It includes registers, links, evidence and manual-value tables, even though their behaviour is session 04.
2. `app/schemas/conditions.py` — the shared `Condition` model and a Python evaluator; `app/schemas/form_schema.py` — field types, properties, validator rules from §7 (id pattern, unique ids, `relevant` only references earlier fields, options, translations warning/error).
3. Form + form_version CRUD; draft edit; publish (validator; immutable trigger test).
4. Submission validator per form version, per-field error shape.
5. `POST /form-versions/{id}/submissions`, `POST /sync/submissions` (batch ≤ 200, idempotent, per-item result `accepted|duplicate|rejected`, L-04 rule), future-date flag.
6. `POST/GET /files` with magic-byte checks, size limits, image compression, permission-checked download; client-supplied ids per L-04.
7. Soft delete of submissions; status changes (flag/approve/reject) with review note; audit with pii masking; `redact` operation.
8. Mark-dirty hook (writes `indicator_dirty` through a function that is a no-op until session 06 creates the table — or guard by table existence; record the choice).

## Out of scope
Entity resolution, registers, evidence endpoints, collector bundle (session 04); calculation (05–06).

## Done when
A form can be published and filled; resending a sync batch creates no duplicates; a cross-project id collision returns `id_conflict`; a published version cannot be altered (trigger); per-field validation errors are correct for each field type (tests); `collected_on` respects timezone (midnight test).

## Handoff must include
Field-type table with validation semantics, the Condition grammar as implemented, sync response shape, the file-id rules, and exactly what 0005 contains versus what session 04 must implement.
