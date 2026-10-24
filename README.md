# Build kit: AI-powered M&E platform (back-end), 14 Claude Code sessions

## Setup (once)
1. Create the repo folder and copy this kit into it (`CLAUDE.md` at the root, `docs/` beside it).
2. Put your three source files in `docs/plan/` with these names:
   - `Problem statement and solution.md`
   - `BACKEND_IMPLEMENTATION_PLAN.md`
   - `public_result_framework.md`
3. Run `git init` and commit. Open Claude Code in that folder.

## Running a phase
1. Open a **new chat** in Claude Code for each phase.
2. Paste the **Kickoff prompt** found at the top of that phase's file in `docs/phases/`.
3. Claude will read the handoff from the previous phase, verify it by running the checks, review the logic of the new phase, build, test, and then write `docs/handoff/phase-NN-handoff.md`.
4. Before opening the next chat, read the final message and the `Questions for the user` section of the handoff. Answer anything blocking.

## Phase list
| # | Session | Main result |
|---|---|---|
| 00 | Foundations | API, worker, SQLite, migrations, jobs |
| 01 | Tenancy and auth | users, orgs, projects, components, scoping tests |
| 02 | Framework model | manual framework, periods, sites, entity types, breakdowns |
| 03 | Forms and sync | form versions, submissions, idempotent sync, files |
| 04 | Entities and registers | entity resolution, registers, evidence, manual values, bundle |
| 05 | Engine core | definitions, validator, compiler, correctness tests |
| 06 | Engine workflow | approval, recalculation, dashboard |
| 07 | Ingestion | any file → IR |
| 08 | AI pipeline A | LLM client, steps A–E |
| 09 | AI pipeline B | forms, definitions, review, publish |
| 10 | Qualitative | thematic analysis |
| 11 | Revisions and reports | revision diff, reports, generated docs |
| 12 | Public portal | public forms and listings |
| 13 | Hardening and ops | backups, security, load, deployment |

## Things to know
- `docs/handoff/LOGIC_REVIEW.md` lists 20 problems found in the plan, with proposed fixes. Sessions settle them as they go; skim it once before you start.
- Phases 08–10 are built and tested against a **mock LLM**. Real-model quality (extraction recall, theme quality) is measured by **you** running `make ai-eval` against a Qwen endpoint, following the checklist each session leaves in its handoff.
- The phase order differs slightly from the plan (portal before hardening; two big phases split). See `DECISIONS.md` D-00.
- If a session runs out of room, it must still write a `partial` handoff. Start the same phase again in a new chat with the same kickoff prompt.
- The front-end is a separate plan; session 13 leaves a contract note for it.
