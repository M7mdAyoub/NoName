# Session 01 — Tenancy and auth

**Kickoff prompt:** `This is session 01 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-00-handoff.md and docs/phases/01-tenancy-auth.md, then do the start-of-session steps before writing code.`

## Goal
Users can log in; organizations, projects, components and memberships exist; every project route is scoped and tested for cross-project isolation.

## Read
PLAN §3.4, §5.2, §6, §18 (Auth, Organizations and projects), §19, §20.4.

## Verify from session 00
`make check`, migration 0001 applied, job worker runs, hard-delete trigger test passes.

## Logic items to settle first
L-03 (org/platform admin resolution), L-14 (CSRF on cookie refresh).

## Scope
1. Migration `0002_tenancy_auth.sql` (§5.2).
2. Argon2id passwords, JWT access (15 min), rotating refresh tokens with family revocation, logout, password reset (202 always), login rate limiting.
3. `app/auth/permissions.py`: action → roles map (§6), `require(action)` dependency.
4. `ProjectScope` dependency (project id, role, allowed component ids) including the org-admin and platform-admin paths. Non-members get 404.
5. Repositories + routers: organizations, org members, projects (create with a default component), parties, project members, components, member-component restriction (PUT), `/me`.
6. Audit entries for create/update/soft-delete/login.
7. Tests: role matrix generated from the permission map; route walker that calls every project route as a member of another project and expects 404; make `check_routes_scoped.py` fail CI when a project route lacks `ProjectScope`.
8. Admin bootstrap command (`make create-admin`) since there is no public sign-up.

## Out of scope
Frameworks, forms, anything else.

## Done when
Role-matrix and route-walker tests pass; refresh-token reuse revokes the family (test); a component-restricted member can't read the other component (test); cross-project access is 404 everywhere.

## Handoff must include
The `ProjectScope` fields and how repositories receive it, the permission action names (so later phases add rows rather than invent names), the route-walker fixture helpers for new routers, error response shape.
