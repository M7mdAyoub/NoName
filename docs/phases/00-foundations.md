# Session 00 — Foundations

**Kickoff prompt:** `This is session 00 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md and docs/phases/00-foundations.md, then do the start-of-session steps before writing code.`

## Goal
A running skeleton: API + worker + SQLite with correct settings, migration runner, job queue, audit log, health endpoints, CI checks.

## Read (plan sections)
BACKEND_IMPLEMENTATION_PLAN §2, §3, §4, §5.1, §17, §19 (logging/secrets), §20.8, §21.

## Previous phase
None. Create the git repo and the directory layout from §4 (empty modules allowed).

## Logic items to settle first
L-01 (transaction mode, sync handlers), L-02 (hard-delete trigger exempt list).

## Scope
1. `pyproject.toml` (uv), `.env.example` from §21.1, `Makefile` with `dev test lint migrate check`.
2. `app/config.py`, structured JSON logging with `request_id` middleware (header returned).
3. `app/db/connection.py`: PRAGMAs (§3.1), version check ≥ 3.38, `BEGIN IMMEDIATE` helper with retry on `SQLITE_BUSY`, autocommit mode (L-01). `ids.py` for UUIDv7.
4. Migration runner with checksum ledger; migration `0001_foundation.sql` (§5.1). Trigger generator for hard-delete protection using the exempt list from L-02; `scripts/check_migrations.py`.
5. Audit log writer used inside the same transaction as a change (function in repositories layer); mask-pii hook stub (L-13 gets finished in 03).
6. Job queue (`queue.py`), worker process, handler registry, stale-lock requeue, backoff, SSE progress route, a `noop`/`sleep` test job.
7. `/healthz`, `/readyz` (DB check; LLM check stubbed as "not configured").
8. CI-style checks: ruff, mypy, pytest; a test that deleting a business-table row fails; a concurrency test (two writers) proving no `database is locked` under normal load.
9. `scripts/check_routes_scoped.py` skeleton (will be enforced from session 01).

## Out of scope
Users, projects, any domain tables.

## Done when
- `make dev` starts API and worker; a test job runs end to end with progress.
- `make check` green; `check_migrations.py` detects a tampered migration (test).
- Hard delete on a protected table fails; exempt tables are listed in code and docs.
- Concurrency test passes.

## Handoff must include
The exact exempt-table list, the connection/transaction helper API (how repositories open read vs write transactions), the audit writer signature, how to add a migration and a job type, and Makefile target meanings.
