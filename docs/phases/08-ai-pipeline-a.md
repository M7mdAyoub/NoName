# Session 08 — AI pipeline A: client and steps A–E

**Kickoff prompt:** `This is session 08 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-07-handoff.md and docs/phases/08-ai-pipeline-a.md, then do the start-of-session steps before writing code.`

## Goal
An LLM client with structured output, validation retries and logging, plus pipeline steps A–E producing normalised raw structure (levels, results, indicators with targets/baselines and open questions) from an IR.

## Read
PLAN §11.1, §11.2, §11.3 (steps A–E and the large-document note), §11.5, §5.6 (ai_run), §20.6, §21.1.

## Verify from session 07
`make check`; golden IR snapshots pass; upload → parse job works.

## Logic items to settle first
L-15 (mock LLM and recorded fixtures; real-model evaluation is user-run).

## Scope
1. `app/ai/client.py`: OpenAI-compatible client, JSON-schema response format, validate-then-retry-with-feedback (max 3), concurrency semaphore, per-step model selection, `ai_run` logging with raw output file. A `MockLLM` that serves recorded/scripted responses keyed by prompt id for tests.
2. Prompt templates under `app/ai/prompts/<step>@v<n>.md` with the structure in §11.2; document content delimited as data.
3. Steps: B locate (file roles, several frameworks → components), C map layout (orientation, column roles, wide per-period columns, level markers), D build structure **in code** from the mapping (with narrative fallback), E normalise indicators (kind, unit, baseline, targets, disaggregation mentions, confidence, open questions).
4. Intermediate "extraction result" Pydantic models (not yet persisted as suggestions; session 09 packages them).
5. Evaluation harness skeleton `make ai-eval`: labelled expected outputs for the synthetic fixtures, recall/precision on indicators, level placement, baseline/target accuracy. It runs against the mock by default and against a real endpoint when configured.
6. Tests with the mock for every step, including malformed model output → retry → fallback to a validation error plus open question (never a silent drop).

## Out of scope
Forms, definitions, suggestions persistence, review.

## Done when
All steps pass their mock-based tests on every synthetic fixture shape; `make ai-eval` runs and reports metrics on the mock; invalid output never escapes the step; a short **user-run checklist** for testing with a real Qwen endpoint is written into the handoff.

## Handoff must include
Step input/output models, prompt ids and versions, the mock-fixture format, how to point the client at vLLM/Ollama, and any prompt weaknesses seen.
