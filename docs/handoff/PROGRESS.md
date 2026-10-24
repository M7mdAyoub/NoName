# Progress

Updated at the end of every session. Read this first.

| Session | Title | Status | Finished | Tag | Tests | Migrations added |
|---|---|---|---|---|---|---|
| 00 | Foundations | done | 2026-10-24 | phase-00-done | 67 passed, 0 failed | 0001 |
| 01 | Tenancy and auth | not started | | | | 0002 |
| 02 | Framework model (manual) | not started | | | | 0003, 0004 |
| 03 | Forms, submissions, sync | not started | | | | 0005 |
| 04 | Entities, registers, evidence, manual values | not started | | | | — |
| 05 | Engine core | not started | | | | 0006, 0007 |
| 06 | Engine workflow and dashboard | not started | | | | — |
| 07 | Document ingestion | not started | | | | — |
| 08 | AI pipeline A (client, steps A–E) | not started | | | | — |
| 09 | AI pipeline B (steps F–K, review, publish) | not started | | | | — |
| 10 | Qualitative analysis | not started | | | | 0008 |
| 11 | Revisions, reports, generated docs | not started | | | | — |
| 12 | Public portal | not started | | | | — |
| 13 | Hardening and operations | not started | | | | — |

## Current state in one paragraph
Session 00 is done. `python scripts/check.py` (the `make check` recipe) is green: ruff, mypy strict, 67 tests, migration/route/hard-delete checks. `scripts/dev.py` (`make dev`) migrates the SQLite database, then runs the FastAPI app (reload, port 8000) and the job worker; a `sleep` test job runs end to end with SSE progress. Built: config, JSON logging with request ids, `Database` with explicit `BEGIN IMMEDIATE` transactions, migration runner with checksum ledger and lock file, hard-delete trigger generator with an exempt list, audit writer, SQLite job queue with retries/stale-lock handling, `/healthz`, `/readyz`. Not built: users, auth, projects, any domain table (session 01 onward). The job routes are unauthenticated until session 01 (L-21). `make` and `uv` are not installed on the dev machine; use the Python commands in the handoff.

## Open blockers for the user
(none blocking). Optional: install `make` and `uv` on the Windows dev machine (see phase-00 handoff §11).
