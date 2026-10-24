# ImpactOS frontend design

Date: 2026-10-24
Status: Proposed for user review

## Brief

Build the staff application UI for the M&E platform documented in M7mdAyoub/NoName. The user explicitly wants the frontend only; backend implementation and real data will come later. Use the visual design supplied in ImpactOS-Website.zip. Success means a coherent, navigable application with working local interactions and a clear path to future API integration.

## Approach

Recommended: a React and TypeScript single-page application, with reusable UI components and a replaceable data service. It supports the documented forms, review workflows, and cross-screen state while keeping deployment static.

Alternatives: buildless HTML and JavaScript would require less setup but make schema-driven forms and shared application state harder to maintain. Building directly against an API would defer the UI until a backend exists and conflicts with the requested frontend-only scope.

## Visual design

Preserve the supplied brand, Arial/Helvetica typography, cream #f7f0e5, sand #e7d1b5, orange #f27032, navy #19232d, fine borders, small uppercase labels, compact corner radii, and restrained dot-grid accents. Use a navy navigation sidebar, cream workspace, sand panels, and orange primary actions. Adapt the landing design to readable tables, forms, and charts. Large scroll animations belong to the existing landing, not routine application screens.

Desktop uses a persistent sidebar, project header, component and reporting-period filters, and a main workspace. Tablet and phone layouts collapse navigation into a drawer and stack panels. Tables scroll within their own containers. Respect reduced motion, keyboard focus, semantic labels, accessible dialogs, and text labels alongside status colors.

## Navigation and screens

1. **Projects:** searchable project cards; create a local sample project; project and component switching. Include a seeded project with multiple components and a new-project empty state.
2. **Overview:** current-period actuals and targets, indicator progress, data collection trends, pending reviews, verification gaps, and recent activity. Filters affect the displayed data. Cards lead to relevant detail screens.
3. **Framework:** expandable results tree using data-defined level names; indicator list and detail drawer; baselines, targets, collection method, approved definition, source references, breakdowns, and calculation explanations. Missing values display reasons rather than zero.
4. **Upload and review:** local file selection, file metadata, and an explicitly simulated processing sequence. Do not claim to parse arbitrary files or run AI. Open a seeded change set grouped into structure, indicators, forms, entity types/breakdowns, and library links. Accept, edit, reject, and restore individual suggestions; answer blocking questions; validate before local sample publication. Source previews are clearly identified sample excerpts. Publication updates the local framework state and retains review history.
5. **Forms and registers:** searchable forms with survey/register mode and version/status labels. Provide schema-driven form preview and local data entry, a draft field editor, and local sample publication. Render documented field types, including groups/repeats, conditional visibility, record/entity references, site, and file selection. Validate required answers, constraints, and options. File selection stores metadata only.
6. **Submissions and evidence:** filterable records, record detail, review status and notes, editable register records with local revision history, evidence metadata, and manual indicator entry. Entity and evidence views are reachable from collection screens.
7. **Insights:** sample themes with counts and source excerpts; selecting a theme reveals supporting responses. Rename/merge themes locally. Analysis actions are explicitly simulated.
8. **Reports:** period and component selection, report preview using local indicator values, browser print, and CSV export of sample indicator data. Do not imply generation of server-produced Word/PDF/XLSX files.
9. **Settings:** editable local project details, component/site lists, reporting periods, and a team/role preview. A role preview adjusts visible actions for review purposes; it provides no security boundary.

The public participant portal and platform-wide organization administration are separate future UI modules. This delivery focuses on the staff journey from framework to collection to results.

## Data and interaction architecture

Keep views, domain types, fixtures, and service operations separate. Use the documentation's organization/project/component hierarchy and domain concepts. Route-level screens share selected project, component, and reporting period. Use URL routes so refresh and browser back work.

Implement a mock service behind typed operations for projects, framework, change sets, forms, submissions, dashboard, themes, and reports. Future HTTP methods map to the documented /api/v1 routes; the backend response contracts still need verification when implemented. No network API calls, credentials, database, or LLM are required now.

Store local demo edits in versioned browser storage, with a visible reset-demo action. Recover gracefully from unavailable or invalid storage. Display a persistent but unobtrusive demo-data label. Uploaded files are not transmitted or retained as binary data. Avoid real personal information in fixtures.

Dashboard statuses include ok, no_data, not_computable, manual, and not_due. Locked periods disable local edits. Block publication while required questions remain unanswered or accepted suggestions have errors. Rejecting a required dependency must surface a validation issue. Show actionable inline errors and loading, empty, and error states. Sample actions must change state or clearly open a preview; no decorative controls masquerading as working features.

## Validation

Run a production build and TypeScript checks. Test the meaningful workflow rules: review publication blockers and dependencies, conditional form validation, filter scoping, locked-period edits, and persistence/reset behavior. Exercise the application in a browser at desktop and mobile sizes, including the upload-to-review-to-publication and form-to-submission journeys. Check navigation, dialogs, keyboard access, overflow, and browser console errors. Document any unavailable verification.

## Delivery

Deliver the frontend source, run instructions, and a preview where available. Preserve the supplied landing assets as the brand reference. Changes to the GitHub repository or implementation of the backend are outside this frontend delivery unless subsequently requested.

## Source references

- https://github.com/M7mdAyoub/NoName/blob/main/docs/plan/Problem%20statement%20and%20solution.md
- https://github.com/M7mdAyoub/NoName/blob/main/docs/plan/BACKEND_IMPLEMENTATION_PLAN.md (roles, schema-driven forms, review/publishing, API reference)
- https://github.com/M7mdAyoub/NoName/blob/main/docs/phases/06-engine-workflow-dashboard.md
- https://github.com/M7mdAyoub/NoName/blob/main/docs/phases/09-ai-pipeline-b-review-publish.md
- Supplied ImpactOS-Website.zip: index.html, style.css, app.js, README.txt
