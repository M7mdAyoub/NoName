# Session 02 — Framework model (manual)

**Kickoff prompt:** `This is session 02 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-01-handoff.md and docs/phases/02-framework-model.md, then do the start-of-session steps before writing code.`

## Goal
A project with two components, each with its own framework (levels, results tree, indicators, targets), periods, sites, entity types and breakdowns, enterable and readable through the API with no AI.

## Read
PLAN §5.3, §5.4, §9.5 (breakdown_key format), §18 (Framework objects), §22 phase 2.

## Verify from session 01
`make check`; login works; a restricted member cannot see another component; migrations 0001–0002 verified.

## Logic items to settle first
L-07 (indicator frequency vs period grid), L-10 (identity scope), L-09 (project start date for cumulative: activation rule).

## Scope
1. Migrations `0003_framework.sql` and `0004_entities_disaggregation.sql` (§5.3, §5.4). Note: `framework_document` tables are created now but used in session 07.
2. CRUD (soft delete) for levels, results, indicators, targets, periods, sites, entity types, disaggregations, indicator library (global + org).
3. Pydantic models for translatable text (`{"en": …}`), `breakdown_key` canonicalisation (sorted-key JSON) with tests.
4. Period generator from project dates and frequency; lock/unlock endpoints (M&E lead; audited).
5. `GET /projects/{id}/framework` tree, per component and whole-project, respecting component restriction.
6. Validation: tree has no cycles; results sit at consistent depth/levels; code uniqueness rules; indicator `kind` vs fields; entity-type attribute schema validity; identity_scope rule from L-10.
7. Project activation rule (L-09): needs start date (or periods) before `active`.

## Out of scope
Forms, submissions, calculation.

## Done when
Two-component project built via API and read back as two trees; restricted member sees one; period generation correct for monthly/quarterly/semiannual/annual (tests incl. leap year); all new routes covered by the route walker and role matrix.

## Handoff must include
Table/column facts later sessions rely on (levels per component, how `indicator.kind` maps to definition kinds), the `breakdown_key` helper, the period helper API, and the rule chosen for L-07.
