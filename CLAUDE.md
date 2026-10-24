# CLAUDE.md — AI-Powered M&E Platform (back-end)

Claude Code reads this file at the start of every session. Keep it short and current.

## What this is
A generic, multi-tenant M&E back-end. An uploaded Results Framework is turned by an open-weight LLM (Qwen) into forms, indicator definitions and a dashboard. **The AI proposes, a human approves, a deterministic engine calculates.**
Stack: Python 3.12, FastAPI, Pydantic v2, SQLite (WAL, STRICT, JSON functions), SQLAlchemy Core (no ORM), plain-SQL migrations, OpenAI-compatible LLM client.

## Where things are
- `docs/plan/` — the three source documents (read-only reference; never edit them).
- `docs/phases/` — one brief per build session (14 sessions, numbered 00–13).
- `docs/handoff/` — `PROGRESS.md`, `DECISIONS.md`, `LOGIC_REVIEW.md`, and one `phase-NN-handoff.md` per finished phase.
- `docs/phases/_session-protocol.md` — **mandatory** start-of-session and end-of-session procedure.

## Non-negotiable invariants
1. No code, table, route or SQL specific to any project or organization. A new project is rows, not code. ENABEL is only an example.
2. Applied migrations are never edited. Every change is a new numbered `.sql` file; `scripts/check_migrations.py` verifies checksums. (A migration not yet applied anywhere may be amended while still unreleased, and the amendment goes in `DECISIONS.md`.)
3. Soft delete only (see L-02 for the exempt table list). The audit log is insert-only.
4. All SQL lives in `app/repositories/` and `app/engine/` (plus migrations). Route handlers never write SQL.
5. Every project-scoped query includes `project_id` via `ProjectScope`; component-restricted members add `component_id IN (…)`. Non-members get 404, never 403.
6. The LLM never produces a published number and has no tools. Its output is schema-validated into suggestions that a human approves.
7. `pii` fields never go to the LLM, to viewer exports or into qualitative quotes.
8. Write transactions are short (`BEGIN IMMEDIATE`). Never hold one across LLM calls, parsing or HTTP.
9. Engine never guesses: ambiguous means `not_computable` with a reason, never a silent zero.
10. Plan deviations are allowed only when recorded in `docs/handoff/DECISIONS.md` with the reason.

## Commands (create in Phase 00 and keep working)
`make dev` · `make test` · `make lint` · `make migrate` · `make check` (lint + types + tests + migration/route checks). `make check` must be green before any phase is declared done.

## Working agreements
- Work in small steps; write tests with the code, not after.
- Ask the user only for decisions that genuinely block you; otherwise pick the proposed resolution, record it, continue.
- Never claim something works without running it. Report real test output and counts in the handoff.
- Commit at meaningful points; tag the finished phase `phase-NN-done`.
- Do not leave the session without writing the handoff (see protocol).
