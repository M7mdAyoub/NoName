# Decision Log

Append-only. One entry per decision. Phases add entries; nobody deletes them (supersede instead).

Format:
```
## D-nn — <title>  (Phase NN, YYYY-MM-DD)
Context: …
Decision: …
Consequence / what it affects: …
Resolves: L-xx (if any)   Supersedes: D-mm (if any)
```

## D-00 — Kit conventions  (pre-build)
Context: The plan is split into 14 sessions with a file-based handoff.
Decision: Sessions are numbered 00–13. Phase order differs from the plan's section 22 as follows: plan Phase 3 → sessions 03 + 04; plan Phase 4 → 05 + 06; plan Phase 6 → 08 + 09; plan Phases 7, 8 → 10, 11; plan Phase 10 (public portal) now runs before Phase 9 (hardening), as sessions 12 and 13.
Consequence: Migrations are created in these sessions: 0001 (00), 0002 (01), 0003 + 0004 (02), 0005 (03; includes registers, evidence and manual-value tables used by 04), 0006 + 0007 (05), 0008 (10).

## D-01 — Code lives at the repository root; tooling is Windows-safe  (Phase 00, 2026-10-24)
Context: The plan's §4 shows a `backend/` folder, but CLAUDE.md names `app/`, `scripts/` and `make` targets at the repo root next to `docs/`. The dev machine is Windows with Python 3.13 and has neither `make` nor `uv`.
Decision: `app/`, `migrations/`, `scripts/`, `tests/`, `pyproject.toml` and `Makefile` sit at the repo root. Every Makefile target is a one-line call to a Python script or tool (`scripts/check.py`, `scripts/dev.py`, `scripts/migrate.py`), so the logic is cross-platform and testable without `make`. The Makefile uses `RUN ?= uv run`; `make RUN= <target>` uses an already-activated venv. Dependencies are in `pyproject.toml` with a `dev` extra (`uv sync --extra dev` or `pip install -e ".[dev]"`).
Consequence: `make check` is `python scripts/check.py`. Where `make` is unavailable, run that command directly; the result is identical. `requires-python` stays >=3.12.

## D-02 — Transaction model (resolves L-01)  (Phase 00, 2026-10-24)
Context: SQLAlchemy Core over `sqlite3` lets the driver open transactions implicitly, which conflicts with `BEGIN IMMEDIATE`; async routes over a sync driver would block the event loop.
Decision: Connections are opened with `isolation_level=None` (autocommit) and `check_same_thread=False`; a SQLAlchemy `begin` event issues the SQL named by the connection's `sqlite_begin` execution option (`DEFERRED` or `IMMEDIATE`). `Database` (app/db/connection.py) owns two engines on the same file: a **read** engine (`PRAGMA query_only=ON`, so a write attempted in a read transaction fails loudly instead of upgrading a snapshot into `SQLITE_BUSY_SNAPSHOT`) and a **write** engine. API: `db.read_tx()` and `db.write_tx()` context managers yield a `Connection`; `write_tx` retries only the `BEGIN IMMEDIATE` on `SQLITE_BUSY`; `db.run_write(fn)` retries the whole unit of work and is for idempotent short writes. Route handlers are plain `def` (FastAPI threadpool), one connection per request via dependencies; the worker uses one connection per job step. Only the SSE generator and the request-id middleware are async (the generator reaches the DB through the threadpool). Busy retries are counted in `db.busy_retries` for the metrics in §21.3.
Consequence: Repositories receive a `Connection` and never open or commit transactions themselves. A concurrency test (threads and processes) proves there is no `database is locked` under normal load.
Resolves: L-01

## D-03 — Hard-delete protection classes (resolves L-02)  (Phase 00, 2026-10-24)
Context: Triggers on "every business table" conflict with tables that legitimately delete rows. Also, the plan has log/derived tables without `deleted_at` (`submission_revision`, `ai_run`, `calc_run`, `indicator_value`) that a "has `deleted_at`" rule would leave silently unprotected.
Decision: `app/db/protection.py` is the single source. Every table is in exactly one class: (a) **soft-delete** = has a `deleted_at` column and is not exempt → `<table>_no_delete` trigger; (b) **history** (no `deleted_at`, never deleted) → same trigger: `submission_revision`, `ai_run`, `calc_run`; (c) **exempt** (rows may be hard-deleted): `membership_component`, `indicator_field_link`, `qual_coding`, `indicator_dirty`, `refresh_token`, `password_reset`, `entity_alias`, `job`; (d) **system**, protected by their own migration SQL: `schema_migrations`, `audit_log`. A table in none of these classes fails the check ("unclassified"), so a later session must decide for each new table; `indicator_value` is deliberately left unclassified (L-22, phase 05). After every applied migration the runner (re)creates the triggers for (a) and (b) with `CREATE TRIGGER IF NOT EXISTS`; `verify_triggers` is used by `check_migrations.py` and `/readyz`. The no-hard-DELETE source scan (`scripts/check_no_hard_delete.py`) allows `DELETE FROM` only on class (c) tables.
Consequence: `file` (created in 0001) is protected by the same generator, not by per-migration SQL.
Resolves: L-02

