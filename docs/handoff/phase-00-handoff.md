# Phase 00 handoff — Foundations

- Date finished: 2026-10-24
- Status: done
- Git tag: phase-00-done
- `make check` result: run as `python scripts/check.py` (identical to the Makefile recipe; `make` is not installed on this machine, see §8). **All 7 steps PASS**: ruff lint, ruff format, mypy strict (38 source files), pytest **67 passed, 0 failed** (1 third-party deprecation warning), `check_migrations.py` ok (1 file), `check_routes_scoped.py` ok (2 expected warnings), `check_no_hard_delete.py` ok. The full suite was run 6 more times in a row and the migration race test 25 times: no failures.

## 1. What was built

- Migrations added: `migrations/0001_foundation.sql` (checksum recorded in `migrations/checksums.lock`; `check_migrations.py` passes).
- Tables created: `schema_migrations`, `audit_log` (+ indexes, insert-only triggers `audit_log_no_update`, `audit_log_no_delete`), `file`, `job` (+ `ix_job_claim`, `ux_job_dedupe`). Generated trigger: `file_no_delete`.
- Modules (path → purpose):
  - `app/config.py` → `Settings` (pydantic-settings) from env / `.env`; `get_settings()` cached. Extra vars beyond §21.1: `LOG_LEVEL`, `SQLITE_BUSY_TIMEOUT_MS`, `SQLITE_BEGIN_RETRIES`, `JOB_POLL_SECONDS`, `JOB_STALE_CHECK_SECONDS`.
  - `app/logging_setup.py` → JSON logging, `request_id_var`, `accept_or_make_request_id`.
  - `app/db/connection.py` → `Database` (two engines, PRAGMAs, transaction helpers). `app/db/ids.py` → `new_id()` (UUIDv7), `utc_now()`, `to_iso`, `from_iso`.
  - `app/db/migrate.py` → discover / split / apply / ledger / lock helpers. `app/db/protection.py` → delete-protection classes and trigger generator.
  - `app/repositories/audit.py` → `write_audit`. `app/repositories/jobs.py` → all job SQL.
  - `app/jobs/queue.py` (facade), `handlers.py` (registry + `noop`/`sleep`/`fail`), `worker.py` (process).
  - `app/api/{middleware,errors,deps}.py`, `app/api/routers/{health,jobs}.py`, `app/main.py` (`create_app`).
  - Empty packages created per plan §4: `app/{auth,services,schemas,engine,ingestion,ai,qualitative,reports,files}`, `tests/{tenancy,engine,ingestion,ai_eval,fixtures}`.
- Endpoints:
  - `GET /healthz` → `{"status":"ok"}` (no auth). `GET /readyz` → 200/503 with `checks`: `database`, `migrations`, `delete_protection`, `llm` (`not_configured` until `LLM_BASE_URL` and `LLM_MODEL_EXTRACT` are set).
  - `GET /api/v1/jobs/{id}` (poll) and `GET /api/v1/jobs/{id}/events` (SSE: `progress` events, final `done`, `: heartbeat` comments). **No auth yet (L-21, session 01).**
  - `POST /api/v1/dev/jobs` body `{"type": "noop"|"sleep"|"fail", "payload": {…}}` → 202 `{"id","created"}`. Mounted only when `APP_ENV` is `development` or `test`.
- Jobs: `noop`, `sleep` (`{"seconds","steps"}`, reports progress per step), `fail` (`{"until_attempt": n}`).
- Make targets / scripts: see "Makefile targets" below.

### The exact hard-delete classes (`app/db/protection.py`, also D-03)
| Class | Tables | Behaviour |
|---|---|---|
| soft-delete (default) | any table with a `deleted_at` column not listed below; today only `file` | `<table>_no_delete` trigger → `RAISE(ABORT, 'hard delete forbidden; set deleted_at')` |
| HISTORY (no `deleted_at`, never deleted) | `submission_revision`, `ai_run`, `calc_run` | same trigger |
| **EXEMPT** (hard delete allowed) | `membership_component`, `indicator_field_link`, `qual_coding`, `indicator_dirty`, `refresh_token`, `password_reset`, `entity_alias`, `job` | none |
| SYSTEM | `schema_migrations`, `audit_log` | `audit_log` has its own insert-only triggers in 0001 |
| unclassified | anything else without `deleted_at` (e.g. `indicator_value`, L-22) | **the migration fails** with the table name |

