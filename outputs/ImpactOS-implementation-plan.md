# ImpactOS Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking. Native execution is recommended; delegation requires the user's selection.

**Goal:** Build a usable frontend for the documented M&E platform with local sample data and the supplied landing-page design.

**Architecture:** React and TypeScript static application with hash-based routes, shared project/component/period context, schema-driven forms, and a replaceable typed mock service. Persist demo edits in versioned browser storage; derive screen data from one consistent state.

**Tech Stack:** React, TypeScript, Vite, CSS, Vitest, browser automation for interaction checks. Resolve compatible dependency versions from the available runtime at execution time.

**Spec:** [ImpactOS frontend design](./ImpactOS-frontend-design.md)

## Global Constraints

- Frontend only; no backend implementation, API credentials, real AI, or remote data submission.
- Preserve cream #f7f0e5, sand #e7d1b5, orange #f27032, navy #19232d, Arial/Helvetica typography, thin borders, compact radii, and restrained dot-grid accents.
- Use data-defined project structures and framework levels; never hardcode a particular project's business logic.
- Use visible sample-data identification and explicitly simulated processing/analysis.
- Uploaded files retain metadata only; no binary persistence or transmission.
- Dashboard statuses: ok, no_data, not_computable, manual, not_due; missing values are not zero.
- Source and user run instructions live under outputs/impactos-frontend/; intermediate scratch work lives under work/.
- Respect keyboard navigation, labeled controls, dialog focus, reduced motion, responsive layouts, and scoped table overflow.

## Review Focus

1. Unavailable or corrupt browser storage must fall back to usable seeded state (Task 1).
2. A project/component/period switch must never retain another scope's records or stale selection (Task 2).
3. Rejecting a required dependency must block publication even when questions are answered (Task 3).
4. Hidden conditional fields must neither fail required validation nor appear in submitted answers (Task 4).
5. Locked-period edits must be rejected by state operations as well as disabled in the UI (Task 5).

## File structure

All paths below are relative to outputs/impactos-frontend/.

- package.json, index.html, tsconfig.json, vite.config.ts: development, build, and test configuration.
- src/main.tsx, src/App.tsx: application entry and hash-route selection.
- src/styles/tokens.css, src/styles/app.css: landing-derived design tokens and responsive application styles.
- src/domain/types.ts: Project, Component, Period, Indicator, ChangeSet, FormSchema, Submission, Theme, DemoState, and Action types.
- src/domain/fixtures.ts: consistent sample project, components, framework, values, forms, records, themes, and source excerpts.
- src/domain/selectors.ts: scope-aware derived values and lists.
- src/domain/review.ts: dependency validation and local publication rules.
- src/domain/forms.ts: field visibility, validation, answer sanitization, schema editing rules.
- src/data/service.ts, src/data/storage.ts, src/data/Store.tsx: typed local operations, persistence, and React state context.
- src/components/: Shell, Dialog, Drawer, StatusBadge, DataTable, EmptyState, FieldRenderer, and reusable chart primitives.
- src/screens/: Projects, Overview, Framework, Review, Forms, Submissions, Insights, Reports, and Settings.
- src/tests/: storage.test.ts, selectors.test.ts, review.test.ts, forms.test.ts, mutations.test.ts.
- README.md: run/build/test instructions, demo limitations, reset behavior, future integration guide.

## Task 1: Runnable application and durable demo state

**Interfaces:** `createSeedState(): DemoState`; `loadDemoState(storage: Storage | null): DemoState`; `saveDemoState(storage: Storage | null, state: DemoState): void`; `useDemo(): {state: DemoState; dispatch: (action: Action) => void; reset: () => void}`.

- [ ] Inspect available Node/package runtime and applicable local instructions. Create the frontend project and required configurations without changing the remote GitHub repository.
- [ ] Add storage tests asserting fallback for missing, malformed, incompatible-version, and inaccessible storage; assert round-trip preservation of valid local edits.
- [ ] Run `npm test -- src/tests/storage.test.ts`; confirm failure before implementation.
- [ ] Define domain types, coherent fixture relationships, storage schema validation, migration-version fallback, and store operations. Create the recognizable branded shell with sample-data notice and reset action.
- [ ] Run the storage tests and `npm run build`; expect passing tests and successful TypeScript/Vite build.

## Task 2: Scoped navigation, projects, overview, and framework

**Consumes:** Task 1 state/store. **Produces:** `selectIndicators(state: DemoState, scope: Scope): Indicator[]`; `selectSubmissions(state: DemoState, scope: Scope): Submission[]`; `Scope = {projectId: string; componentId: string | null; periodId: string}`.

