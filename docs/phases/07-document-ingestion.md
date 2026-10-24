# Session 07 — Document ingestion

**Kickoff prompt:** `This is session 07 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-06-handoff.md and docs/phases/07-document-ingestion.md, then do the start-of-session steps before writing code.`

## Goal
Any supported file or package becomes a source-referenced intermediate representation (IR), through a `parse_document` job and the framework-document upload endpoints.

## Read
PLAN §10 (all), §5.3 (framework_document tables), §18 (framework upload), §20.5, §22 phase 5.
Also `docs/plan/public_result_framework.md` for public sample documents.

## Verify from session 06
`make check`; job worker handles a job; `framework_document` and `framework_document_file` tables exist.

## Logic items to settle first
None assigned. Check whether LibreOffice and Tesseract exist in the dev environment; if not, record how tests skip or fake them.

## Scope
1. IR models (§10.2) and JSON storage via the `file` table.
2. `convert.py` (LibreOffice headless, sandboxed temp dir, timeout), then parsers: xlsx (merged-cell unmerging, hidden sheets, comments, colour/indent hints, multi-row headers), csv, docx (headings, lists, tables, text boxes), pptx (shapes, connectors, tables), pdf (text, tables, scanned-page detection), image/OCR and vision hook (interface plus Tesseract path; the vision model path may be an interface only).
3. Limits and zip-bomb checks (§10.3); magic-byte type detection.
4. `POST /projects/{id}/framework-documents` (multi-file, optional component and role hint), versioning, `GET` endpoints, parse job with a summary (§10.4).
5. Fixtures: synthetic documents we create ourselves for every shape in §10.1 (4×4 logframe with merged cells, wide yearly-targets table, transposed table, multi-sheet workbook, multi-file package, Word narrative plan, PowerPoint Theory of Change, digital PDF with tables, scanned PDF, `.xls`, Arabic example). **No real beneficiary data.** Public sample PDFs may be tried manually by the user.
6. Golden IR snapshots.

## Out of scope
Any LLM call.

## Done when
Golden snapshots pass for every input type and shape (scanned/legacy ones skip with a clear reason only if the tool is missing, and that is recorded); limits enforced; upload creates a parse job and a summary visible via API.

## Handoff must include
The IR JSON schema as implemented, block id and `ref` conventions (steps A–E depend on them), which parsers were tested vs only stubbed, and the fixture inventory.
