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
