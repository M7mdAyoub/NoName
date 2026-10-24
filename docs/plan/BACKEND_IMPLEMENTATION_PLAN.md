# Backend Implementation Plan

The detailed build plan for the back-end of the AI-powered M&E platform described in [Problem statement and solution.md](Problem%20statement%20and%20solution.md). The database is **SQLite**.

---

## Contents

1. [Goals and non-goals](#1-goals-and-non-goals)
2. [Technology stack](#2-technology-stack)
3. [SQLite: how we use it safely](#3-sqlite-how-we-use-it-safely)
4. [Repository layout](#4-repository-layout)
5. [Database schema](#5-database-schema)
6. [Roles and permissions](#6-roles-and-permissions)
7. [Form schema format](#7-form-schema-format)
8. [Indicator definition format](#8-indicator-definition-format)
9. [Calculation engine](#9-calculation-engine)
10. [Document ingestion](#10-document-ingestion)
11. [AI extraction pipeline](#11-ai-extraction-pipeline)
12. [Review and publishing](#12-review-and-publishing)
13. [Data collection and offline sync](#13-data-collection-and-offline-sync)
14. [Qualitative analysis](#14-qualitative-analysis)
15. [Framework revisions](#15-framework-revisions)
16. [Reports](#16-reports)
17. [Background jobs](#17-background-jobs)
18. [API reference](#18-api-reference)
19. [Security and privacy](#19-security-and-privacy)
20. [Testing strategy](#20-testing-strategy)
21. [Operations](#21-operations)
22. [Build phases](#22-build-phases)
23. [Risks and mitigations](#23-risks-and-mitigations)
24. [Open decisions](#24-open-decisions)
25. [Worked example: ENABEL as one project](#25-worked-example-enabel-as-one-project)

---

## 1. Goals and non-goals

### Goals
- **One generic back-end for every project.** No table, view, route or line of code is ever written for a specific project or organization. A new project is rows, not code.
- **Many organizations, many projects each.** Any company, NGO or consulting firm is an organization; each runs as many projects as it needs. A project can contain several **components** (municipalities, countries, workstreams), each with its own framework and team.
- **Any framework in, one fixed structure inside.** The AI translates any Results Framework, in any file type, layout, donor template or language (see [10.1](#101-supported-inputs)), into the platform's fixed data model.
- **ENABEL-level output for every project.** What was built by hand for ENABEL (forms, activity registers, calculated indicators with breakdowns, a dashboard that explains missing figures, manual entries, evidence, periodic donor reports, a public portal) is generated for any project. ENABEL is only an example of the output, never a template: see [section 25](#25-worked-example-enabel-as-one-project).
- **The AI proposes, a human approves, the engine calculates.** The LLM never produces a published number. It writes drafts; the M&E lead approves them; a deterministic engine computes every figure.
- **Fully self-hosted.** API, worker, database file and LLM run on infrastructure the operator controls.
- **Field-ready.** Offline collection, idempotent sync, form versions that never break old data.
- **Auditable.** Every AI output, approval, edit and data change is traceable.

### Non-goals (for now)
- The front-end (a separate plan). This plan only defines the API contract it will use.
- Multi-server horizontal scaling. SQLite means one server; [section 3.6](#36-when-to-move-to-postgresql) explains when and how to move.
- Custom code or SQL written by users. Indicator rules use the fixed definition format in [section 8](#8-indicator-definition-format), never free-form SQL.

---

## 2. Technology stack

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.12+** | Best ecosystem for document parsing (Excel, Word, PDF, OCR) and LLM work |
| Web framework | **FastAPI** | Typed request/response models, automatic OpenAPI docs, async-capable |
| Validation | **Pydantic v2** | One set of models validates API input, form schemas, indicator definitions and LLM output |
| Database | **SQLite ≥ 3.38** (JSON functions, `->>` operator, `STRICT` tables, `RETURNING`) | Single file, no server, built-in JSON support |
| Database access | **SQLAlchemy 2.x Core** (no ORM) over the standard `sqlite3` driver | Explicit SQL, bound parameters, easy to keep portable |
| Migrations | **Plain numbered `.sql` files + a small runner** with a checksum ledger | Same discipline as ENABEL: append-only, verifiable |
| LLM client | **`openai` Python SDK** pointed at an OpenAI-compatible endpoint | Works with vLLM, Ollama, LM Studio or a hosted Qwen API by changing one URL |
| LLM serving | **vLLM** (production, GPU) or **Ollama** (development) | Both support JSON-schema-constrained output |
| Excel | **openpyxl** | Merged cells, hidden sheets, formulas, comments |
| Word | **python-docx** | Paragraphs, headings and tables |
| PowerPoint | **python-pptx** | Theory of Change slides: text boxes, tables, shapes and connectors |
| Legacy and OpenDocument files | **LibreOffice (headless)** | Converts `.xls`, `.doc`, `.ppt`, `.ods`, `.odt`, `.odp` to their modern equivalents before parsing |
| PDF | **pdfplumber**; **Tesseract** (or a Qwen vision model) for scanned pages | Text and table extraction; OCR fallback |
| Fuzzy matching | **rapidfuzz** | Matching indicators across framework revisions |
| Passwords | **argon2-cffi** (Argon2id) | Current best practice |
| Tokens | **PyJWT** | Short-lived access tokens + rotating refresh tokens |
| Images | **Pillow** | Compressing evidence photos |
| IDs | **UUIDv7** (time-ordered) via `uuid-utils` | Can be generated offline by clients; sorts by time; good index locality |
| Server | **uvicorn** behind **Caddy** (TLS) | Simple, production-ready |
| Tooling | **uv** (dependencies), **ruff** (lint/format), **mypy** (types), **pytest** | Fast, standard |

---

## 3. SQLite: how we use it safely

SQLite is a good fit for a single-server deployment, but only with the right settings and habits.

### 3.1 Connection settings
Applied on every new connection:

```sql
PRAGMA journal_mode = WAL;        -- readers never block the writer
PRAGMA synchronous = NORMAL;      -- safe with WAL, much faster than FULL
PRAGMA foreign_keys = ON;         -- off by default in SQLite!
PRAGMA busy_timeout = 5000;       -- wait up to 5 s for the write lock instead of failing
PRAGMA temp_store = MEMORY;
PRAGMA cache_size = -64000;       -- ~64 MB page cache
```

On shutdown: `PRAGMA optimize;`. At startup the app checks `sqlite_version() >= 3.38.0` and refuses to start otherwise.

### 3.2 Concurrency rules
SQLite allows **many readers but one writer at a time**. To keep that from becoming a bottleneck:

1. **Write transactions are short.** Begin with `BEGIN IMMEDIATE` (takes the write lock up front, avoiding deadlock-style `SQLITE_BUSY` upgrades), do the writes, commit. Target: under 50 ms.
2. **Never hold a transaction during slow work.** LLM calls, file parsing and HTTP calls happen *outside* transactions. The pattern is always: read → release → do slow work → open a short write transaction → save.
3. **Bulk work is batched.** Sync uploads and recalculations write in batches of a few hundred rows per transaction.
4. **One background worker process** handles all jobs, so heavy writes (AI results, recalculation) are serialized and never compete with each other.
5. **API processes:** 2–4 uvicorn workers. WAL lets them all read in parallel.

### 3.3 Table conventions
- All tables are `STRICT` (real type checking).
- Primary keys: `id TEXT` holding a UUIDv7. Exceptions: `audit_log` and `schema_migrations` use `INTEGER` keys.
- Timestamps: `TEXT` in ISO-8601 UTC (`2026-10-24T09:30:00.000Z`). Dates: `TEXT` `YYYY-MM-DD`.
- JSON: `TEXT` columns with `CHECK (json_valid(col))`.
- Translatable text: a JSON object keyed by language, e.g. `{"en": "Farmers trained", "ar": "مزارعون مدربون"}`.
- Every table has `created_at`, `updated_at` and `deleted_at` (soft delete), except append-only logs.
- **Hard deletes are blocked by triggers** on every business table (see [5.1](#51-foundation-0001)).
- Frequently filtered JSON paths get **expression indexes** or **generated columns** (e.g. `collected_on` on `submission`).
- "Live row" uniqueness uses **partial unique indexes** (`WHERE deleted_at IS NULL`).

### 3.4 Tenancy without row-level security
SQLite has no row-level security, so data separation is enforced in the application:

- Every project-owned table carries `project_id` (directly or through a parent that does).
- **All data access goes through a repository layer.** Each repository function takes a `ProjectScope` (the project ID plus the caller's role), and every query it builds includes `project_id = :project_id`. Route handlers never write SQL.
- A FastAPI dependency resolves the caller's membership for the project in the URL and builds the `ProjectScope`. A route that touches project data cannot be written without it.
- **Component restriction.** A membership can be limited to some components of a project (e.g. a municipality's team sees only its municipality). `ProjectScope` carries the allowed component ids, and repositories add `component_id IN (…)` on every table that has a component. A membership with no component rows sees the whole project.
- **Automated guard tests** (see [20.4](#204-tenancy-and-permission-tests)) call every endpoint as a user from a different project and assert `404`.

### 3.5 Backups and integrity
- **Nightly:** `VACUUM INTO 'backups/app-YYYYMMDD.db'` (a consistent online copy), then compress. Keep 14 daily, 8 weekly, 12 monthly copies.
- **Off-site:** copy backups to a second machine or bucket the operator controls.
- **Weekly:** `PRAGMA integrity_check;` on the latest backup, with an alert if it fails.
- **Monthly restore drill:** restore the latest backup to a scratch environment and run the smoke tests.
- Uploaded files live on disk next to the database (`data/files/`) and are backed up with it.

### 3.6 When to move to PostgreSQL
Move when any of these happens: the platform needs **more than one application server**, sustained **write contention** shows up in metrics (`SQLITE_BUSY` retries, slow sync), or it becomes a **hosted multi-tenant service** for many organizations.

To keep that move cheap:
- All SQL lives in the repository layer and the calculation-engine compiler, never in routes.
- The engine compiler has a **dialect layer** (`json_extract(col, path)` in SQLite ↔ `col #>> path` in PostgreSQL).
- No SQLite-only features outside migrations and the dialect layer.

---

## 4. Repository layout

```
backend/
├── pyproject.toml
├── .env.example
├── Makefile                     # dev, test, lint, migrate, check
├── migrations/
│   ├── 0001_foundation.sql
│   ├── 0002_tenancy_auth.sql
│   ├── 0003_framework.sql
│   ├── 0004_entities_disaggregation.sql
│   ├── 0005_forms_submissions.sql
│   ├── 0006_ai_review.sql
│   ├── 0007_calculation.sql
│   └── 0008_qualitative_reports.sql
├── app/
│   ├── main.py                  # FastAPI app factory, routers, middleware
│   ├── config.py                # settings from environment
│   ├── db/
│   │   ├── connection.py        # engine, PRAGMAs, BEGIN IMMEDIATE helper
│   │   ├── migrate.py           # migration runner + checksum check
│   │   └── ids.py               # UUIDv7
│   ├── auth/                    # passwords, tokens, dependencies, permissions
│   ├── repositories/            # ALL SQL lives here, one module per area
│   ├── services/                # business logic (publish, sync, entity resolution…)
│   ├── api/routers/             # thin HTTP layer, one module per area
│   ├── schemas/                 # Pydantic models: API, form schema, definitions
│   ├── engine/
│   │   ├── definition.py        # indicator definition models + validation
│   │   ├── compiler.py          # definition → parameterized SQL
│   │   ├── dialect.py           # SQLite / PostgreSQL differences
│   │   ├── runner.py            # computes and stores indicator_value
│   │   └── dirty.py             # tracks which indicators need recalculation
│   ├── ingestion/
│   │   ├── ir.py                # document intermediate representation
│   │   ├── convert.py           # LibreOffice conversion of legacy / OpenDocument files
│   │   ├── xlsx.py, docx.py, pptx.py, pdf.py, csv.py
│   │   └── ocr.py, vision.py    # scanned pages and images
│   ├── ai/
│   │   ├── client.py            # OpenAI-compatible client, retries, logging
│   │   ├── prompts/             # versioned prompt templates (.md)
│   │   ├── steps/               # one module per pipeline step
│   │   ├── validators.py        # deterministic cross-checks
│   │   └── pipeline.py          # orchestrates the steps into a change set
│   ├── qualitative/             # theme analysis pipeline
│   ├── reports/                 # xlsx / csv report builders
│   ├── jobs/
│   │   ├── queue.py             # enqueue, claim, complete, fail
│   │   ├── worker.py            # the worker process entry point
│   │   └── handlers.py          # job type → function
│   └── files/                   # storage, hashing, image compression
├── tests/
│   ├── unit/  integration/  tenancy/  engine/  ingestion/  ai_eval/
│   └── fixtures/                # sample frameworks, synthetic datasets
└── scripts/
    ├── check_migrations.py      # every applied file matches its checksum
    ├── check_routes_scoped.py   # every project route uses ProjectScope
    └── seed_demo.py             # demo organization + project + data
```

---

## 5. Database schema

Eight migrations. The SQL below is the target content of each file. (`<std>` stands for the three standard columns: `created_at TEXT NOT NULL, updated_at TEXT NOT NULL, deleted_at TEXT`.)

### 5.1 Foundation (`0001`)

```sql
CREATE TABLE schema_migrations (
  version     INTEGER PRIMARY KEY,
  filename    TEXT NOT NULL,
  sha256      TEXT NOT NULL,
  applied_at  TEXT NOT NULL
) STRICT;

-- Insert-only audit trail, written by the repository layer in the same transaction as the change
CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  at          TEXT NOT NULL,
  user_id     TEXT,
  project_id  TEXT,
  action      TEXT NOT NULL,          -- create | update | soft_delete | restore | publish | login | …
  table_name  TEXT NOT NULL,
  row_id      TEXT,
  before      TEXT CHECK (before IS NULL OR json_valid(before)),
  after       TEXT CHECK (after  IS NULL OR json_valid(after)),
  request_id  TEXT
) STRICT;
CREATE INDEX ix_audit_project_at ON audit_log(project_id, at);

CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is insert-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is insert-only'); END;

CREATE TABLE file (
  id             TEXT PRIMARY KEY,     -- client may supply (offline uploads)
  project_id     TEXT,                 -- NULL only for organization-level files
  sha256         TEXT NOT NULL,
  mime_type      TEXT NOT NULL,
  size_bytes     INTEGER NOT NULL,
  original_name  TEXT NOT NULL,
  storage_path   TEXT NOT NULL,
  uploaded_by    TEXT,
  <std>
) STRICT;

CREATE TABLE job (
  id            TEXT PRIMARY KEY,
  project_id    TEXT,
  type          TEXT NOT NULL,        -- parse_document | extract_framework | recalculate | qualitative | report | revision_diff
  status        TEXT NOT NULL CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  payload       TEXT NOT NULL CHECK (json_valid(payload)),
  result        TEXT CHECK (result IS NULL OR json_valid(result)),
  progress      REAL NOT NULL DEFAULT 0,
  progress_note TEXT,
  attempts      INTEGER NOT NULL DEFAULT 0,
  max_attempts  INTEGER NOT NULL DEFAULT 3,
  run_after     TEXT NOT NULL,
  locked_by     TEXT,
  locked_at     TEXT,
  error         TEXT,
  dedupe_key    TEXT,                 -- e.g. 'recalc:<project_id>' so duplicates collapse
  created_by    TEXT,
  created_at    TEXT NOT NULL,
  finished_at   TEXT
) STRICT;
CREATE INDEX ix_job_claim ON job(status, run_after);
CREATE UNIQUE INDEX ux_job_dedupe ON job(dedupe_key) WHERE status = 'queued';   -- enqueue uses ON CONFLICT DO NOTHING
```

The runner also generates, for every business table created in later migrations:

```sql
CREATE TRIGGER <table>_no_delete BEFORE DELETE ON <table>
BEGIN SELECT RAISE(ABORT, 'hard delete forbidden; set deleted_at'); END;
```

### 5.2 Tenancy and auth (`0002`)

```sql
CREATE TABLE organization (
  id                TEXT PRIMARY KEY,
  name              TEXT NOT NULL,
  slug              TEXT NOT NULL,
  default_language  TEXT NOT NULL DEFAULT 'en',
  default_currency  TEXT,
  settings          TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(settings)),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_org_slug ON organization(slug) WHERE deleted_at IS NULL;

CREATE TABLE app_user (
  id                  TEXT PRIMARY KEY,
  email               TEXT NOT NULL COLLATE NOCASE,
  password_hash       TEXT NOT NULL,
  full_name           TEXT NOT NULL,
  preferred_language  TEXT NOT NULL DEFAULT 'en',
  is_platform_admin   INTEGER NOT NULL DEFAULT 0 CHECK (is_platform_admin IN (0,1)),
  is_active           INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0,1)),
  last_login_at       TEXT,
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_user_email ON app_user(email) WHERE deleted_at IS NULL;

CREATE TABLE refresh_token (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES app_user(id),
  token_hash  TEXT NOT NULL UNIQUE,
  family_id   TEXT NOT NULL,           -- reuse of a rotated token revokes the whole family
  expires_at  TEXT NOT NULL,
  revoked_at  TEXT,
  created_at  TEXT NOT NULL
) STRICT;

CREATE TABLE password_reset (
  id          TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL REFERENCES app_user(id),
  token_hash  TEXT NOT NULL UNIQUE,
  expires_at  TEXT NOT NULL,
  used_at     TEXT,
  created_at  TEXT NOT NULL
) STRICT;

CREATE TABLE org_membership (
  id               TEXT PRIMARY KEY,
  organization_id  TEXT NOT NULL REFERENCES organization(id),
  user_id          TEXT NOT NULL REFERENCES app_user(id),
  role             TEXT NOT NULL CHECK (role IN ('org_admin','org_member')),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_org_member ON org_membership(organization_id, user_id) WHERE deleted_at IS NULL;

CREATE TABLE project (
  id                   TEXT PRIMARY KEY,
  organization_id      TEXT NOT NULL REFERENCES organization(id),   -- owner
  code                 TEXT NOT NULL,
  name                 TEXT NOT NULL CHECK (json_valid(name)),
  description          TEXT CHECK (description IS NULL OR json_valid(description)),
  status               TEXT NOT NULL CHECK (status IN ('setup','active','closed')),
  start_date           TEXT,
  end_date             TEXT,
  reporting_frequency  TEXT NOT NULL CHECK (reporting_frequency IN ('monthly','quarterly','semiannual','annual')),
  languages            TEXT NOT NULL DEFAULT '["en"]' CHECK (json_valid(languages)),
  default_language     TEXT NOT NULL DEFAULT 'en',
  currency             TEXT,
  timezone             TEXT NOT NULL DEFAULT 'UTC',
  settings             TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(settings)),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_project_code ON project(organization_id, code) WHERE deleted_at IS NULL;

-- Clients, donors and partners; they may or may not be organizations on the platform
CREATE TABLE project_party (
  id               TEXT PRIMARY KEY,
  project_id       TEXT NOT NULL REFERENCES project(id),
  organization_id  TEXT REFERENCES organization(id),
  name             TEXT NOT NULL,
  role             TEXT NOT NULL CHECK (role IN ('client','donor','partner','implementer')),
  <std>
) STRICT;

CREATE TABLE project_membership (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES project(id),
  user_id     TEXT NOT NULL REFERENCES app_user(id),
  role        TEXT NOT NULL CHECK (role IN ('project_admin','me_lead','data_manager','enumerator','viewer','participant')),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_project_member ON project_membership(project_id, user_id) WHERE deleted_at IS NULL;

-- A part of a project with its own framework and, optionally, its own team:
-- a municipality, a country, a workstream. Every project has at least one (is_default = 1).
CREATE TABLE component (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES project(id),
  key         TEXT NOT NULL,
  name        TEXT NOT NULL CHECK (json_valid(name)),
  is_default  INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0,1)),
  public_slug TEXT,                                -- e.g. 'sahel-horan' for its public portal
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_component_key ON component(project_id, key) WHERE deleted_at IS NULL;

-- Limits a membership to some components; no rows = the whole project
CREATE TABLE membership_component (
  membership_id  TEXT NOT NULL REFERENCES project_membership(id),
  component_id   TEXT NOT NULL REFERENCES component(id),
  PRIMARY KEY (membership_id, component_id)
) STRICT;
```

### 5.3 Framework (`0003`)

```sql
-- One upload = one "framework package": a single file, or several files that belong together
-- (framework + indicator reference sheets + survey tools + targets workbook)
CREATE TABLE framework_document (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES project(id),
  component_id      TEXT REFERENCES component(id),   -- NULL = let the AI propose components (several frameworks in one package)
  version_no        INTEGER NOT NULL,
  status            TEXT NOT NULL CHECK (status IN
                      ('uploaded','parsing','parsed','extracting','in_review','published','failed','superseded')),
  detected_language TEXT,
  error             TEXT,
  uploaded_by       TEXT NOT NULL REFERENCES app_user(id),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_fwdoc_version ON framework_document(project_id, IFNULL(component_id,''), version_no);

CREATE TABLE framework_document_file (
  id                     TEXT PRIMARY KEY,
  framework_document_id  TEXT NOT NULL REFERENCES framework_document(id),
  file_id                TEXT NOT NULL REFERENCES file(id),      -- the original upload
  converted_file_id      TEXT REFERENCES file(id),               -- e.g. .xls → .xlsx via LibreOffice
  ir_file_id             TEXT REFERENCES file(id),               -- parsed intermediate representation (JSON on disk)
  role_hint              TEXT CHECK (role_hint IN ('framework','indicator_reference','survey_tool','targets','other')),  -- optional, from the uploader
  detected_role          TEXT,                                   -- what the AI decided the file is
  <std>
) STRICT;

CREATE TABLE framework_level (
  id            TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES project(id),
  component_id  TEXT NOT NULL REFERENCES component(id),   -- each component's framework names its own levels
  depth         INTEGER NOT NULL CHECK (depth >= 0),      -- 0 = top (e.g. Impact / Goal)
  name          TEXT NOT NULL CHECK (json_valid(name)),   -- the framework's own word for this level
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_level_depth ON framework_level(component_id, depth) WHERE deleted_at IS NULL;

CREATE TABLE result (
  id           TEXT PRIMARY KEY,
  project_id   TEXT NOT NULL REFERENCES project(id),
  component_id TEXT NOT NULL REFERENCES component(id),
  parent_id    TEXT REFERENCES result(id),
  level_id     TEXT NOT NULL REFERENCES framework_level(id),
  code         TEXT,                                     -- as written in the framework, e.g. "1.2"
  statement    TEXT NOT NULL CHECK (json_valid(statement)),
  assumptions  TEXT CHECK (assumptions IS NULL OR json_valid(assumptions)),
  sort_order   INTEGER NOT NULL DEFAULT 0,
  status       TEXT NOT NULL CHECK (status IN ('active','retired')),
  source_ref   TEXT CHECK (source_ref IS NULL OR json_valid(source_ref)),   -- where in the document it came from
  <std>
) STRICT;
CREATE INDEX ix_result_project ON result(project_id, parent_id);

CREATE TABLE indicator_library (
  id               TEXT PRIMARY KEY,
  organization_id  TEXT REFERENCES organization(id),    -- NULL = global (SDG, donor core sets)
  source           TEXT NOT NULL,                        -- 'SDG' | 'EU_RF' | 'USAID' | 'WB_CRI' | 'custom' …
  code             TEXT NOT NULL,
  name             TEXT NOT NULL CHECK (json_valid(name)),
  unit             TEXT,
  guidance         TEXT CHECK (guidance IS NULL OR json_valid(guidance)),
  <std>
) STRICT;

CREATE TABLE indicator (
  id                    TEXT PRIMARY KEY,
  project_id            TEXT NOT NULL REFERENCES project(id),
  result_id             TEXT NOT NULL REFERENCES result(id),
  code                  TEXT,
  name                  TEXT NOT NULL CHECK (json_valid(name)),
  description           TEXT CHECK (description IS NULL OR json_valid(description)),
  unit                  TEXT,                            -- 'people', '%', 'JOD', 'km' …
  kind                  TEXT NOT NULL CHECK (kind IN
                          ('count','sum','average','ratio','milestone','index','qualitative','manual')),
  direction             TEXT NOT NULL DEFAULT 'increase' CHECK (direction IN ('increase','decrease','maintain')),
  baseline_value        REAL,
  baseline_text         TEXT,                            -- when the baseline is not a number
  baseline_date         TEXT,
  reporting_frequency   TEXT,                            -- NULL = project default
  means_of_verification TEXT CHECK (means_of_verification IS NULL OR json_valid(means_of_verification)),
  data_source           TEXT,
  responsible           TEXT,
  library_indicator_id  TEXT REFERENCES indicator_library(id),
  evidence_required     INTEGER NOT NULL DEFAULT 0 CHECK (evidence_required IN (0,1)),  -- counted records need a supporting file
  status                TEXT NOT NULL CHECK (status IN ('draft','active','retired')),
  source_ref            TEXT CHECK (source_ref IS NULL OR json_valid(source_ref)),
  <std>
) STRICT;
CREATE INDEX ix_indicator_project ON indicator(project_id, status);

CREATE TABLE reporting_period (
  id          TEXT PRIMARY KEY,
  project_id  TEXT NOT NULL REFERENCES project(id),
  label       TEXT NOT NULL,                             -- 'Q1 2027'
  start_date  TEXT NOT NULL,
  end_date    TEXT NOT NULL,                             -- inclusive
  status      TEXT NOT NULL CHECK (status IN ('open','locked')),
  locked_at   TEXT,
  locked_by   TEXT REFERENCES app_user(id),
  <std>,
  CHECK (end_date >= start_date)
) STRICT;
CREATE UNIQUE INDEX ux_period_start ON reporting_period(project_id, start_date) WHERE deleted_at IS NULL;

CREATE TABLE indicator_target (
  id                   TEXT PRIMARY KEY,
  indicator_id         TEXT NOT NULL REFERENCES indicator(id),
  reporting_period_id  TEXT REFERENCES reporting_period(id),   -- NULL = end-of-project target
  breakdown_key        TEXT NOT NULL DEFAULT '',               -- '' = total; else canonical JSON, see 9.5
  target_value         REAL,
  target_text          TEXT,
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_target ON indicator_target(indicator_id, IFNULL(reporting_period_id,''), breakdown_key)
  WHERE deleted_at IS NULL;
```

### 5.4 Entities and breakdowns (`0004`)

```sql
-- What the project counts: Person, Household, Business, School …
CREATE TABLE entity_type (
  id                TEXT PRIMARY KEY,
  project_id        TEXT NOT NULL REFERENCES project(id),
  key               TEXT NOT NULL,                          -- 'person'
  name              TEXT NOT NULL CHECK (json_valid(name)),
  attribute_schema  TEXT NOT NULL CHECK (json_valid(attribute_schema)),   -- fields like sex, date_of_birth, sector
  identity_fields   TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(identity_fields)),  -- e.g. ["national_id"]
  identity_scope    TEXT NOT NULL DEFAULT 'project' CHECK (identity_scope IN ('project','organization')),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_entity_type_key ON entity_type(project_id, key) WHERE deleted_at IS NULL;

CREATE TABLE entity (
  id                    TEXT PRIMARY KEY,                   -- client-generated when created offline
  project_id            TEXT NOT NULL REFERENCES project(id),
  entity_type_id        TEXT NOT NULL REFERENCES entity_type(id),
  identity_hash         TEXT,                               -- HMAC of normalized identity fields, never the raw ID
  display_name          TEXT,
  attributes            TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attributes)),
  merged_into_id        TEXT REFERENCES entity(id),
  created_by            TEXT REFERENCES app_user(id),
  source_submission_id  TEXT,
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_entity_identity ON entity(project_id, entity_type_id, identity_hash)
  WHERE identity_hash IS NOT NULL AND deleted_at IS NULL AND merged_into_id IS NULL;
CREATE INDEX ix_entity_type ON entity(project_id, entity_type_id);

-- Offline-created IDs that turned out to be an existing entity
CREATE TABLE entity_alias (
  alias_id    TEXT PRIMARY KEY,
  entity_id   TEXT NOT NULL REFERENCES entity(id),
  created_at  TEXT NOT NULL
) STRICT;

-- Where data is collected: governorates, villages, health facilities, schools … (any depth)
CREATE TABLE site (
  id            TEXT PRIMARY KEY,
  project_id    TEXT NOT NULL REFERENCES project(id),
  component_id  TEXT REFERENCES component(id),
  parent_id     TEXT REFERENCES site(id),
  key           TEXT NOT NULL,
  name          TEXT NOT NULL CHECK (json_valid(name)),
  kind          TEXT NOT NULL,                              -- the project's own word: 'village', 'facility' …
  location      TEXT CHECK (location IS NULL OR json_valid(location)),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_site_key ON site(project_id, key) WHERE deleted_at IS NULL;

CREATE TABLE disaggregation (
  id           TEXT PRIMARY KEY,
  project_id   TEXT NOT NULL REFERENCES project(id),
  key          TEXT NOT NULL,                               -- 'sex', 'age_group', 'governorate'
  name         TEXT NOT NULL CHECK (json_valid(name)),
  source       TEXT NOT NULL CHECK (source IN ('entity_attribute','submission_field','site','component')),
  source_path  TEXT NOT NULL,                               -- attribute key or form field id
  derive       TEXT CHECK (derive IS NULL OR json_valid(derive)),       -- e.g. age bins from date_of_birth
  value_set    TEXT NOT NULL CHECK (json_valid(value_set)),             -- [{"value":"f","label":{...}}, …]
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_disagg_key ON disaggregation(project_id, key) WHERE deleted_at IS NULL;
```

### 5.5 Forms and submissions (`0005`)

```sql
CREATE TABLE form (
  id              TEXT PRIMARY KEY,
  project_id      TEXT NOT NULL REFERENCES project(id),
  component_id    TEXT REFERENCES component(id),           -- NULL = used by every component
  key             TEXT NOT NULL,                            -- stable machine name, e.g. 'training_attendance'
  title           TEXT NOT NULL CHECK (json_valid(title)),
  purpose         TEXT,
  entity_type_id  TEXT REFERENCES entity_type(id),
  mode            TEXT NOT NULL DEFAULT 'survey' CHECK (mode IN ('survey','register')),
                  -- survey: filled once per interview; register: a list of records that are kept and edited
                  -- over time (training sessions, exhibitions, advisory visits, grants …)
  access          TEXT NOT NULL DEFAULT 'staff' CHECK (access IN ('staff','participant','public')),
                  -- participant/public forms are filled on the public portal (applications, registrations)
  public_key      TEXT,                                     -- unguessable id used in public URLs
  public_listing  INTEGER NOT NULL DEFAULT 0 CHECK (public_listing IN (0,1)),
                  -- register records marked "published" are listed on the portal (e.g. upcoming trainings)
  status          TEXT NOT NULL CHECK (status IN ('draft','active','retired')),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_form_key ON form(project_id, key) WHERE deleted_at IS NULL;

-- Published versions are immutable (enforced by trigger below)
CREATE TABLE form_version (
  id            TEXT PRIMARY KEY,
  form_id       TEXT NOT NULL REFERENCES form(id),
  version       INTEGER NOT NULL,
  schema        TEXT NOT NULL CHECK (json_valid(schema)),    -- see section 7
  status        TEXT NOT NULL CHECK (status IN ('draft','published','retired')),
  change_note   TEXT,
  published_at  TEXT,
  published_by  TEXT REFERENCES app_user(id),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_form_version ON form_version(form_id, version);

CREATE TRIGGER form_version_immutable BEFORE UPDATE OF schema ON form_version
WHEN OLD.status <> 'draft'
BEGIN SELECT RAISE(ABORT, 'published form versions are immutable; create a new version'); END;

CREATE TABLE submission (
  id                TEXT PRIMARY KEY,                       -- client-generated UUIDv7 (idempotent sync)
  project_id        TEXT NOT NULL REFERENCES project(id),
  component_id      TEXT NOT NULL REFERENCES component(id),
  site_id           TEXT REFERENCES site(id),
  form_version_id   TEXT NOT NULL REFERENCES form_version(id),
  entity_id         TEXT REFERENCES entity(id),
  data              TEXT NOT NULL CHECK (json_valid(data)),
  revision          INTEGER NOT NULL DEFAULT 1,             -- register records can be edited; see submission_revision
  is_published      INTEGER NOT NULL DEFAULT 0 CHECK (is_published IN (0,1)),   -- shown on the public portal
  collected_at      TEXT NOT NULL,                          -- when the interview happened (device clock)
  collected_on      TEXT GENERATED ALWAYS AS (substr(collected_at, 1, 10)) STORED,
  received_at       TEXT NOT NULL,                          -- when the server got it
  collected_by      TEXT REFERENCES app_user(id),           -- NULL for anonymous public submissions
  device_id         TEXT,
  location          TEXT CHECK (location IS NULL OR json_valid(location)),
  status            TEXT NOT NULL CHECK (status IN ('submitted','flagged','approved','rejected')),
  review_note       TEXT,
  reviewed_by       TEXT REFERENCES app_user(id),
  <std>
) STRICT;
CREATE INDEX ix_sub_form_date ON submission(project_id, form_version_id, collected_on);
CREATE INDEX ix_sub_entity ON submission(entity_id);
CREATE INDEX ix_sub_collector ON submission(project_id, collected_by, collected_on);
CREATE INDEX ix_sub_component ON submission(component_id, collected_on);

-- Earlier versions of edited register records (the current version stays in submission)
CREATE TABLE submission_revision (
  id             TEXT PRIMARY KEY,
  submission_id  TEXT NOT NULL REFERENCES submission(id),
  revision       INTEGER NOT NULL,
  data           TEXT NOT NULL CHECK (json_valid(data)),
  edited_by      TEXT REFERENCES app_user(id),
  edited_at      TEXT NOT NULL,
  note           TEXT
) STRICT;
CREATE UNIQUE INDEX ux_sub_revision ON submission_revision(submission_id, revision);

-- Links written from record_ref / entity_ref fields (e.g. attendance → training session),
-- kept as rows for fast joins and integrity checks
CREATE TABLE submission_link (
  id                  TEXT PRIMARY KEY,
  project_id          TEXT NOT NULL REFERENCES project(id),
  from_submission_id  TEXT NOT NULL REFERENCES submission(id),
  field_id            TEXT NOT NULL,
  to_submission_id    TEXT REFERENCES submission(id),
  to_entity_id        TEXT REFERENCES entity(id),
  <std>,
  CHECK ((to_submission_id IS NULL) <> (to_entity_id IS NULL))
) STRICT;
CREATE INDEX ix_link_from ON submission_link(from_submission_id);
CREATE INDEX ix_link_to_sub ON submission_link(to_submission_id);

-- Means of verification: files attached to records, indicator periods or manual values
CREATE TABLE evidence (
  id                   TEXT PRIMARY KEY,
  project_id           TEXT NOT NULL REFERENCES project(id),
  file_id              TEXT NOT NULL REFERENCES file(id),
  submission_id        TEXT REFERENCES submission(id),
  indicator_id         TEXT REFERENCES indicator(id),
  reporting_period_id  TEXT REFERENCES reporting_period(id),
  kind                 TEXT,                                -- 'attendance_sheet', 'photo', 'certificate', 'report' …
  note                 TEXT,
  uploaded_by          TEXT REFERENCES app_user(id),
  <std>,
  CHECK (submission_id IS NOT NULL OR indicator_id IS NOT NULL)
) STRICT;
CREATE INDEX ix_evidence_sub ON evidence(submission_id);
CREATE INDEX ix_evidence_ind ON evidence(indicator_id, reporting_period_id);

-- For indicators that have no data-collection form
CREATE TABLE manual_value (
  id                   TEXT PRIMARY KEY,
  indicator_id         TEXT NOT NULL REFERENCES indicator(id),
  reporting_period_id  TEXT NOT NULL REFERENCES reporting_period(id),
  breakdown_key        TEXT NOT NULL DEFAULT '',
  value                REAL,
  value_text           TEXT,
  note                 TEXT,
  evidence_file_id     TEXT REFERENCES file(id),
  entered_by           TEXT NOT NULL REFERENCES app_user(id),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_manual_value ON manual_value(indicator_id, reporting_period_id, breakdown_key)
  WHERE deleted_at IS NULL;
```

### 5.6 AI and review (`0006`)

```sql
-- A batch of proposed changes reviewed and published together
CREATE TABLE change_set (
  id                     TEXT PRIMARY KEY,
  project_id             TEXT NOT NULL REFERENCES project(id),
  framework_document_id  TEXT REFERENCES framework_document(id),
  kind                   TEXT NOT NULL CHECK (kind IN ('initial_extraction','revision','form_generation','manual')),
  status                 TEXT NOT NULL CHECK (status IN ('building','in_review','published','discarded','failed')),
  summary                TEXT CHECK (summary IS NULL OR json_valid(summary)),
  created_by             TEXT REFERENCES app_user(id),
  published_by           TEXT REFERENCES app_user(id),
  published_at           TEXT,
  <std>
) STRICT;

-- One log row per LLM call
CREATE TABLE ai_run (
  id              TEXT PRIMARY KEY,
  job_id          TEXT REFERENCES job(id),
  project_id      TEXT,
  step            TEXT NOT NULL,                  -- 'locate_tables', 'map_columns', 'extract_indicators' …
  model           TEXT NOT NULL,
  prompt_id       TEXT NOT NULL,                  -- e.g. 'extract_indicators@v3'
  input_tokens    INTEGER,
  output_tokens   INTEGER,
  latency_ms      INTEGER,
  attempt         INTEGER NOT NULL DEFAULT 1,
  output_valid    INTEGER NOT NULL CHECK (output_valid IN (0,1)),
  error           TEXT,
  raw_output_file TEXT REFERENCES file(id),       -- kept for debugging and evaluation
  created_at      TEXT NOT NULL
) STRICT;

CREATE TABLE ai_suggestion (
  id                TEXT PRIMARY KEY,
  change_set_id     TEXT NOT NULL REFERENCES change_set(id),
  kind              TEXT NOT NULL CHECK (kind IN
                      ('component','framework_level','result','indicator','indicator_definition','target',
                       'manual_value','entity_type','disaggregation','site','form','reporting_period','library_link')),
  action            TEXT NOT NULL CHECK (action IN ('create','update','retire')),
  target_id         TEXT,                          -- existing row for update/retire
  temp_key          TEXT NOT NULL,                 -- lets suggestions reference each other before publish
  payload           TEXT NOT NULL CHECK (json_valid(payload)),            -- current (possibly edited) content
  original_payload  TEXT NOT NULL CHECK (json_valid(original_payload)),   -- exactly what the AI produced
  depends_on        TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(depends_on)),  -- temp_keys
  status            TEXT NOT NULL CHECK (status IN ('pending','accepted','edited','rejected')),
  confidence        REAL CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
  validation_errors TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(validation_errors)),
  source_ref        TEXT CHECK (source_ref IS NULL OR json_valid(source_ref)),
  ai_run_id         TEXT REFERENCES ai_run(id),
  reviewed_by       TEXT REFERENCES app_user(id),
  reviewed_at       TEXT,
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_suggestion_key ON ai_suggestion(change_set_id, temp_key);

CREATE TABLE open_question (
  id             TEXT PRIMARY KEY,
  project_id     TEXT NOT NULL REFERENCES project(id),
  change_set_id  TEXT REFERENCES change_set(id),
  suggestion_id  TEXT REFERENCES ai_suggestion(id),
  subject_kind   TEXT NOT NULL,                  -- 'indicator', 'form', 'target' …
  subject_id     TEXT,
  question       TEXT NOT NULL,
  options        TEXT CHECK (options IS NULL OR json_valid(options)),   -- suggested answers
  blocking       INTEGER NOT NULL DEFAULT 0 CHECK (blocking IN (0,1)),  -- must be answered before publish
  answer         TEXT,
  status         TEXT NOT NULL CHECK (status IN ('open','answered','dismissed')),
  raised_by      TEXT NOT NULL DEFAULT 'ai',     -- 'ai' or a user id
  answered_by    TEXT REFERENCES app_user(id),
  answered_at    TEXT,
  <std>
) STRICT;
```

### 5.7 Calculation (`0007`)

```sql
-- Versioned calculation rules; exactly one approved version per indicator
CREATE TABLE indicator_definition (
  id             TEXT PRIMARY KEY,
  indicator_id   TEXT NOT NULL REFERENCES indicator(id),
  version        INTEGER NOT NULL,
  definition     TEXT NOT NULL CHECK (json_valid(definition)),   -- see section 8
  status         TEXT NOT NULL CHECK (status IN ('draft','approved','superseded')),
  approved_by    TEXT REFERENCES app_user(id),
  approved_at    TEXT,
  suggestion_id  TEXT REFERENCES ai_suggestion(id),
  <std>
) STRICT;
CREATE UNIQUE INDEX ux_def_version ON indicator_definition(indicator_id, version);
CREATE UNIQUE INDEX ux_def_approved ON indicator_definition(indicator_id) WHERE status = 'approved';

-- Which form fields each approved definition reads (filled on approval; used for impact analysis and dirty tracking)
CREATE TABLE indicator_field_link (
  indicator_definition_id  TEXT NOT NULL REFERENCES indicator_definition(id),
  form_id                  TEXT NOT NULL REFERENCES form(id),
  field_id                 TEXT NOT NULL,
  PRIMARY KEY (indicator_definition_id, form_id, field_id)
) STRICT;
CREATE INDEX ix_field_link_form ON indicator_field_link(form_id);

CREATE TABLE calc_run (
  id           TEXT PRIMARY KEY,
  project_id   TEXT NOT NULL REFERENCES project(id),
  trigger      TEXT NOT NULL,                  -- 'submission', 'definition_approved', 'nightly', 'manual'
  status       TEXT NOT NULL CHECK (status IN ('running','succeeded','failed')),
  stats        TEXT CHECK (stats IS NULL OR json_valid(stats)),
  started_at   TEXT NOT NULL,
  finished_at  TEXT
) STRICT;

CREATE TABLE indicator_value (
  id                       TEXT PRIMARY KEY,
  indicator_id             TEXT NOT NULL REFERENCES indicator(id),
  indicator_definition_id  TEXT REFERENCES indicator_definition(id),
  reporting_period_id      TEXT NOT NULL REFERENCES reporting_period(id),
  scope                    TEXT NOT NULL CHECK (scope IN ('period','cumulative')),
  breakdown_key            TEXT NOT NULL DEFAULT '',
  value                    REAL,
  numerator                REAL,
  denominator              REAL,
  n_records                INTEGER,
  status                   TEXT NOT NULL CHECK (status IN ('ok','no_data','not_computable','manual')),
  reason                   TEXT,                 -- why not computable, shown on the dashboard
  warnings                 TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(warnings)),
  calc_run_id              TEXT REFERENCES calc_run(id),
  computed_at              TEXT NOT NULL
) STRICT;
CREATE UNIQUE INDEX ux_value ON indicator_value(indicator_id, reporting_period_id, scope, breakdown_key);

-- Indicators waiting for recalculation
CREATE TABLE indicator_dirty (
  indicator_id  TEXT PRIMARY KEY REFERENCES indicator(id),
  since         TEXT NOT NULL
) STRICT;
```

### 5.8 Qualitative analysis and reports (`0008`)

```sql
CREATE TABLE qual_analysis (
  id           TEXT PRIMARY KEY,
  project_id   TEXT NOT NULL REFERENCES project(id),
  title        TEXT NOT NULL,
  scope        TEXT NOT NULL CHECK (json_valid(scope)),     -- forms, fields, periods, filters
  status       TEXT NOT NULL CHECK (status IN ('queued','running','done','failed')),
  model        TEXT,
  n_responses  INTEGER,
  summary      TEXT,
  created_by   TEXT NOT NULL REFERENCES app_user(id),
  <std>
) STRICT;

CREATE TABLE qual_theme (
  id           TEXT PRIMARY KEY,
  analysis_id  TEXT NOT NULL REFERENCES qual_analysis(id),
  label        TEXT NOT NULL,
  description  TEXT,
  sentiment    TEXT CHECK (sentiment IN ('positive','negative','mixed','neutral')),
  n_responses  INTEGER NOT NULL DEFAULT 0,
  breakdown    TEXT CHECK (breakdown IS NULL OR json_valid(breakdown)),   -- counts per disaggregation
  edited_by    TEXT REFERENCES app_user(id),                             -- humans can rename/merge
  <std>
) STRICT;

CREATE TABLE qual_coding (
  analysis_id    TEXT NOT NULL REFERENCES qual_analysis(id),
  submission_id  TEXT NOT NULL REFERENCES submission(id),
  field_id       TEXT NOT NULL,
  theme_id       TEXT NOT NULL REFERENCES qual_theme(id),
  quote          TEXT,
  confidence     REAL,
  PRIMARY KEY (analysis_id, submission_id, field_id, theme_id)
) STRICT;

CREATE TABLE report (
  id                   TEXT PRIMARY KEY,
  project_id           TEXT NOT NULL REFERENCES project(id),
  reporting_period_id  TEXT NOT NULL REFERENCES reporting_period(id),
  format               TEXT NOT NULL CHECK (format IN ('xlsx','csv')),
  file_id              TEXT REFERENCES file(id),
  status               TEXT NOT NULL CHECK (status IN ('queued','done','failed')),
  created_by           TEXT NOT NULL REFERENCES app_user(id),
  <std>
) STRICT;
```

### 5.9 How the tables relate

```
organization ─┬─ org_membership ── app_user ── project_membership (── membership_component)
              └─ project (many per organization)
                   ├─ project_party (clients, donors, partners)
                   ├─ component (one or more; each has its own framework)
                   │    ├─ framework_document ── framework_document_file
                   │    │        └─ change_set ── ai_suggestion ── open_question
                   │    └─ framework_level ── result (tree) ── indicator ─┬─ indicator_target
                   │                                                       ├─ indicator_definition ── indicator_field_link
                   │                                                       ├─ indicator_value
                   │                                                       ├─ manual_value
                   │                                                       └─ evidence
                   ├─ site (tree)
                   ├─ reporting_period
                   ├─ entity_type ── entity (── entity_alias)
                   ├─ disaggregation
                   ├─ form ── form_version ── submission ─┬─ submission_revision
                   │                                       ├─ submission_link (→ other records / entities)
                   │                                       └─ evidence
                   └─ qual_analysis ── qual_theme ── qual_coding
```

---

## 6. Roles and permissions

| Action | platform admin | org admin | project admin | M&E lead | data manager | enumerator | viewer |
|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| Manage organizations | ✓ | own | | | | | |
| Manage org members, create projects | ✓ | ✓ | | | | | |
| Project settings, members, parties | ✓ | ✓ | ✓ | | | | |
| Upload framework, run AI extraction | | ✓ | ✓ | ✓ | | | |
| Review/edit AI suggestions, answer questions | | | ✓ | ✓ | | | |
| Publish change sets, approve definitions | | | ✓ | ✓ | | | |
| Edit draft forms | | | ✓ | ✓ | ✓ | | |
| Publish form versions | | | ✓ | ✓ | | | |
| Submit data | | | | ✓ | ✓ | ✓ | |
| See submissions | | | ✓ | ✓ | ✓ | own only | |
| Flag/approve/reject submissions, merge entities | | | | ✓ | ✓ | | |
| Enter manual values | | | | ✓ | ✓ | | |
| Dashboard and indicator values | ✓ | ✓ | ✓ | ✓ | ✓ | | ✓ |
| Run qualitative analysis | | | ✓ | ✓ | | | |
| See themes (no raw quotes) | | | ✓ | ✓ | ✓ | | ✓ |
| Lock periods, generate reports | | | ✓ | ✓ | | | |
| Read audit log | ✓ | ✓ | ✓ | | | | |

Org admins have project-admin rights on every project their organization owns.

**Participants** are people the project serves who have a portal account (e.g. to apply for a training). They can only fill `participant`/`public` forms and see their own submissions and their status ("my applications"). They never see the staff app, other people's data or indicators. Anonymous visitors can fill `public` forms only.

**Component restriction** applies on top of the role: a data manager limited to one component has data-manager rights in that component only ([3.4](#34-tenancy-without-row-level-security)). Permissions are defined once in `app/auth/permissions.py` as a map from action to allowed roles, and checked through a single dependency, `require(action)`.

---

## 7. Form schema format

Stored in `form_version.schema`. The AI produces it, the M&E lead edits it, the front-end renders it, and the back-end validates every submission against it. Inspired by XLSForm (familiar to M&E teams from KoboToolbox and ODK), but stored as JSON.

```json
{
  "schema_version": 1,
  "title": {"en": "Training attendance", "ar": "حضور التدريب"},
  "entity": {
    "entity_type": "person",
    "mode": "select_or_create",
    "identity_fields": ["national_id"]
  },
  "fields": [
    {"id": "national_id", "type": "text", "label": {"en": "National ID"}, "required": true,
     "pii": true, "entity_attribute": "national_id"},
    {"id": "sex", "type": "select_one", "label": {"en": "Sex"}, "required": true,
     "options": [{"value": "female", "label": {"en": "Female"}}, {"value": "male", "label": {"en": "Male"}}],
     "entity_attribute": "sex"},
    {"id": "dob", "type": "date", "label": {"en": "Date of birth"}, "entity_attribute": "date_of_birth"},
    {"id": "session_date", "type": "date", "label": {"en": "Session date"}, "required": true},
    {"id": "completed", "type": "select_one", "label": {"en": "Completed the full course?"},
     "options": [{"value": "yes", "label": {"en": "Yes"}}, {"value": "no", "label": {"en": "No"}}]},
    {"id": "dropout_reason", "type": "text", "label": {"en": "Why not?"}, "qualitative": true,
     "relevant": {"field": "completed", "op": "eq", "value": "no"}},
    {"id": "income", "type": "decimal", "label": {"en": "Monthly income"}, "unit": "JOD",
     "constraints": {"min": 0, "max": 100000}},
    {"id": "children", "type": "repeat", "label": {"en": "Children"}, "fields": [
      {"id": "child_age", "type": "integer", "label": {"en": "Age"}, "constraints": {"min": 0, "max": 18}}
    ]},
    {"id": "photo", "type": "file", "label": {"en": "Attendance sheet photo"}, "accept": ["image/*"]}
  ]
}
```

**Field types:** `text`, `integer`, `decimal`, `select_one`, `select_multiple`, `date`, `datetime`, `geopoint`, `file`, `note` (display only), `group`, `repeat`, `site` (pick a site), `record_ref` (pick a record from a register form, e.g. which training session this attendance belongs to: `"ref_form": "training_session"`), `entity_ref` (pick another entity besides the form's main one, e.g. the business a person works for).

**Survey vs. register forms** (`form.mode`): a **survey** is filled once per interview. A **register** is a list of records that are kept and edited over time (training sessions, exhibitions, advisory visits, grants, partnerships). Registers get list and detail screens; every edit keeps the previous version in `submission_revision`. Survey forms can point at register records with `record_ref`, which is how "attendance at a session" or "follow-up of a grant" is modelled without any project-specific tables.

**Field properties:** `id` (stable, unique within the form), `type`, `label`, `hint`, `required`, `options`, `constraints` (`min`, `max`, `min_length`, `max_length`, `pattern`), `relevant` (show only when a condition holds), `unit`, `pii` (never sent to the LLM, hidden from viewers), `qualitative` (open text included in qualitative analysis), `entity_attribute` (copied to the linked entity), `default`.

**Conditions** use the same grammar as indicator definitions ([8.3](#83-conditions)), so the front-end and the engine share one evaluator design.

**Rules the validator enforces:**
- Field `id`s match `^[a-z][a-z0-9_]{0,62}$` and are unique within the form, including inside groups and repeats.
- **Field ids are stable across versions.** Changing a label keeps the id; changing the meaning of a question requires a new id. Indicator definitions reference ids, never labels.
- `relevant` may only reference fields that appear earlier in the form.
- Every `select_one`/`select_multiple` has at least two options with unique values.
- Every language listed on the project has a label for every field (missing translations are warnings in draft, errors on publish).

**Submission validation:** types, required fields (skipped when `relevant` is false), option values, constraints, and that answers to non-relevant fields are absent. Errors are returned per field: `{"field": "income", "code": "max", "message": "…"}`.

---

## 8. Indicator definition format

Stored in `indicator_definition.definition`. This is the heart of the "AI proposes, human approves, engine calculates" model: the AI writes these, people approve them, and the engine compiles them into SQL. It is deliberately **declarative and closed**, with no expressions, code or SQL, so every definition can be validated, explained in plain language and computed safely.

### 8.1 Shape

```json
{
  "schema_version": 1,
  "kind": "count",
  "count": {
    "unit": "entity",
    "entity_type": "person",
    "sources": [
      {"form": "training_attendance", "where": {"field": "completed", "op": "eq", "value": "yes"}}
    ],
    "entity_where": {"field": "entity.sex", "op": "eq", "value": "female"},
    "require_in": []
  },
  "time": {"aggregation": "cumulative", "date": "collected_at"},
  "disaggregate_by": ["age_group", "refugee_status"]
}
```

### 8.2 Kinds

| Kind | Meaning | Required block |
|---|---|---|
| `count` | Number of distinct **entities**, **records** or **repeat items** matching conditions | `count` |
| `sum` | Sum of a numeric field | `value` |
| `average` | Mean (or median) of a numeric field | `value` (+ `"stat": "mean" \| "median"`) |
| `ratio` | `numerator / denominator × scale`; each side is itself a `count` or `sum` block | `numerator`, `denominator`, `scale` (100 for %) |
| `milestone` | Achieved or not (1/0), e.g. "policy adopted" | `milestone` |
| `index` | Weighted combination of other indicators' values | `components: [{indicator, weight}]` |
| `qualitative` | Narrative; filled from a qualitative analysis or a text entry | `qualitative` |
| `manual` | Value entered by hand each period | none |

Blocks:

```jsonc
// count
"count": {
  "unit": "entity" | "record" | "repeat_item",
  "entity_type": "person",                 // required when unit = entity
  "sources": [                             // union across forms
    {"form": "<form key>", "where": <condition>, "repeat": "<repeat field id>"}
  ],
  "entity_where": <condition on entity.* attributes>,
  "require_in": [                          // entity must ALSO appear in these sources (semi-join)
    {"form": "<form key>", "where": <condition>}
  ]
}

// value (sum / average)
"value": {"form": "<form key>", "field": "<numeric field id>", "where": <condition>, "repeat": "<optional>"}

// milestone
"milestone": {"form": "<form key>", "achieved_when": <condition>}   // achieved if any matching record exists

// time
"time": {
  "aggregation": "period" | "cumulative" | "latest",
  "date": "collected_at" | "<date field id>"
}
```

**Time aggregation:**
- `period`: only records dated inside the reporting period.
- `cumulative`: everything from project start to the end of the period, **computed directly** (distinct entities are de-duplicated across the whole span, never by summing period counts).
- `latest`: the most recent record per entity up to the period end (for "% of households with…" measured in repeated survey rounds).

The engine always stores **both** a `period` and a `cumulative` value where that makes sense, so the dashboard can show either.

### 8.3 Conditions

```jsonc
{"all": [<condition>, ...]}
{"any": [<condition>, ...]}
{"not": <condition>}
{"field": "<field id> | entity.<attribute>", "op": "<op>", "value": <value>}
```

Operators: `eq`, `neq`, `gt`, `gte`, `lt`, `lte`, `in`, `not_in`, `between` (`[lo, hi]`), `contains` (for `select_multiple`), `is_empty`, `is_not_empty`.

Besides form fields and `entity.<attribute>`, a condition can reach **one hop** through a `record_ref` field: `"field": "session.session_type"` reads `session_type` on the register record that the `session` field points to. Example: count distinct people who attended sessions whose type is "agri-food". Also available: `"field": "site"` / `"component"` with `in` lists of keys.

### 8.4 Examples

**Women trained (distinct people, cumulative, by age group and refugee status):** the example in [8.1](#81-shape).

**% of trained farmers reporting higher income at follow-up:**
```json
{
  "schema_version": 1,
  "kind": "ratio",
  "scale": 100,
  "numerator": {"count": {
    "unit": "entity", "entity_type": "person",
    "sources": [{"form": "followup_survey", "where": {"field": "income_change", "op": "eq", "value": "increased"}}],
    "require_in": [{"form": "training_attendance", "where": {"field": "completed", "op": "eq", "value": "yes"}}]
  }},
  "denominator": {"count": {
    "unit": "entity", "entity_type": "person",
    "sources": [{"form": "followup_survey"}],
    "require_in": [{"form": "training_attendance", "where": {"field": "completed", "op": "eq", "value": "yes"}}]
  }},
  "time": {"aggregation": "latest", "date": "collected_at"},
  "disaggregate_by": ["sex"]
}
```

**Total hectares under improved practices:**
```json
{"schema_version": 1, "kind": "sum",
 "value": {"form": "farm_visit", "field": "hectares_improved"},
 "time": {"aggregation": "latest", "date": "visit_date"}}
```

### 8.5 Validation on approval
A definition can only be approved when:
1. It parses into the Pydantic model (closed set of keys and values).
2. Every referenced form exists in the project and has a published version.
3. Every referenced field exists in **every published version** it will read. If it's missing in some, those versions are listed as a warning, and their records are excluded.
4. Types fit: `sum`/`average` fields are numeric; `between` values are ordered; `contains` is only used on `select_multiple`; `in` values are among the field's options.
5. `entity` counts name an entity type that the source forms link to.
6. Every `disaggregate_by` key exists and its source is reachable (entity attribute of the counted entity, or a field in every source form).
7. A **preview run** against current data succeeds and its result is shown to the approver.

On approval, `indicator_field_link` rows are written and the indicator is marked dirty.

---

## 9. Calculation engine

### 9.1 Flow

```
approved definition ─► compiler ─► parameterized SQL ─► SQLite ─► rows ─► indicator_value
                          ▲
                 dialect (SQLite now, PostgreSQL later)
```

### 9.2 Compilation
The compiler walks the definition and emits one SQL statement per (indicator, period, scope). **Field paths and values are always bound parameters**, never string-concatenated. Field ids have already been validated against the form schema, so the compiler only ever builds paths like `$.completed` from known-good ids.

The "women trained" example compiles (simplified) to:

```sql
WITH src AS (
  SELECT DISTINCT COALESCE(e0.merged_into_id, e0.id) AS entity_id   -- merged entities count as their survivor
  FROM submission s
  JOIN form_version fv ON fv.id = s.form_version_id
  JOIN form f          ON f.id = fv.form_id
  JOIN entity e0       ON e0.id = s.entity_id
  WHERE s.project_id = :project_id
    AND f.key = :form_0
    AND s.deleted_at IS NULL
    AND s.status <> 'rejected'
    AND s.collected_on BETWEEN :project_start AND :period_end      -- cumulative
    AND json_extract(s.data, :path_0) = :val_0                      -- '$.completed' = 'yes'
)
SELECT
  CASE
    WHEN (julianday(:period_end) - julianday(json_extract(e.attributes, '$.date_of_birth'))) / 365.25 < 18 THEN '<18'
    WHEN (julianday(:period_end) - julianday(json_extract(e.attributes, '$.date_of_birth'))) / 365.25 < 30 THEN '18-29'
    ELSE '30+'
  END                                          AS age_group,
  json_extract(e.attributes, '$.refugee_status') AS refugee_status,
  COUNT(DISTINCT e.id)                         AS value
FROM src
JOIN entity e ON e.id = src.entity_id
WHERE e.deleted_at IS NULL
  AND json_extract(e.attributes, :epath_0) = :eval_0                 -- '$.sex' = 'female'
GROUP BY age_group, refugee_status;            -- plus the total and single-dimension levels, see 9.5
```

Other constructs:
- **Repeat groups:** `JOIN json_each(s.data, '$.children') AS r` and conditions on `json_extract(r.value, '$.child_age')`.
- **`require_in`:** `AND src.entity_id IN (SELECT entity_id FROM … other source …)`.
- **`select_multiple` contains:** `EXISTS (SELECT 1 FROM json_each(s.data, :path) WHERE value = :val)`.
- **`latest`:** a window function (`ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY collected_at DESC)`) keeps the latest record per entity up to the period end.
- **Merged entities** resolve to their surviving entity before counting (`COALESCE(merged_into_id, id)`), so their submissions still count, but only once.

### 9.3 Running
- **Dirty tracking:** when a submission is saved, the service looks up `indicator_field_link` for that form and inserts the affected indicators into `indicator_dirty`, then enqueues a `recalculate` job with `dedupe_key = 'recalc:<project_id>'` and `run_after = now + 30 s`. A burst of submissions collapses into one recalculation.
- **The recalculate job** computes the dirty indicators for every **open** period (period and cumulative scopes, all breakdowns), writes `indicator_value` rows in one short transaction per indicator, and clears only the dirty flags set *before* it started. Because the dedupe index only covers queued jobs, a submission arriving mid-run queues the next recalculation, so nothing is missed.
- **Locked periods are never recalculated**, so submitted reports stay frozen. Unlocking (M&E lead only, audited) makes them recalculable.
- **Nightly:** a full recalculation of every active indicator, as a safety net.
- **Approving a new definition version** recalculates that indicator for all open periods.

### 9.4 Statuses shown on the dashboard
| Status | Meaning |
|---|---|
| `ok` | Computed |
| `no_data` | Definition is fine, but no matching records yet |
| `not_computable` | No approved definition, a blocking open question, or a referenced field missing; `reason` says which in plain language |
| `manual` | Comes from `manual_value` |

### 9.5 Breakdowns
`breakdown_key` is `''` for the total, or canonical JSON with sorted keys, e.g. `{"age_group":"18-29","sex":"female"}`. The engine stores the total, each single-dimension breakdown, and the full cross-breakdown (SQLite has no `GROUPING SETS`, so each level is a separate `GROUP BY` over the same CTE in one transaction). Values not in the disaggregation's `value_set` are grouped under `"unknown"`, so totals always add up and data-quality gaps are visible.

### 9.6 Correctness rules (lessons from ENABEL)
- **Distinct entities vs. records** is always explicit in the definition (`unit`), never inferred.
- **Cumulative counts are computed, never summed** from period counts.
- **Rejected and soft-deleted submissions are always excluded**; flagged ones are included but counted in `warnings`.
- **The engine never guesses.** Anything ambiguous is `not_computable` with a reason, never a silent zero.

---

## 10. Document ingestion

Turns any uploaded file into an **intermediate representation (IR)** the AI can read, with a source reference for every piece of text so reviewers can see where each suggestion came from.

### 10.1 Supported inputs

The rule: **if a person can read the framework, the platform should be able to extract it.** No template, no required column names, no required layout.

**File types**

| Type | Handling |
|---|---|
| `.xlsx`, `.xlsm`, `.csv` | Parsed directly |
| `.xls`, `.ods` | Converted to `.xlsx` with LibreOffice, then parsed |
| `.docx` | Parsed directly |
| `.doc`, `.odt`, `.rtf` | Converted to `.docx`, then parsed |
| `.pptx` | Parsed directly (Theory of Change slides: shapes, text boxes, arrows, tables) |
| `.ppt`, `.odp` | Converted to `.pptx`, then parsed |
| `.pdf` (digital) | Text and tables extracted |
| `.pdf` (scanned), `.png`, `.jpg` | OCR, or a vision model for diagrams and photos of printed logframes |

**Framework shapes** the pipeline is built and tested against:

- **Logframe matrix** (e.g. the classic 4×4: intervention logic / indicators / sources of verification / assumptions), with merged cells spanning rows.
- **Results chain tables** (impact → outcomes → outputs → activities) with any level names.
- **Indicator tracking tables** where baselines and targets are spread across columns per year or quarter ("wide" layout), including actuals already filled in.
- **Performance measurement frameworks / plans** with one row per indicator and many attribute columns.
- **Indicator reference sheets** (one indicator per page or per sheet, as key–value pairs: definition, unit, disaggregation, data source, frequency, responsible).
- **Narrative M&E plans** in Word, where indicators sit in paragraphs and bullet lists.
- **Theory of Change diagrams** in PowerPoint, PDF or as images (boxes and arrows).
- **Donor templates** (EU, USAID, FCDO, GIZ, UN agencies, World Bank and others); recognized as layouts, never hard-coded.
- **Transposed tables** (indicators as columns), **multi-row headers**, **blank spacer rows**, **subtotal rows**, **colour-coded levels** (fill colour is kept in the IR as a hint).
- **Several frameworks in one file** (e.g. one sheet per municipality or country) → proposed as separate **components** of one project.
- **Any language**, including right-to-left scripts, and mixed-language documents.

**Packages:** one upload can contain several files that belong together: the framework, indicator reference sheets, the survey tools (questionnaires), a targets workbook and calculation notes. The AI decides what each file is (`framework_document_file.detected_role`) and links them: questionnaires become forms, reference sheets enrich indicators, targets fill `indicator_target`.

### 10.2 IR format (stored as a JSON file, linked from `framework_document_file.ir_file_id`)

```json
{
  "source": {"filename": "RF_final.xlsx", "type": "xlsx", "sha256": "…"},
  "blocks": [
    {"id": "b1", "kind": "heading", "text": "Results Framework", "ref": {"sheet": "Logframe", "cell": "A1"}},
    {"id": "b2", "kind": "table", "ref": {"sheet": "Logframe", "range": "A3:H41"},
     "header_rows": 2,
     "rows": [["Level", "Result", "Indicator", "Baseline", "Target", "MoV", "Frequency", "Responsible"], ["…"]],
     "cell_refs": [["A3", "B3", "…"]]},
    {"id": "b3", "kind": "paragraph", "text": "…", "ref": {"page": 4}}
  ]
}
```

### 10.3 Parsers
- **Conversion first:** legacy and OpenDocument files are converted with LibreOffice in headless mode (`soffice --headless --convert-to …`), in a sandboxed temporary directory with a timeout. The converted file is kept (`converted_file_id`) so reviewers can open it.
- **Excel (`openpyxl`):** every sheet, including hidden sheets (marked hidden). **Merged cells are unmerged and the value copied into every covered cell**, so each row is self-contained. Formulas are read as their cached values. Cell comments are kept as notes. Fill colour and bold/indent are kept as style hints (many frameworks mark levels by colour or indentation). Empty rows split tables. Multi-row headers are detected (rows above the first data-like row) and kept as `header_rows`.
- **Word (`python-docx`):** headings (with level), paragraphs, bulleted and numbered lists (with nesting) and tables (merged cells unmerged the same way). Text boxes are read from the underlying XML.
- **PowerPoint (`python-pptx`):** per slide, every shape with its text and position, connectors with the shapes they join (so a Theory of Change diagram becomes boxes plus arrows), and tables.
- **PDF (`pdfplumber`):** text per page and detected tables. If a page has almost no extractable text, it is treated as scanned and sent to **OCR** (Tesseract, or a Qwen vision model if configured).
- **Images:** sent to the vision model (if configured) for a structured description of tables or boxes and arrows; otherwise OCR.
- **CSV:** one table block.
- **Limits:** 25 MB per file, 10 files per package, 200 pages, 50 sheets, 100,000 cells (configurable). Office files are opened read-only with a decompressed-size check (zip-bomb protection).

### 10.4 Output checks
The parse step records counts (sheets, tables, rows, pages, OCR pages) and warnings on the `job` result, so the user sees "Parsed 3 sheets, 2 tables, 118 rows; 1 hidden sheet included" before extraction starts.

---

## 11. AI extraction pipeline

### 11.1 LLM client
- `openai` SDK with `base_url` and `api_key` from config, so the same code talks to vLLM, Ollama, LM Studio or a hosted Qwen endpoint.
- **Structured output:** every call passes a JSON Schema generated from the step's Pydantic model (`response_format={"type": "json_schema", …}`; Ollama's `format` parameter is used when on Ollama). The server constrains generation to valid JSON for that schema.
- **Validate, then retry with feedback:** the output is validated with Pydantic and step-specific checks. On failure the errors are sent back in a follow-up message ("Field `unit` must be one of …"), up to 3 attempts. After that the item becomes a suggestion with `validation_errors` and an open question. It never silently disappears.
- **Determinism:** `temperature = 0` (or 0.1 for generation steps), fixed `seed` where supported.
- **Concurrency:** a semaphore (`LLM_MAX_CONCURRENCY`, default 4) limits parallel calls.
- **Logging:** every call writes an `ai_run` row (model, prompt id, tokens, latency, validity, raw output file).
- **Models are configurable per step:** a larger model (e.g. a 30B–70B-class Qwen instruct model) for extraction and definitions; a smaller, faster one for classification and qualitative coding; a vision model for OCR if used.

### 11.2 Prompts
Stored as versioned templates in `app/ai/prompts/<step>@v<n>.md`. Each prompt has: role and task, the canonical model it must fill (described in plain language), rules (e.g. "never invent a baseline; if missing, set null and raise a question"), 1–2 short worked examples, and the input. The prompt id is saved on every `ai_run` and `ai_suggestion`, so output can be traced back to the exact prompt.

**Framework documents are untrusted input.** Prompts wrap document content in clear delimiters and tell the model to treat it as data. More importantly, nothing the model returns is ever executed: it only becomes a schema-validated *suggestion* that a human reviews.

### 11.3 Steps

The pipeline runs as one `extract_framework` job, with progress updates after each step.

| # | Step | LLM? | Input | Output |
|---|---|---|---|---|
| A | **Parse** | no | every file in the package | one IR per file (section 10) |
| B | **Locate** | yes (small) | list of IR blocks from all files, with short previews | what each file and block is: results framework, indicator reference sheet, questionnaire, targets table, Theory of Change, irrelevant. Also detects **several frameworks** in one package (e.g. one sheet per municipality) and proposes one **component** per framework. |
| C | **Map layout** | yes (small) | header rows + 5 sample rows of each framework table | the table's orientation (normal or transposed) and, for each column, its role: `level`, `result_code`, `result_statement`, `indicator`, `unit`, `baseline`, `target`, `target_by_period` (one column per year/quarter, with the period it represents), `actual_by_period`, `means_of_verification`, `frequency`, `responsible`, `assumptions`, `disaggregation`, `ignore`. Plus how levels are marked when there's no level column (indentation, colour, numbering like `1` / `1.1` / `1.1.1`). |
| D | **Build structure** | mostly no | mapped tables | levels, results tree and raw indicator rows, built **by code** from the layout mapping. Documents with no usable table (narrative plans, reference sheets, ToC diagrams) fall back to LLM extraction per section, slide or page. Reference sheets are matched to indicators by code or name and merged in. |
| E | **Normalize indicators** | yes | each raw indicator row (+ its result) | clean name, unit, kind, direction, baseline (value/text/date), targets (per period or final), disaggregation mentions, data source, frequency, confidence, open questions |
| F | **Entities and breakdowns** | yes | all normalized indicators | proposed `entity_type`s with attribute schemas, and `disaggregation`s with value sets (e.g. "disaggregated by sex and age" → `sex`, `age_group` with bins) |
| G | **Forms** | yes | questionnaire blocks from B (if any) + indicators grouped by data source and frequency | **convert** existing questionnaires into the form schema (section 7), or **generate** new forms from means of verification. Decides **survey vs. register** (activities like training sessions or exhibitions become registers; attendance and follow-ups become surveys linked to them with `record_ref`), and which forms are **public** (applications, registrations). One form per data-collection moment, shared across the indicators that use it. Fields needed by breakdowns are included. |
| H | **Definitions** | yes | each indicator + its form(s) + entity types + disaggregations | an indicator definition (section 8) referencing real form keys and field ids |
| I | **Library links** | yes (small) | indicators + candidate library entries (pre-filtered by rapidfuzz) | suggested links to standard indicators |
| J | **Cross-check** | no | everything | deterministic validation (below) |
| K | **Package** | no | everything | one `change_set` with ordered `ai_suggestion`s and `open_question`s |

Targets and actuals found in wide tables (step C) become `indicator_target` suggestions per period and, for actuals already reported before the platform was used, `manual_value` suggestions, so historic results aren't lost.

Using an LLM only to **map the layout** (C), then building the structure **in code** (D), is the key to reliability and cost: on a typical 40-row logframe, the model reads ~10 rows instead of all 40, and row-level mistakes can't happen in step D.

**Large documents:** steps E and H run per indicator (in parallel, within the concurrency limit), so document size never exceeds the context window. Step B sends previews, not full blocks.

### 11.4 Cross-check (step J)
- Every indicator belongs to a result; every result has a level; the tree has no cycles.
- Every definition passes the full approval validation in [8.5](#85-validation-on-approval) against the *proposed* forms.
- Every form passes the form validator ([section 7](#7-form-schema-format)).
- Every breakdown mentioned in an indicator has a disaggregation, and a field or entity attribute that feeds it.
- Every indicator has either a valid definition or is explicitly `manual` / `qualitative`.
- Duplicate indicators (same name under the same result) are flagged.
- **Each failure becomes a `validation_errors` entry on the suggestion and, if a person must decide, an open question** (blocking where publishing would produce something broken).

### 11.5 What the AI flags as open questions
Missing baselines; targets without a number ("improved capacity"); unclear unit of count ("beneficiaries": people or households?); unclear time aggregation (cumulative or per period?); indicators with no obvious data source; conflicting targets between sheets; disaggregations mentioned without categories. Each question has suggested answers in `options` where possible.

---

## 12. Review and publishing

### 12.1 Review
- The change set opens grouped the way a person thinks: **structure** (levels, results) → **indicators** (with targets and definitions) → **forms** → **entity types and breakdowns** → **library links**.
- Each suggestion shows its `source_ref` (sheet and cells, or page) so the reviewer can check it against the original.
- Actions per suggestion: **accept**, **edit** (payload replaced, `original_payload` kept, status `edited`), **reject**, **regenerate** (re-runs that one step for that item, optionally with a reviewer note like "count households, not people").
- Answering an open question can trigger regeneration of the suggestions it affects.
- `POST /change-sets/{id}/validate` runs the cross-check on the current (edited) state without publishing.

### 12.2 Publishing
`POST /change-sets/{id}/publish` runs in **one write transaction**:
1. Re-validate everything. Fail if any accepted suggestion has errors or any blocking question is open.
2. Topologically sort accepted/edited suggestions by `depends_on`.
3. Apply them: create/update/retire rows, mapping each `temp_key` to the real id.
4. Forms become `form` + `form_version` (published); definitions become `indicator_definition` (approved) + `indicator_field_link`.
5. Write audit log entries, mark the change set `published` and the framework document `published` (the previous one `superseded`).
6. Mark all affected indicators dirty and enqueue recalculation (after commit).

Rejected suggestions are kept for evaluation (they show where the AI is weak).

---

## 13. Data collection and offline sync

### 13.1 Collector bundle
`GET /projects/{id}/collector-bundle` returns everything a field device needs to work offline: active published form versions (with schemas), the entity types, and the entities the collector may select (paged, filtered by assignment if configured). It has an `ETag`; devices send `If-None-Match` and get `304` when nothing changed.

### 13.2 Submitting
- Devices create submissions with **UUIDv7 ids generated on the device** and keep them in a local queue.
- `POST /sync/submissions` accepts a batch (max 200). Per item the server:
  1. Checks the collector may submit to that project and the form version is published (or was published when collected).
  2. Validates `data` against **that** form version's schema.
  3. Resolves the entity (13.3).
  4. Inserts with `INSERT … ON CONFLICT(id) DO NOTHING`, so **resending is always safe**.
  5. Marks affected indicators dirty.
- The response lists each item as `accepted`, `duplicate` (already had it, which counts as success) or `rejected` with field errors. Devices drop accepted and duplicate items and show rejected ones to the collector.
- **Files** (photos, evidence) are uploaded first via `POST /files` with a device-generated id, then referenced by id in the submission data. Images are compressed server-side (long edge 1600 px, JPEG quality 80).
- The server keeps the device's `collected_at` and its own `received_at`. Submissions dated in the future (beyond a 1-day tolerance) are flagged.

### 13.3 Entity resolution
- If the form links to an entity and includes the entity type's identity fields, the server normalizes them (trim, uppercase, remove spaces and dashes) and computes `identity_hash = HMAC-SHA256(secret, entity_type_id + normalized values)`. **Raw national IDs are never stored in `entity`.**
- Existing entity with that hash → the submission is stored with the existing entity's id. If the device sent a new entity id, store it in `entity_alias` (so later submissions using it resolve too) and return the mapping so the device can update its local copy.
- No match → create the entity with the device's id; copy `entity_attribute` fields into `attributes`.
- **Possible duplicates** without an identity key (same name, date of birth and location) are listed at `GET /entities/duplicates` for a data manager to merge. Merging sets `merged_into_id` (and repoints any earlier merges into the merged entity, so chains never form); nothing is deleted, and the engine counts merged entities once.

### 13.4 Registers (activity records)
- `GET /forms/{id}/records` lists a register's records with filters and the columns the schema marks as `list: true`; `GET /submissions/{id}` returns the record with its linked records (`submission_link` both ways: a session shows its attendance; an attendance shows its session) and evidence.
- `PATCH /submissions/{id}` with new `data` (register records only): validated against the record's form version, the old data copied to `submission_revision`, `revision` incremented, links rebuilt, affected indicators marked dirty. Survey submissions are never edited, only flagged, rejected or superseded by a new submission.
- On every save, `record_ref` / `entity_ref` fields are checked (the target exists, is in the same project, is of the right form) and written to `submission_link`.

### 13.5 Evidence and verification gaps
- Files can be attached to any record (`evidence.submission_id`) or to an indicator for a period (`evidence.indicator_id` + `reporting_period_id`), e.g. a signed attendance sheet or a partner's report.
- For indicators with `evidence_required = 1`, `GET /projects/{id}/verification-gaps?period=` lists the records counted by that indicator that have no evidence, so the M&E lead can chase them before reporting. The engine still counts them, but adds a warning ("12 of 58 counted records have no evidence").

### 13.6 Public portal
For forms with `access = public` or `participant`, per component (its `public_slug`):
- `GET /public/{slug}` returns the component's public page data: open public forms, and published register records from forms with `public_listing = 1` (e.g. upcoming trainings or markets with dates and places; only fields the schema marks `public: true`).
- `POST /public/forms/{public_key}/submissions` accepts submissions without staff login: strict rate limits per IP, a honeypot field, and size limits. They arrive with status `submitted` for staff to review.
- Participants with an account (`participant` role) sign in and see `GET /public/me/submissions`, their own applications and their status.
- Public pages never expose indicators, other people's data or anything marked `pii`.

---

## 14. Qualitative analysis

Runs as a `qualitative` job over the open-text fields marked `qualitative: true`.

1. **Select** responses by forms, fields, periods and filters. **PII fields are never included**; known PII patterns in free text (phone numbers, ID numbers, emails) are masked before sending.
2. **Open coding:** batches of ~30 responses; the model proposes short codes for each response (structured output: `[{submission_id, codes: [...]}]`).
3. **Consolidate:** all codes are merged into a codebook of at most N themes (default 12), each with a label, description and sentiment.
4. **Assign:** each response is mapped to 0–3 final themes, with a short supporting quote taken **verbatim** from the response. The quote is checked to be an exact substring; if not, it is dropped.
5. **Summarize:** counts per theme, breakdown by disaggregation (via the linked entity), and a short narrative per theme plus an overall summary.
6. **Store** in `qual_analysis`, `qual_theme`, `qual_coding`. People can rename, merge or split themes afterwards (audited).

Responses in any language are analyzed together; themes and summaries are written in the project's default language. Viewers see themes, counts and summaries, but not raw quotes.

A qualitative indicator (`kind: qualitative`) can point at a saved analysis, so its themes appear on the dashboard for that period.

---

## 15. Framework revisions

Uploading a new version of the framework runs the same pipeline (steps A–J), then a **diff** step (`revision_diff` job):

1. **Match** each new result/indicator to an existing one: exact code match first, then fuzzy name similarity (rapidfuzz, threshold 85), then an LLM tie-break for ambiguous pairs.
2. **Produce suggestions** of kind `update` (changed text, unit, baseline or targets), `create` (new items) and `retire` (items no longer present; never deleted).
3. **Forms:** changes produce a **new draft form version**, never edits to a published one.
4. **Definitions:** if a referenced field disappears or changes type, the affected definition gets a new draft version and an open question.
5. Everything goes into a `change_set` of kind `revision` and follows the normal review and publish flow. Past submissions stay tied to the form version they were collected with, and locked periods keep their values.

---

## 16. Reports

`POST /projects/{id}/reports` (period, format) enqueues a `report` job that builds:

- **xlsx:** a summary sheet (project, period, generated at, by whom); an **indicator table** (code, result, indicator, unit, baseline, period target, period actual, cumulative actual, end target, % of end target, status/reason); one sheet per breakdown dimension; an open-questions sheet listing what is still undecided; and a qualitative sheet with themes and counts.
- **csv:** the indicator table only.

Reports for a **locked** period are reproducible: the same file every time. Reports for an open period are labelled "provisional". Donor-specific templates are a later feature: a template maps the platform's indicator table onto the donor's layout.

**Generated project documentation** (always up to date, because it's built from the published data):
- **Indicator reference sheets:** one page per indicator with its result, definition in plain language (from `/indicators/{id}/explain`), unit, baseline, targets, breakdowns, data source, forms and fields used, frequency, responsible, and open questions.
- **Data dictionary:** every form, field, option list, entity type and breakdown, with which indicators use each field.

Both export as xlsx (and Markdown), and replace the documentation that otherwise has to be written by hand for every project.

---

## 17. Background jobs

A small job queue in SQLite, with no Redis and no extra services.

- **Enqueue:** insert into `job` (with `dedupe_key` where repeats should collapse).
- **Claim** (worker, in a short transaction):
  ```sql
  UPDATE job
     SET status = 'running', locked_by = :worker, locked_at = :now, attempts = attempts + 1
   WHERE id = (SELECT id FROM job
                WHERE status = 'queued' AND run_after <= :now
                ORDER BY run_after LIMIT 1)
  RETURNING *;
  ```
- **Run** the handler outside any transaction; it reports `progress` (0–1) and `progress_note` as it goes.
- **Finish:** `succeeded` with `result`, or on error: re-queue with exponential backoff (`run_after = now + 30 s × 2^attempts`) until `max_attempts`, then `failed` with `error`.
- **Stale locks:** jobs `running` for longer than their type's timeout are re-queued at worker startup and every minute.
- **Progress to the browser:** `GET /jobs/{id}/events` (Server-Sent Events) streams status and progress; `GET /jobs/{id}` for polling.
- **Scheduled jobs:** the worker enqueues nightly recalculation, nightly backup and weekly integrity check.

| Job type | Typical duration | Timeout |
|---|---|---|
| `parse_document` | seconds | 5 min |
| `extract_framework` | 1–10 min (model and size dependent) | 60 min |
| `recalculate` | seconds | 10 min |
| `qualitative` | minutes | 60 min |
| `report` | seconds | 5 min |
| `revision_diff` | minutes | 60 min |

---

## 18. API reference

All routes under `/api/v1`. JSON in and out, except uploads (multipart) and downloads. Errors use one shape: `{"error": {"code": "validation_failed", "message": "…", "details": […]}}`. Lists are cursor-paginated (`?cursor=…&limit=50`). Project-scoped routes return `404` (not `403`) to non-members, so project existence isn't leaked.

**Auth**
| Method | Path | Notes |
|---|---|---|
| POST | `/auth/login` | email + password → access token (15 min) + refresh token (30 days, httpOnly cookie) |
| POST | `/auth/refresh` | rotates the refresh token |
| POST | `/auth/logout` | revokes the refresh token family |
| POST | `/auth/password-reset/request` | always returns 202 (no account enumeration) |
| POST | `/auth/password-reset/confirm` | token + new password |
| GET | `/me` | user, organizations, projects and roles |

**Organizations and projects**
| Method | Path |
|---|---|
| GET, POST | `/organizations` |
| GET, PATCH | `/organizations/{org_id}` |
| GET, POST, PATCH, DELETE | `/organizations/{org_id}/members[/{id}]` |
| GET, POST | `/organizations/{org_id}/projects` |
| GET, PATCH | `/projects/{project_id}` |
| GET, POST, PATCH, DELETE | `/projects/{project_id}/members[/{id}]` |
| GET, POST, PATCH, DELETE | `/projects/{project_id}/parties[/{id}]` |
| GET, POST, PATCH, DELETE | `/projects/{project_id}/components[/{id}]` |
| PUT | `/projects/{project_id}/members/{id}/components` (limit a member to some components) |
| GET, POST, PATCH, DELETE | `/projects/{project_id}/sites[/{id}]` |

**Framework and AI review**
| Method | Path | Notes |
|---|---|---|
| POST | `/projects/{id}/framework-documents` | multipart upload of one or more files (optional `component_id`, optional role hint per file) → `{document, job}` (parse + extract) |
| GET | `/projects/{id}/framework-documents` | versions and statuses |
| GET | `/framework-documents/{id}` | status, parse summary, IR preview |
| GET | `/projects/{id}/framework` | the published tree: levels → results → indicators (+ targets, definition status, latest value) |
| GET | `/projects/{id}/change-sets` | |
| GET | `/change-sets/{id}` | suggestions grouped by kind, with validation errors and open questions |
| PATCH | `/suggestions/{id}` | `{status}` or `{payload}` (edit) |
| POST | `/suggestions/{id}/regenerate` | optional `{note}` |
| POST | `/change-sets/{id}/validate` | dry-run cross-check |
| POST | `/change-sets/{id}/publish` | |
| POST | `/change-sets/{id}/discard` | |
| GET | `/projects/{id}/open-questions` | filter by status, blocking |
| POST | `/open-questions/{id}/answer` | `{answer, regenerate: bool}` |
| POST | `/open-questions/{id}/dismiss` | |

**Framework objects (manual editing outside AI)**
| Method | Path |
|---|---|
| GET, POST, PATCH, DELETE | `/projects/{id}/levels`, `/results`, `/indicators`, `/periods`, `/entity-types`, `/disaggregations` (`[/{item_id}]`) |
| GET, POST, PATCH, DELETE | `/indicators/{id}/targets[/{target_id}]` |
| GET, POST | `/indicators/{id}/definitions` (POST creates a draft version) |
| POST | `/indicators/{id}/definitions/{version}/approve` |
| POST | `/indicators/{id}/preview` | `{definition}` → computed values without saving |
| GET | `/indicators/{id}/explain` | the approved definition in plain language |
| POST | `/periods/{id}/lock`, `/periods/{id}/unlock` |
| GET | `/indicator-library?search=` |

**Forms, entities and submissions**
| Method | Path | Notes |
|---|---|---|
| GET, POST | `/projects/{id}/forms` | |
| GET, PATCH | `/forms/{id}` | |
| GET, POST | `/forms/{id}/versions` | POST creates a draft |
| PATCH | `/form-versions/{id}` | draft only |
| POST | `/form-versions/{id}/publish` | runs the form validator |
| GET | `/projects/{id}/collector-bundle` | ETag |
| POST | `/sync/submissions` | batch, idempotent |
| POST | `/form-versions/{id}/submissions` | single online submission |
| GET | `/projects/{id}/submissions` | filters: component, site, form, period, collector, status, entity |
| GET | `/forms/{id}/records` | register list view |
| GET, PATCH | `/submissions/{id}` | GET includes links and evidence; PATCH: status + review note, or new `data` for register records |
| GET | `/submissions/{id}/revisions` | earlier versions of a register record |
| DELETE | `/submissions/{id}` | soft delete |
| GET, POST, DELETE | `/projects/{id}/evidence[/{evidence_id}]` | attach files to records or indicator periods |
| GET | `/projects/{id}/verification-gaps?period=` | counted records missing required evidence |
| GET, POST, PATCH | `/projects/{id}/entities[/{entity_id}]` | |
| GET | `/projects/{id}/entities/duplicates` | |
| POST | `/entities/{id}/merge` | `{into_id}` |
| POST | `/files` | multipart, optional client id |
| GET | `/files/{id}` | permission-checked download |
| GET, POST, PATCH, DELETE | `/projects/{id}/manual-values[/{item_id}]` | |

**Dashboard, analysis and reports**
| Method | Path | Notes |
|---|---|---|
| GET | `/projects/{id}/dashboard?period=` | all indicators: baseline, target, period and cumulative values, status, reason, % of target |
| GET | `/indicators/{id}/values?breakdown=sex,age_group` | time series and breakdowns |
| POST | `/projects/{id}/recalculate` | |
| POST, GET | `/projects/{id}/qualitative-analyses` | |
| GET | `/qualitative-analyses/{id}` | themes, counts, summary (quotes by role) |
| PATCH | `/qual-themes/{id}` | rename, merge |
| POST, GET | `/projects/{id}/reports` | |
| GET | `/reports/{id}/download` | |
| GET | `/projects/{id}/docs/indicator-sheets?format=xlsx\|md` | generated indicator reference sheets |
| GET | `/projects/{id}/docs/data-dictionary?format=xlsx\|md` | generated data dictionary |
| GET | `/public/{slug}` | public page data for a component (no login) |
| POST | `/public/forms/{public_key}/submissions` | public submission (no login, rate-limited) |
| GET | `/public/me/submissions` | a participant's own applications |
| GET | `/jobs/{id}`, `/jobs/{id}/events` | |
| GET | `/projects/{id}/audit-log` | |
| GET | `/healthz`, `/readyz` | readyz checks the database and the LLM endpoint |

Example dashboard item:

```json
{
  "indicator_id": "0192…",
  "code": "1.1",
  "name": "Number of women completing agri-food training",
  "result": {"code": "1", "statement": "Women's participation in agri-food production increased"},
  "unit": "people",
  "baseline": 0,
  "target_end": 400,
  "period": {"label": "Q1 2027", "value": 58, "target": 100},
  "cumulative": {"value": 112, "percent_of_end_target": 28.0},
  "status": "ok",
  "warnings": ["3 flagged submissions included"],
  "breakdowns_available": ["age_group", "refugee_status"]
}
```

---

## 19. Security and privacy

- **Passwords:** Argon2id. Login rate-limited per IP and per account (e.g. 10 attempts per 15 minutes). Accounts are created by admins (no public sign-up).
- **Tokens:** 15-minute JWT access tokens; refresh tokens stored as hashes, rotated on every use, and reuse of an old refresh token revokes the whole family.
- **Transport:** HTTPS only (Caddy); HSTS; CORS restricted to the configured front-end origins.
- **Tenancy:** repository-layer scoping plus automated cross-project tests ([3.4](#34-tenancy-without-row-level-security), [20.4](#204-tenancy-and-permission-tests)).
- **SQL injection:** all SQL uses bound parameters; the engine only builds JSON paths from validated field ids.
- **Uploads:** type checked by content (magic bytes), not extension; size limits; stored outside the web root under random names; served only through permission-checked routes.
- **PII:** `pii` fields are excluded from LLM calls, exports for viewers and qualitative quotes. Identity numbers are stored only as HMAC hashes (the key lives in config, not the database). Free text is pattern-masked before reaching the LLM.
- **LLM data boundary:** with a self-hosted model, no project data leaves the server. If a hosted API is configured, the admin UI shows a clear warning and the organization must opt in.
- **Prompt injection:** document content is treated as data; model output can only become validated suggestions that a human reviews; the model has no tools and can't trigger actions.
- **Audit:** every write, publish, approval, login and export is in `audit_log`, which can't be modified.
- **Secrets:** environment variables only; `.env` is never committed; `.env.example` lists every variable.

---

## 20. Testing strategy

### 20.1 Unit
Form validator, submission validator, definition validator, condition evaluator, compiler output (golden SQL snapshots), identity normalization and hashing, permission map, job backoff.

### 20.2 Engine correctness
A synthetic dataset generator creates entities and submissions with known answers. Required cases:
- distinct entities vs. records (one person attending 3 sessions = 1 person, 3 records);
- cumulative de-duplication across periods;
- `require_in` semi-joins;
- `latest` per entity across survey rounds;
- repeat groups;
- age bins at period end;
- merged entities counted once;
- rejected/deleted submissions excluded;
- fields missing in older form versions;
- `unknown` breakdown bucket keeps totals consistent.

**Benchmark:** recreate 5 indicators from the Sahel Horan framework (ENABEL) as definitions, run them on a synthetic dataset, and check they match hand-computed expected values. That proves the generic engine can replace ENABEL's hand-written SQL views.

### 20.3 Integration
Real SQLite file per test (temporary directory), all migrations applied, FastAPI test client. Covers: upload → parse → (mocked LLM) extract → review → publish → submit → recalculate → dashboard.

### 20.4 Tenancy and permission tests
- A generated test walks **every route** in the OpenAPI spec, calls it as a member of project B with ids from project A, and asserts `404`.
- A role matrix test asserts every row of the permissions table in [section 6](#6-roles-and-permissions).
- `scripts/check_routes_scoped.py` fails CI if a project route doesn't depend on `ProjectScope`.

### 20.5 Ingestion
Golden IR snapshots for at least one sample of every input type and shape in [10.1](#101-supported-inputs): a classic 4×4 logframe in Excel with merged cells, an indicator tracking table with targets per year as columns, a transposed table, a workbook with one framework per sheet, a multi-file package (framework + reference sheets + questionnaires), indicator reference sheets in Word, a narrative M&E plan, a Theory of Change in PowerPoint, a PDF annex with tables, a scanned PDF, a photo of a printed logframe, a legacy `.xls`, and an Arabic-language framework. **Use only documents we have permission to use**; real beneficiary data never goes into fixtures.

### 20.6 AI evaluation
`tests/ai_eval/` holds hand-labelled expected outputs for the sample frameworks. `make ai-eval` runs the real pipeline against a configured model and reports:
- indicator **recall and precision** (proposed target: ≥ 90% recall before beta);
- correct result/level placement;
- baseline and target accuracy;
- % of definitions that pass validation without edits;
- open questions raised vs. expected;
- tokens and time per framework.

It's run on every prompt or model change, and results are kept, so a prompt change can't silently make extraction worse.

**Hand-built benchmark:** where a project was previously set up by hand (ENABEL is the first: its frameworks, forms workbooks and indicator documentation exist), the AI's draft from the original files is compared against what was built by hand: indicators found, forms proposed, definitions and open questions. Used only with permission to use those files.

### 20.7 Load
Simulate 50 collectors syncing batches of 20 submissions at once while an extraction job and a recalculation run. Targets: p95 sync under 1 s, no failed writes, recalculation lag under 2 minutes.

### 20.8 CI checks (every push)
`ruff`, `mypy`, unit + integration + tenancy tests, `check_migrations.py` (applied migrations match their checksums; files are only ever added), `check_routes_scoped.py`, and a check that no hard `DELETE` statements exist outside migrations.

---

## 21. Operations

### 21.1 Configuration (`.env.example`)
```
APP_ENV=development
DATABASE_PATH=./data/app.db
FILES_PATH=./data/files
BACKUP_PATH=./data/backups
SECRET_KEY=change-me                  # JWT signing
IDENTITY_HMAC_KEY=change-me           # hashing of national IDs; never rotate without a re-hash plan
CORS_ORIGINS=http://localhost:5173
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=30
LLM_BASE_URL=http://localhost:8001/v1
LLM_API_KEY=not-needed-for-local
LLM_MODEL_EXTRACT=qwen-extract        # served model name for extraction/definitions
LLM_MODEL_FAST=qwen-fast              # classification, qualitative coding
LLM_MODEL_VISION=                     # optional, OCR of scanned pages
LLM_MAX_CONCURRENCY=4
LLM_TIMEOUT_SECONDS=180
LLM_IS_EXTERNAL=false                 # true shows the data-boundary warning
UPLOAD_MAX_MB=25
```

### 21.2 Running
- **Development:** `make dev` starts the API (with reload) and the worker; Ollama serves a Qwen model locally.
- **Production:** Docker Compose with `api` (uvicorn, 2–4 workers), `worker` (1 process), `caddy` (TLS), and a volume for `data/`. The LLM runs on vLLM, on the same machine if it has a GPU or on a separate GPU machine on the private network.

### 21.3 Observability
- Structured JSON logs with a `request_id` on every line (also returned as a response header).
- Metrics: request latency per route, `SQLITE_BUSY` retries, job queue depth and age, job durations, LLM tokens and latency per step (from `ai_run`), recalculation lag.
- Alerts: backup failure, integrity-check failure, job failures, queue age over 15 minutes, LLM endpoint unreachable.

---

## 22. Build phases

Each phase ends with a working, tested increment. AI work starts only once the engine is proven by hand-written definitions.

### Phase 0: Foundations
- Repository layout, `uv`, FastAPI app factory, config, logging with request ids.
- SQLite connection with PRAGMAs, `BEGIN IMMEDIATE` helper, version check.
- Migration runner + checksum ledger + `check_migrations.py`; migration `0001`.
- Hard-delete triggers generator; audit log writer.
- Job queue + worker + SSE progress; health endpoints.
- CI: ruff, mypy, pytest.

**Done when:** `make dev` runs API + worker; a test job runs end to end; CI is green; deleting a row from a business table fails.

### Phase 1: Tenancy and auth
- Migration `0002`. Users, login, refresh rotation, logout, password reset.
- Organizations, projects, parties, memberships; `ProjectScope` dependency; permission map.
- Tenancy route walker and role matrix tests.

**Done when:** every route in the matrix passes; cross-project access returns 404 everywhere.

### Phase 2: Framework model (manual)
- Migrations `0003`, `0004`. CRUD for components, sites, levels, results, indicators, targets, periods, entity types, disaggregations, library.
- Component restriction on memberships, enforced in `ProjectScope` and covered by the tenancy tests.
- Framework tree endpoint (per component and for the whole project). Period generator from project dates and frequency.

**Done when:** a project with two components, each with its own framework, can be entered by hand through the API and read back as trees; a member limited to one component can't see the other.

### Phase 3: Forms and data collection
- Migration `0005`. Form schema models and validator; form versions with immutability; publish.
- Submission validator; online submit; batch sync with idempotency; files with compression.
- Entity resolution, aliases, duplicate detection, merge. Manual values. Collector bundle with ETag.
- Registers: record list/detail, edits with revisions, `record_ref`/`entity_ref` fields and `submission_link`. Evidence attachments and verification gaps.

**Done when:** a form can be published, filled offline (simulated), synced twice without duplicates, and linked to the right entities; a register (e.g. training sessions) can be edited with full history, and attendance surveys link to its records.

### Phase 4: Calculation engine and dashboard
- Migrations `0006` and `0007`. (The AI review tables are created now because definitions reference them; they're first used in Phase 6.) Definition models, validator, compiler (all kinds, conditions, repeats, `require_in`, time aggregations, breakdowns), dialect layer.
- Definition versions and approval; field links; dirty tracking; recalculation job; nightly recalculation; locked periods.
- Preview and explain endpoints; dashboard and values endpoints.

**Done when:** all engine correctness cases in [20.2](#202-engine-correctness) pass, including the 5-indicator ENABEL benchmark.

### Phase 5: Document ingestion
- IR format; LibreOffice conversion; Excel, Word, PowerPoint, PDF, CSV and image parsers; OCR / vision fallback; multi-file packages; limits; parse job and summary.

**Done when:** golden IR snapshots pass for every input type and shape listed in [10.1](#101-supported-inputs).

### Phase 6: AI extraction and review
- LLM client (structured output, retries with feedback, logging, concurrency).
- Prompts and steps B–K; cross-check; change sets, suggestions, open questions.
- Review endpoints (edit, accept, reject, regenerate, answer), validate, publish transaction.
- AI evaluation harness.

**Done when:** uploading each sample framework produces a change set that, after review, publishes forms and definitions that compute on test data; a package with several frameworks produces one component per framework; evaluation meets the agreed targets, including the hand-built benchmark ([20.6](#206-ai-evaluation)); no schema-invalid output ever reaches the review screen.

### Phase 7: Qualitative analysis
- Migration `0008` (qualitative tables). Selection with PII masking, coding, consolidation, assignment with verbatim-quote check, summaries, theme editing.

**Done when:** on a labelled sample of open-ended responses, themes are judged useful by an M&E reviewer and every quote is a verbatim substring.

### Phase 8: Revisions and reports
- Revision diff job and change sets; new form versions from revisions.
- Report builder (xlsx, csv); provisional vs. locked.
- Generated indicator reference sheets and data dictionary.

**Done when:** a revised framework produces correct update/create/retire suggestions; a locked-period report regenerates byte-identically; the generated documentation covers every published indicator and field.

### Phase 9: Hardening and operations
- Backups, retention, integrity check, restore drill.
- Rate limits, security review, upload hardening.
- Load test against the targets in [20.7](#207-load); fix bottlenecks.
- Docker Compose, Caddy, deployment and runbook docs.

**Done when:** a restore drill succeeds; load targets are met; the deployment guide brings up a fresh server end to end.

### Phase 10: Public portal
- Public page data per component, public and participant forms, published register listings, participant accounts and "my applications".
- Rate limits, honeypot, size limits; `public: true` field filtering; staff review queue for public submissions.

**Done when:** an anonymous visitor can see a component's listings and apply; a participant sees only their own applications; nothing indicator-related or `pii` is reachable from public routes (covered by the route walker).

---

## 23. Risks and mitigations

| Risk | Mitigation |
|---|---|
| The AI extracts something wrong | Human review of everything; source references on every suggestion; open questions instead of guesses; evaluation harness on every prompt/model change |
| The definition format can't express an indicator | `manual` kind as a fallback; collect such cases and extend the format in a new `schema_version` (validator supports old versions) |
| SQLite write contention | Short `BEGIN IMMEDIATE` transactions, one worker, batching, WAL; load test in Phase 9; documented move to PostgreSQL ([3.6](#36-when-to-move-to-postgresql)) |
| Form changes break past data | Immutable published versions, stable field ids, per-version validation, engine checks fields per version |
| Double counting | Explicit `unit`, cumulative computed directly, entity resolution and merging |
| Personal data reaching the LLM | Self-hosted model by default; `pii` fields excluded; pattern masking; hosted-API opt-in with warning |
| Model too weak on hardware available | Column-mapping approach keeps prompts small; per-step model choice; evaluation results guide the model size |
| Lost database file | Nightly consistent backups, off-site copies, integrity checks, monthly restore drills |

---

## 24. Open decisions

1. **Qwen model size and hardware.** Rough guide: a 30B-class model quantized to 4-bit fits on one 24–48 GB GPU; a 70B-class model needs roughly twice that. Pick after running the evaluation harness on sample frameworks with 2–3 candidate models.
2. **Where the LLM runs.** Same machine as the API, a separate GPU server, or (with opt-in) a hosted Qwen API.
3. **Identity scope.** Whether one person is one entity per project (simpler, more private) or per organization (lets an organization see the same person across its projects, as ENABEL did across municipalities). The schema supports both via `entity_type.identity_scope`.
4. **Launch languages** for the interface and AI output (e.g. English and Arabic first).
5. **Sample frameworks** we have permission to use for tests and evaluation.
6. **Front-end stack**, to be covered in its own plan; this API is designed to be used by any client.
7. **Public portal scope.** Which public features ship first (applications only, or listings too).

---

## 25. Worked example: ENABEL as one project

ENABEL is used here **only as an example** of the output the platform must reach. Nothing in the design is specific to it. ENABEL was built by hand: a developer read the frameworks and wrote the tables, forms, SQL views and screens. On this platform, the same result comes from uploading the files and reviewing the AI's draft.

### 25.1 How ENABEL maps onto the model

| ENABEL (built by hand) | On the platform (generated) |
|---|---|
| The company running the M&E work | `organization`, which has other projects too |
| The ENABEL programme (EU-funded, implemented with Enabel) | one `project`, with Enabel and the EU as `project_party` rows |
| Sahel Horan and Ramtha municipalities, each with its own framework | two `component`s; uploading a package with both frameworks proposes them automatically |
| Each municipality's staff sees only its own records; a super admin switches | memberships limited with `membership_component`; project admins see both |
| Sahel Horan: 7 forms, 20 indicators | AI draft from the Sahel Horan framework and forms workbook: forms and indicators in that component |
| Ramtha: 17 forms, 18 indicators | AI draft from the Ramtha framework and forms/calculations workbooks |
| Breakdowns by sex, age, refugee status and disability | `disaggregation` rows from the framework text; `person` `entity_type` with those attributes |
| One national ID = one person | identity field `national_id` → `identity_hash` |
| Sessions, exhibitions and registrations, advisory sessions, production initiatives, linkage requests | **register** forms; attendance and registrations are surveys linked with `record_ref` |
| The five-section follow-up survey for phones in the field | a survey form with `group`s, offline-capable |
| Indicators counted in hand-written SQL views (distinct people vs. rows) | `indicator_definition`s with explicit `unit`, computed by the generic engine |
| 5 Sahel Horan indicators with no form, entered on a manual screen | indicators of kind `manual`, entered as `manual_value`s |
| 9 Ramtha indicators waiting on a definition the M&E lead must decide | blocking `open_question`s; those indicators show `not_computable` with the reason |
| Dashboard explaining why a figure is missing | `indicator_value.status` + `reason` |
| Evidence files (photos compressed on upload) | `evidence` + `file`, with image compression and verification gaps |
| Quarterly return for the donor | `report` for a locked quarterly `reporting_period` |
| Public sites per municipality (trainings, markets, advisory, "my applications") | the public portal per component (`public_slug`), public forms and listings, `participant` role |
| Indicator and data dictionary documents written by hand | generated indicator reference sheets and data dictionary |
| English/Arabic with right-to-left | project `languages` = `["en","ar"]`; labels translated in every schema |

### 25.2 The same platform, a different organization

To show it isn't a template: a consulting firm with three projects, none like ENABEL.

| Project | Framework input | What the AI produces |
|---|---|---|
| Maternal health in two countries | a donor-style performance monitoring plan in Word plus indicator reference sheets as PDFs | two components (one per country); entity types `health_facility` and `household`; breakdowns by district and facility type; ratio indicators ("% of births attended by skilled staff") with `latest` aggregation |
| Rural road rehabilitation | a 4×4 logframe as a scanned PDF | one component; entity type `road_segment`; `sum` of kilometres rehabilitated; `milestone` indicators ("maintenance committee established"); no public portal |
| Youth employment | a Theory of Change in PowerPoint plus an existing questionnaire as `.xls` | the questionnaire converted to a survey; a register of training cohorts; ratio "% employed 6 months after training" using `require_in`; a public application form for new cohorts |

Same tables, same engine, same screens. Only the rows differ.
