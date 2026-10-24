# Session 09 — AI pipeline B: forms, definitions, review and publish

**Kickoff prompt:** `This is session 09 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-08-handoff.md and docs/phases/09-ai-pipeline-b-review-publish.md, then do the start-of-session steps before writing code.`

## Goal
The full path from uploaded package to published, computable project: steps F–K, change sets, human review, atomic publish.

## Read
PLAN §11.3 (F–K), §11.4, §12, §5.6, §7, §8, §18 (framework and AI review), §22 phase 6.
Note from `docs/plan/public_result_framework.md`: not every indicator needs a survey; the system must choose the collection method (survey, register, existing records, manual) before generating a form.

## Verify from session 08
`make check`; steps A–E tests pass with the mock; `make ai-eval` runs.

## Logic items to settle first
Review L-11 (public forms need a component), L-12 and L-06 as they affect generated definitions.

## Scope
1. Steps F (entity types, breakdowns), G (convert existing questionnaires or generate forms; survey vs register; `record_ref`; public forms; collection-method decision incl. "manual / external data"), H (definitions referencing real form keys and field ids), I (library links with rapidfuzz prefilter), J (deterministic cross-check using the session 05 validator and session 03 form validator), K (package into `change_set`, ordered `ai_suggestion`s with `temp_key`/`depends_on`, `open_question`s with options and `blocking`).
2. `extract_framework` job orchestrating A–K with progress.
3. Review API: get change set grouped, edit (keeps `original_payload`), accept/reject, regenerate with note, answer/dismiss questions (optional regeneration), validate (dry run), discard.
4. `publish`: one write transaction, re-validate, topological apply, create forms + published versions, definitions approved + field links, mark dirty after commit, audit entries, supersede previous document.
5. Integration tests with the mock: upload → extract → review (edit one, reject one) → publish → submit synthetic data → dashboard numbers correct. A multi-framework package yields one component per framework.

## Out of scope
Qualitative analysis, revisions.

## Done when
End-to-end mock test passes; a blocking open question prevents publish; publish is atomic (failure leaves nothing behind — test with an injected error); no schema-invalid output reaches review; `make ai-eval` metrics are recorded on the mock and a **user-run real-model checklist** is in the handoff (L-15). Real recall/precision targets (≥ 90 %) are pending that run and must be reported as "not yet measured", not as passed.

## Handoff must include
Suggestion kinds and payload schemas, temp_key conventions, prompt ids/versions, how revisions (session 11) can reuse steps A–K, and the real-model run instructions.
