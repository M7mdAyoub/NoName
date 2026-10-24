# Session 13 — Hardening and operations

**Kickoff prompt:** `This is session 13 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-12-handoff.md and docs/phases/13-hardening-operations.md, then do the start-of-session steps before writing code.`

## Goal
Backups with proven restore, security review including all public routes, load targets met, and a deployment that brings up a fresh server.

## Read
PLAN §3.5, §3.6, §19, §20.7, §21, §22 phase 9, §23.

## Verify from session 12
`make check`; full end-to-end suite; list of public routes from the handoff matches the OpenAPI spec.

## Logic items to settle first
Review every `open` item left in `LOGIC_REVIEW.md`; each must be resolved or explicitly accepted (`accepted-risk` with reason).

## Scope
1. Nightly `VACUUM INTO` backup, retention (14 daily / 8 weekly / 12 monthly), weekly `integrity_check`, restore script and a tested restore drill.
2. Security review checklist run against code: auth rate limits, refresh reuse, CSRF, upload checks, SQL parameterisation audit (grep + tests), PII exclusion from LLM calls and exports, audit coverage, secrets handling, CORS/HSTS config, all `/public` routes.
3. Load test per §20.7 (50 collectors × batches of 20 while extraction and recalculation run); fix bottlenecks; record numbers.
4. Metrics and alerts hooks (§21.3).
5. Docker Compose (`api`, `worker`, `caddy`, data volume), `.env.example` complete, deployment guide and runbook (backup/restore, rotate secrets, upgrade, move-to-PostgreSQL triggers).
6. Final documentation pass: update `docs/handoff/PROGRESS.md`, produce `docs/ARCHITECTURE_AS_BUILT.md` (what exists vs the plan, deviations, API summary), and a front-end contract note (dashboard, form schema, sync, review APIs).

## Out of scope
New features.

## Done when
Restore drill succeeds; load targets met or deviations documented; security checklist complete with findings fixed or accepted; a fresh-server bring-up follows the guide; no `open` logic-review items remain unexplained.

## Handoff must include
This is the final handoff: as-built summary, operations runbook location, remaining risks, and a recommended order for the front-end and AI model evaluation work.