The no-hard-DELETE source scan (`scripts/check_no_hard_delete.py`) allows `DELETE FROM` in `app/` only for the EXEMPT tables and rejects SQLAlchemy `delete()`.

### Connection / transaction API (how repositories open transactions)
```python
db = Database(path, busy_timeout_ms=5000, begin_retries=5)   # app.state.db in the API; one per worker process

with db.read_tx() as conn:       # BEGIN DEFERRED, PRAGMA query_only=ON, always rolled back. Writing raises "readonly database".
    conn.execute(text("SELECT ..."), {...})
with db.write_tx() as conn:      # BEGIN IMMEDIATE ... COMMIT; ROLLBACK on any exception. Only acquiring the lock is retried on SQLITE_BUSY.
    conn.execute(text("INSERT ..."), {...})
    write_audit(conn, ...)
db.run_write(lambda conn: ..., retries=None)   # retries the WHOLE unit if SQLite reports BUSY; the unit must be repeatable
db.busy_retries                  # counter for metrics;  db.ping(); db.close()   # close runs PRAGMA optimize
```
Rules: repositories take a `Connection` and never begin/commit; route handlers are `def` (not `async`); `ReadConn` dependency (`app/api/deps.py`) gives a read connection per request; **writes call `db.write_tx()` in the service**, never inside a dependency; no LLM / HTTP / parsing inside either block.

### Audit writer
```python
write_audit(conn, *, action: str, table_name: str, row_id: str | None = None, user_id: str | None = None,
            project_id: str | None = None, before: dict | None = None, after: dict | None = None,
            request_id: str | None = None) -> int          # app/repositories/audit.py
```
Raises `RuntimeError` unless `conn` is inside `db.write_tx()`. `request_id` defaults to the current request's id. JSON is stored with sorted keys. `before`/`after` pass through `mask_pii(table_name, data)`; install the real masker with `audit.set_pii_masker(fn)` (identity until session 03, L-13).

### How to add a migration
1. Create `migrations/NNNN_name.sql` (next number, no gaps; lowercase name). Plain SQL, `STRICT` tables, `<std>` columns written out. Do **not** write `_no_delete` triggers.
2. Classify every new table that has no `deleted_at` in `app/db/protection.py` (EXEMPT or HISTORY) and record why in `DECISIONS.md`; otherwise `make migrate` fails naming the table.
3. `python scripts/check_migrations.py --update` registers the file in `migrations/checksums.lock`; commit both.
4. Never edit an applied file. For a file that has never been applied anywhere: edit it, run `python scripts/check_migrations.py --amend N`, and write the amendment in `DECISIONS.md`.

### How to add a job type
In a module imported by `app/jobs/worker.py` (add the import to `app/jobs/handlers.py` or `worker.py`; there is no auto-discovery yet):
```python
@register("my_type", timeout_s=300)
def my_type(ctx: JobContext) -> dict | None:   # ctx.payload, ctx.project_id, ctx.attempts, ctx.progress(0.5, "note")
    ...
```
Enqueue with `queue.enqueue(db, "my_type", {...}, project_id=..., dedupe_key="recalc:<id>")`. Handlers run with no transaction open and must be idempotent. `ctx.progress` raises `LostLock` if the job was re-queued; let it propagate.

### Makefile targets (each is one line over a Python script, D-01)
| Target | Runs | Meaning |
|---|---|---|
| `make dev` | `python scripts/dev.py` | migrate, then API with reload on 127.0.0.1:8000 and the worker; Ctrl+C stops both (kills the process tree on Windows) |
| `make test` | `scripts/check.py test` | pytest only |
| `make lint` | `scripts/check.py lint` | ruff check, ruff format --check, mypy |
| `make migrate` | `scripts/migrate.py` | apply pending migrations to `DATABASE_PATH` |
| `make check` | `scripts/check.py` | lint + types + pytest + `check_migrations` + `check_routes_scoped` + `check_no_hard_delete` |
`RUN ?= uv run`; use `make RUN= <target>` inside an activated venv.