## D-04 — Migration ledger, checksums and line endings  (Phase 00, 2026-10-24)
Context: Git on Windows rewrites line endings (this repo already warns "LF will be replaced by CRLF"), which would change a raw-bytes SHA-256 between checkouts. A ledger inside the database cannot catch an edited migration in CI, where the database is fresh.
Decision: checksums are SHA-256 of the file content with `\r\n` normalised to `\n`; `.gitattributes` pins `*.sql text eol=lf`. Besides the `schema_migrations` ledger, the committed `migrations/checksums.lock` records `version filename sha256`. `scripts/check_migrations.py` fails when a file is missing, renamed, changed, not contiguous (0001, 0002, …) or not registered in the lock; `--update` only appends new files; `--amend N` rewrites one hash and exists solely for the "unreleased migration" exception in CLAUDE.md invariant 2 (the amendment must also be written in this file). When a database exists, the same check runs against its ledger. The runner splits files with `sqlite3.complete_statement` (triggers contain `;`), runs each file in one `BEGIN IMMEDIATE`, re-reads the ledger inside that transaction (API and worker may start together) and writes the ledger row in the same transaction.

## D-05 — Job queue details  (Phase 00, 2026-10-24)
Context: §17 leaves cases open. (1) `ux_job_dedupe` is unique on queued jobs, so re-queueing a retried job while another queued job has the same `dedupe_key` violates the index. (2) A hung handler would be re-queued by the stale-lock sweep forever. (3) A stale job's original worker may still be running and could overwrite a newer attempt.
Decision: (1) when a retry or stale re-queue collides with the unique index, the old job is finished as `cancelled` with `error='superseded by queued duplicate'`. (2) the stale sweep honours `max_attempts`: at the limit the job becomes `failed` ('timed out'). (3) progress and finish statements are guarded by `WHERE id=:id AND status='running' AND locked_by=:worker AND attempts=:attempts`; if no row matches, the handler gets `LostLock` and stops. Handler registry: `@register("type", timeout_s=…)`, with the §17 timeouts for the planned types; `noop` and `sleep` are test jobs. Timestamps are ISO-8601 UTC with milliseconds, so string comparison orders them. Queue functions take an optional `now` for deterministic tests. SSE (`GET /jobs/{id}/events`) is an async generator that polls every 0.5 s with a short read transaction (run in the threadpool), sends heartbeat comments and ends at a terminal status.
Consequence: Scheduled jobs (nightly recalculation, backup, integrity check) are not part of phase 00 (L-23). Job routes are unauthenticated until session 01 (L-21).

## D-06 — Config, logging and request ids  (Phase 00, 2026-10-24)
Context: §21.1 lists the variables; §21.3 requires JSON logs with `request_id`.
Decision: settings use `pydantic-settings` (new dependency, same Pydantic v2 family). Outside `APP_ENV=development|test`, the placeholder `change-me` values for `SECRET_KEY` and `IDENTITY_HMAC_KEY` are refused at startup. The request id is taken from an incoming `X-Request-ID` only if it matches `^[A-Za-z0-9._-]{8,64}$` (log-injection guard); otherwise a UUIDv7 is generated. It is returned in the `X-Request-ID` response header and kept in a `contextvars` variable read by the JSON formatter and the audit writer. The middleware is pure ASGI (not `BaseHTTPMiddleware`) so SSE streaming and contextvars behave.

## D-07 — Audit writer  (Phase 00, 2026-10-24)
Context: §5.1 says the audit row is written in the same transaction as the change; masking of `pii` (L-13) is finished in session 03.
Decision: `app/repositories/audit.py::write_audit(conn, *, action, table_name, row_id=None, user_id=None, project_id=None, before=None, after=None, request_id=None)`. It refuses to run outside a write transaction (`conn.get_execution_options()['sqlite_begin'] == 'IMMEDIATE'`), defaults `request_id` from the context variable, serialises JSON with sorted keys, and passes `before`/`after` through `mask_pii(table_name, data)`, a hook that is the identity function until session 03.

## D-08 — Small deviations from the plan's layout and wording  (Phase 00, 2026-10-24)
Context: Building phase 00 showed places where the plan's literal text conflicts with CLAUDE.md or with how the stack behaves.
Decision:
1. **Job SQL lives in `app/repositories/jobs.py`**, not in `app/jobs/queue.py` (CLAUDE.md invariant 4 allows SQL only in repositories and the engine). `queue.py` is the facade that opens the short transactions; `handlers.py` and `worker.py` contain no SQL.
2. **`/healthz` and `/readyz` are mounted at the root**, outside `/api/v1`, because load balancers and Docker health checks should not depend on the API version. Everything else is under `/api/v1` as §18 says.
3. **`POST /api/v1/dev/jobs`** (enqueue `noop`, `sleep` or `fail`) exists only when `APP_ENV` is `development` or `test`; it is what lets `make dev` run a test job without a CLI. It is not mounted in any other environment (tested).
4. **WAL switch retry.** Switching a new database file to WAL needs a lock that SQLite's busy handler does not wait for; eight processes starting at once failed with `database is locked` (found by the migration race test). `Database` now sets `busy_timeout` first and retries `PRAGMA journal_mode = WAL` itself for up to twice the busy timeout. This matters because `make dev` and production start the API and worker together.
5. **Pool sizes**: read engine 20 + 40 overflow (FastAPI's threadpool has 40 threads and each request holds a read connection), write engine 5 + 10.
6. **`check_routes_scoped.py` walks FastAPI's included routers** (recent FastAPI keeps them as lazy wrappers, so `app.routes` alone showed zero API routes) and then cross-checks its list against the OpenAPI paths, failing with "guard could not inspect …" if it ever sees fewer routes than the framework documents.
7. `app/db/ids.py` also holds the timestamp helpers (`utc_now`, `to_iso`, `from_iso`) instead of a new module.
