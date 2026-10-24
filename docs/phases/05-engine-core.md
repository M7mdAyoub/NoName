# Session 05 — Calculation engine core

**Kickoff prompt:** `This is session 05 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-04-handoff.md and docs/phases/05-engine-core.md, then do the start-of-session steps before writing code.`

## Goal
Definition models, validator and SQL compiler that compute every indicator kind correctly against synthetic data, proven by tests before any workflow around it exists.

## Read
PLAN §5.6, §5.7, §8 (all), §9.1, §9.2, §9.4–§9.6, §20.2.

## Verify from session 04
`make check`; entity resolution and merge tests pass; submissions with entities and repeat groups can be created by a test helper.

## Logic items to settle first
L-06 (component scope), L-08 (index dependencies), L-09 (cumulative start), L-12 (public/participant submissions excluded until approved), L-16 (synthetic ENABEL-pattern benchmark), L-19 reuse.

## Scope
1. Migrations `0006_ai_review.sql` (create now; first used in session 09) and `0007_calculation.sql`.
2. `app/engine/definition.py` — Pydantic models for all kinds, blocks, time, `scope` (L-06). Reuse the shared Condition model.
3. Approval validator (§8.5 rules 1–6) as a pure function over the project's published forms; plus `index` cycle check (L-08).
4. `compiler.py` + `dialect.py`: parameterised SQL only; JSON paths built from validated ids; kinds count/sum/average/ratio/milestone/index; repeat groups; `require_in`; `contains`; one-hop `record_ref` conditions; time aggregation period/cumulative/latest; merged-entity resolution; status rules (L-12); component scope; age bins from `derive`.
5. `runner.py` core: compute one indicator for one period to rows including all breakdown levels (total, single-dimension, full cross) with the `unknown` bucket; write nothing yet except through a function that returns rows (persistence in session 06).
6. Golden-SQL snapshot tests and the full set of correctness tests in §20.2, plus the synthetic ENABEL-pattern benchmark (5 indicators with hand-computed expected values).

## Out of scope
Approval endpoints, dirty tracking, recalculation job, dashboard (session 06).

## Done when
Every case in §20.2 passes; the benchmark passes; no SQL string is built from user-supplied text (test that rejects bad ids); the compiler output for each kind is snapshot-tested.

## Handoff must include
The final definition JSON schema (with `scope`), the runner's function signatures, the statuses it returns and reason strings, and a list of any definition constructs deferred.