## 2. How to verify (commands the next session can run)
```
python -m venv .venv && .venv/Scripts/python -m pip install -e ".[dev]"   → installs (or: uv sync --extra dev)
.venv/Scripts/python scripts/check.py                                     → 7 PASS lines, "67 passed"
.venv/Scripts/python scripts/check_migrations.py --db NONE.db             → "migrations ok (1 files)"
.venv/Scripts/python scripts/dev.py   (then, in another shell)
   POST http://127.0.0.1:8000/api/v1/dev/jobs {"type":"sleep","payload":{"seconds":2,"steps":4}}  → 202 {"id": …}
   GET  http://127.0.0.1:8000/api/v1/jobs/<id>/events → progress 0.25, 0.5, 0.75, 1.0, then "event: done" with status succeeded
   GET  http://127.0.0.1:8000/readyz → 200 {"database":"ok","migrations":"ok","delete_protection":"ok","llm":"not_configured"}
```

## 3. Done-when checklist (from the phase brief)
| Item | Evidence |
|---|---|
| `make dev` starts API and worker; a test job runs end to end with progress | Ran `scripts/dev.py` (the `make dev` recipe): migration applied, API and worker started, `sleep` job streamed `queued → running 0.0 → 0.25 → 0.5 → 0.75 → succeeded 1.0` over SSE, `GET /jobs/{id}` showed `result {"slept":2.0,"steps":4}`. Automated version: `tests/integration/test_api.py::test_job_runs_end_to_end_with_progress_and_sse` |
| `make check` green | `scripts/check.py`: 7/7 PASS, 67 tests passed (see header) |
| `check_migrations.py` detects a tampered migration (test) | `test_migrations.py::test_tampered_migration_is_detected_by_the_lock`, `…_by_the_database_ledger`, `test_runner_refuses_to_apply_on_top_of_a_changed_migration`, plus renamed / missing / gap / unregistered-file cases |
| Hard delete on a protected table fails; exempt tables listed in code and docs | `test_protection_audit.py::test_hard_delete_of_a_business_table_row_fails`, `test_later_business_tables_get_triggers_automatically` (soft-delete + history tables blocked, exempt allowed). List in `app/db/protection.py` and the table above; pinned by `test_exempt_and_protected_lists_are_consistent` |
| Concurrency test passes | `test_concurrency.py`: 4 threads × 60 writes + 2 concurrent readers (snapshot asserts change and audit row atomic), 2 processes × 60 writes, 8 threads sharing one `Database`, reader not blocked by an open writer. Zero `database is locked`. Also `test_connection.py` busy-retry tests |
| Scope items 1–9 | config/logging/request-id: `test_basics.py`, `test_api.py`; PRAGMAs and ≥3.38 check: `test_connection.py` (SQLite here is 3.49.1); audit: `test_protection_audit.py`; queue, backoff, stale locks: `test_jobs.py`; `/healthz`, `/readyz`: `test_api.py`; routes check skeleton: `test_check_scripts.py` |

## 4. Deviations from the plan
| Plan reference | What changed | Why | Decision id |
|---|---|---|---|
| §4 layout (`backend/…`) | code at repo root | CLAUDE.md names root paths | D-01 |
| §2 tooling (uv, make) | Makefile delegates to Python scripts; `RUN ?= uv run` | neither is installed here; logic must be testable | D-01 |
| §4 `jobs/queue.py` holds queue SQL | SQL in `repositories/jobs.py` | invariant 4 | D-08 |
| §18 "all routes under /api/v1" | `/healthz`, `/readyz` at root | probes should not be versioned | D-08 |
| §17 | dedupe collision on retry → `cancelled`; stale sweep honours `max_attempts`; lock-guarded progress/finish | otherwise duplicate-key errors, infinite re-queue, double writers | D-05 |
| §5.1 "runner generates triggers for later migrations" | generator also covers `file` (0001) and no-`deleted_at` history tables | tables created in 0001 and history tables were unprotected | D-03 |
| §3.1 PRAGMA order | `busy_timeout` first and WAL switch retried in code | start-up race found by test | D-08 |
| Extra dependency | `pydantic-settings` | settings loading | D-06 |
| Extra route | `POST /api/v1/dev/jobs` (dev/test only) | lets `make dev` run a job | D-08 |

