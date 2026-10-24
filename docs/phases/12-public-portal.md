# Session 12 — Public portal

**Kickoff prompt:** `This is session 12 of the M&E platform build. Follow docs/phases/_session-protocol.md. Read CLAUDE.md, docs/handoff/PROGRESS.md, docs/handoff/phase-11-handoff.md and docs/phases/12-public-portal.md, then do the start-of-session steps before writing code.`

## Goal
Anonymous visitors and participants can see published listings and submit public forms safely, without any path to indicators, PII or other people's data.

## Read
PLAN §13.6, §6 (participant role), §5.5 (`access`, `public_key`, `public_listing`, `is_published`), §18 (public routes), §19, §22 phase 10 (moved before hardening).

## Verify from session 11
`make check`; registers can be published/unpublished (`is_published`); the engine excludes non-approved public/participant submissions (test from session 05).

## Logic items to settle first
L-11 (component required for public forms), L-12 (public submissions need approval before counting).

## Scope
1. `GET /public/{slug}`: open public forms and published register records (only fields marked `public: true`).
2. `POST /public/forms/{public_key}/submissions`: no login, per-IP rate limits, honeypot, size limits; status `submitted`; staff review queue.
3. Participant accounts (`participant` role), `GET /public/me/submissions`.
4. Form validator additions: `public: true` field flag; public forms need a component; PII fields never public.
5. Route-walker extension: every `/public` route proven to expose no indicator data, no `pii`, no cross-component records.
6. Abuse tests: oversized body, repeated posts, unpublished record access, guessing `public_key`.

## Out of scope
Front-end pages.

## Done when
Anonymous flow works end to end; a participant sees only their own applications; abuse tests pass; the walker confirms no indicator/pii reachable publicly; approved public submissions begin counting only after approval (integration test).

## Handoff must include
Public route list, rate-limit settings and where they are configured, and the attack surface notes session 13 must review.
