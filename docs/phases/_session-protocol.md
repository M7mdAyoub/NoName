# Session Protocol (every phase, every new chat)

Each phase runs in a fresh chat with **no memory** of earlier ones. The repository files are the only memory. This protocol makes sure nothing is lost between sessions.

## A. Start of session (before writing any feature code)

1. **Load context** — read in this order: `CLAUDE.md`, `docs/handoff/PROGRESS.md`, the **previous** `docs/handoff/phase-NN-handoff.md`, `docs/handoff/DECISIONS.md`, the `open` rows of `docs/handoff/LOGIC_REVIEW.md` for this phase, then this phase's brief, then only the plan sections the brief lists.
2. **Verify the previous phase (trust, but check)** — don't assume the handoff is right:
   - run `make check`; record the real pass/fail counts;
   - confirm the migrations listed in the handoff exist and `check_migrations.py` passes;
   - spot-check 3 claims from the handoff (an endpoint, a table, a test) by actually running or reading them;
   - if something is broken or the handoff is wrong: fix it first (small) or, if large, tell the user before continuing. Record it under "Corrections to earlier phases" in your handoff.
3. **Logic check of this phase** — read the plan sections for this phase critically:
   - find contradictions between SQL, JSON examples, endpoints and rules (e.g. a column used but not defined, a rule the schema cannot enforce);
   - settle every `LOGIC_REVIEW` item assigned to this phase;
   - write each decision in `DECISIONS.md` (id `D-nn`, context, decision, consequence) **before** coding.
4. **State the plan** — a short task list (use the task tool) taken from the brief's scope, in build order. If a blocking question remains for the user, ask it now, once, with a recommendation.

## B. During the session
- Build in the brief's order; tests with each piece.
- Anything discovered that affects a later phase: add it to `LOGIC_REVIEW.md` (new `L-xx`, assigned phase) at once, not at the end.
- Stay inside the phase scope. If you must pull work forward or leave work behind, record it.

## C. End of session (mandatory, even if the phase is incomplete)

1. Run `make check`. Do not mark done unless it is green. If not done, say so plainly.
2. Walk the brief's **Done when** list, item by item, with evidence (command run and result).
3. Write `docs/handoff/phase-NN-handoff.md` from `HANDOFF_TEMPLATE.md`. It must be understandable by someone with zero context.
4. Update `PROGRESS.md` (status, date, test counts, migration list, tag).
5. Update `DECISIONS.md` and the `LOGIC_REVIEW.md` Status column.
6. Commit and tag `phase-NN-done` (or `phase-NN-partial` with the remaining work in the handoff).
7. Final reply to the user: 5–10 lines — what's done, what isn't, decisions that need their input, and the exact kickoff prompt for the next phase.

## D. Rules for the handoff file
- Facts, not narrative: file paths, table names, endpoint lists, command lines, numbers.
- Include **how to verify** each claim.
- List every deviation from the plan and why.
- List what the next phase must do first and what it must not assume.
- Never paste secrets. Never rewrite earlier handoffs; append corrections in the new one.