## 5. Decisions made (also in DECISIONS.md)
D-01 layout and tooling · D-02 transaction model · D-03 delete-protection classes · D-04 migration checksums/lock/line endings · D-05 job queue details · D-06 config, logging, request ids · D-07 audit writer · D-08 small deviations.

## 6. LOGIC_REVIEW items touched
- L-01: resolved (D-02). L-02: resolved (D-03).
- New: **L-21** (session 01: auth and scoping for the job routes), **L-22** (session 05: classify `indicator_value`), **L-23** (session 13: scheduled jobs).

## 7. Corrections to earlier phases
None (this is the first phase). The kit documents were only extended: `DECISIONS.md` (D-01–D-08) and `LOGIC_REVIEW.md` (L-01, L-02 status; L-21–L-23).

## 8. Known issues and tech debt
- **`make` and `uv` are not installed on this Windows machine**, so the Makefile text itself was not executed. Every recipe is a single `python scripts/…` call and each of those commands was run directly. First thing to do when `make` is available: run `make check` once.
- Job routes are unauthenticated (L-21). `POST /api/v1/dev/jobs` is dev/test only.
- Handlers run inside the worker process; a hung handler cannot be killed, only detected (lock expiry marks the job for retry while the old thread may keep running; its late writes are rejected by `LostLock`).
- SSE polls the database every 0.5 s per open stream (cheap read transaction, no thread held while sleeping). Fine for dozens of watchers; revisit if the portal needs many.
- `pytest` prints a `StarletteDeprecationWarning` about `httpx` (third-party, harmless).
- mypy covers `app/` and `scripts/`; tests are linted but not type-checked.
- Scheduled jobs (nightly recalculation, backup, integrity check) are not built (L-23).

## 9. What the next phase must know
- Interfaces it will call: `Database.read_tx/write_tx/run_write`, `write_audit`, `new_id`, `utc_now`, `queue.enqueue`, `@register`, `create_app`, `Settings`. `app/api/deps.py` has `DbDep`, `ReadConn`, `SettingsDep`.
- Conventions: all timestamps `YYYY-MM-DDTHH:MM:SS.mmmZ` from `utc_now()`; ids from `new_id()`; errors `{"error": {"code","message","details"}}` (raise `ApiError` or `HTTPException`); every response carries `X-Request-ID`; tests use the `db` (migrated tmp database), `empty_db` and `settings` fixtures in `tests/conftest.py`; `scripts/` is importable in tests (e.g. `import check_migrations`).
- Must NOT assume: that routes are protected (nothing is); that `app.routes` lists API routes (use `check_routes_scoped.iter_api_routes`); that a new table may skip classification; that `make` exists on Windows; that SQLAlchemy opens transactions for you (it does not, always use the helpers); that UUID/time helpers live elsewhere than `app/db/ids.py`.

## 10. First actions for the next session (01 Tenancy and auth)
1. Read `PROGRESS.md`, this file, `DECISIONS.md`, open `LOGIC_REVIEW.md` rows for phase 01 (L-03, L-14, **L-21**).
2. Run `python scripts/check.py`; confirm 67 passed.
3. Add `get_project_scope` in `app/auth/scope.py` (the name `scripts/check_routes_scoped.py` looks for), then **remove the two `TEMPORARY_ALLOWLIST` entries** by giving the job routes auth and scoping (L-21).
4. Migration `0002_tenancy_auth.sql`: `refresh_token`, `password_reset`, `membership_component` are already classified EXEMPT; classify anything new that lacks `deleted_at`.

## 11. Questions for the user (blocking / non-blocking)
- Non-blocking: install `make` (e.g. `choco install make`) and `uv` so `make check` can be run as written. Until then use `python scripts/check.py`.