- [ ] Add selector tests for each scope filter, all-components selection, missing values, and switching to a project without the previously selected component/period.
- [ ] Run `npm test -- src/tests/selectors.test.ts`; confirm failure.
- [ ] Implement selectors, route persistence through URL hashes, responsive shell, project creation/search/switching, dashboard cards and trend charts, results tree, indicator detail, breakdowns, and calculation/source explanations.
- [ ] Verify selectors pass. In the browser, confirm back/forward navigation, scope filters, new-project empty state, and meaningful dashboard links.

## Task 3: Framework upload and review workflow

**Consumes:** state/store and scope. **Produces:** `validateChangeSet(changeSet: ChangeSet): ReviewIssue[]`; `publishChangeSet(state: DemoState, changeSetId: string): DemoState`. Publication returns updated state or throws a user-readable validation error.

- [ ] Add review tests: unanswered blocking question prevents publish; rejected dependency prevents dependent acceptance from publishing; valid accepted/edited suggestions publish once; rejected items remain in history.
- [ ] Run `npm test -- src/tests/review.test.ts`; confirm failure.
- [ ] Implement file selection and metadata preview, explicitly simulated processing, grouped review, sample source excerpts, accept/edit/reject/restore, question answers, reviewer notes, simulated regeneration, validation summary, and local publication.
- [ ] Verify tests pass and browser workflow moves from file selection to review to updated framework. Cancellation and repeated publication must preserve coherent state.

## Task 4: Schema-driven forms and register collection

**Consumes:** FormSchema, fixtures, store. **Produces:** `isFieldVisible(field: FieldSchema, answers: Answers): boolean`; `validateAnswers(schema: FormSchema, answers: Answers): FieldError[]`; `sanitizeAnswers(schema: FormSchema, answers: Answers): Answers`.

- [ ] Add tests for required/optional fields, numeric limits, option membership, hidden required fields, omitted hidden answers, repeated groups, and immutable stable field IDs during label edits.
- [ ] Run `npm test -- src/tests/forms.test.ts`; confirm failure.
- [ ] Implement forms search/status/version filters, draft editing with stable identifiers, publish validation, survey/register previews, and local collection. Render text, numeric, options, date/time, site/entity/record references, notes, groups/repeats, geopoint, and metadata-only file selection.
- [ ] Verify tests pass. In the browser submit a valid survey, reveal/hide a conditional field, and create a register record; confirm records appear in collection views.

## Task 5: Submission review, evidence, manual values, and settings

**Consumes:** shared state, selectors, form validation. **Produces:** `applyAction(state: DemoState, action: Action): DemoState` handling record review/edit, evidence metadata, manual values, period locks, settings, and role-preview visibility.

- [ ] Add mutation tests asserting locked periods reject edits, register edits retain revisions, scope-invalid references are rejected, and resetting restores seeded state.
- [ ] Run `npm test -- src/tests/mutations.test.ts`; confirm failure.
- [ ] Implement searchable/filterable submissions, detail drawers, review notes/status actions, register revision history, evidence metadata/gaps, entity details, manual values, project/component/site settings, period locks, and team/role preview.
- [ ] Verify tests pass; browser-check an edit and its history, evidence metadata attachment, manual entry, and locked-period behavior. Role preview is labeled as a UI demonstration, not authentication.

## Task 6: Insights and reporting

**Consumes:** scoped state/selectors. **Produces:** local theme edits, report preview, CSV download, and print styles.

- [ ] Implement theme selection, supporting excerpts, rename/merge, and explicitly simulated analysis status.
- [ ] Implement reporting-period/component controls, preview from current local indicator values, escaped CSV export, and browser print layout. Escape CSV formula prefixes in text cells.
- [ ] In the browser verify theme changes persist, CSV contains filtered values with correct escaping, and print view omits application navigation.

## Task 7: Complete visual and workflow verification

- [ ] Run `npm test` and `npm run build`; inspect complete output and resolve failures.
- [ ] Browser-check desktop and narrow mobile layouts: sidebar drawer, table scrolling, dialogs/drawers, focus return, visible keyboard focus, error/empty states, reduced motion, and no console errors.
- [ ] Exercise full upload/review/publish and form/submission journeys, reset the demo, and verify a fresh seed is restored. Check persisted state after refresh.
- [ ] Write README instructions and future API adapter mapping against documented /api/v1 concepts, identifying contracts that must be confirmed once the backend exists.
- [ ] Package the source into a user-facing ZIP, open a working preview where available, and report verified features and any remaining limits. Do not claim backend/AI capabilities.

## Self-review

The plan covers all nine staff screen groups in the approved design. Each of the five review-focus risks is assigned a domain test. Shared types, scope selectors, and store operations provide consistent cross-screen behavior. Backend implementation, public portal, real authentication, real file parsing, and server-generated documents remain outside this frontend delivery.
