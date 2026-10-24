# AI-Powered M&E Platform 

From a static Results Framework to a live tracking system: KPIs, field surveys and dashboards, generated and connected automatically ( YES ) .

## Problem Statement

Development projects define their KPIs in text-based Results Frameworks, but track them through a fragmented stack of survey tools, spreadsheets and Power BI dashboards. Turning a framework into a working M&E system is manual work: someone has to extract the indicators, design the surveys, build the database, map every survey field to an indicator and write the calculation rules. The result is a custom-built system for each project. It can't process qualitative feedback, it breaks whenever the project adapts, and it has to be rebuilt from scratch for the next project.

## Who It's For

Any organization that runs projects against a Results Framework: NGOs, consulting firms, companies, public bodies, donors and implementing agencies. One organization can run many projects, each with its own framework, donors and reporting cycle.

## Solution

An M&E platform with an open-weight AI model built in. The AI does the work that is normally done by hand for every project:

1. **Extract**: it reads the uploaded Results Framework and pulls out the structure, results and indicators.
2. **Generate**: it converts surveys that already exist in the file into digital forms, or designs new ones where none exist.
3. **Define**: it writes a calculation rule for every indicator and links each rule to specific form fields.
4. **Review**: everything it produces is a draft that the M&E lead checks, edits and publishes.
5. **Run**: once published, field workers collect data, KPIs are calculated automatically, and the dashboard updates. No developer is involved.
6. **Analyze**: the AI reads open-ended responses and delivers thematic insights on qualitative feedback.

## Core Principle: Dynamic Input, Fixed Core

- **The input is fully dynamic.** No template is required. A framework can be a logframe in Excel, a Theory of Change in Word, a PDF annex from a donor or a messy sheet with merged cells. It can have any number of levels, any level names, any column layout and any language.
- **The core is fixed.** Inside the platform, every project is stored in the same generic structure (results, indicators, forms, entities, breakdown categories). The AI's job is to translate whatever comes in into that structure.

Because the core never changes, the dashboard, the calculation engine and the form renderer work for every project without new code. Adding a new organization or a completely different framework adds data, never database migrations or custom code.

## How It Works

### 1. Framework extraction

When a framework is uploaded, the AI:

1. **Reads the file**: turns Excel, Word or PDF into clean text and tables, including messy layouts.
2. **Finds the structure**: identifies the levels (whatever the framework calls them), the results and how they nest.
3. **Extracts each indicator**: name, unit, baseline, target, frequency, means of verification, data source and responsible party, from whatever columns the framework has.
4. **Writes the calculation rule**: what is counted (people, households, businesses, schools…), how (count, percentage, sum, average, milestone…) and which breakdowns apply.
5. **Builds the forms**: converts surveys already in the file, or designs new ones from the means of verification. Indicators that share a data source are grouped into one form, so field workers don't fill in several surveys for one visit.
6. **Links fields to indicators**: each calculation rule points to specific form fields.
7. **Flags gaps**: missing baselines, vague targets ("improved capacity") and unclear definitions become open questions for the M&E lead instead of silent guesses.

All AI output uses structured JSON that must match a fixed schema, and it is validated before it reaches review.

### 2. Review and publishing

Nothing the AI produces goes live on its own. The M&E lead reviews the extracted framework, the indicator definitions and the forms, answers the open questions, edits anything wrong and publishes. Every AI suggestion and every approval is kept as an audit trail.

### 3. Data collection

Published forms are rendered dynamically from their JSON schema, so a new or changed form needs no code. Forms work on phones and can collect data offline, syncing when a connection is available. Each submission is stored as JSON together with the form version it was filled in on, so changing a survey never breaks past data. Submissions can be linked to an entity (a person, household, business…), so an indicator can count distinct entities across several forms.

### 4. KPI calculation

A single generic calculation engine reads each indicator's approved calculation rule and computes its value per reporting period and per breakdown. **The AI never calculates the figures itself**: it proposes the rule, a human approves it, and the engine produces the numbers deterministically. Indicators with no data-collection form can be entered manually.

### 5. Dashboard and reporting

The dashboard shows each indicator's actual value against its baseline and target, broken down by the project's categories, with clear flags for indicators that can't be calculated yet and why. Periodic reports for donors are produced from the same figures.

### 6. Qualitative analysis

The AI reads open-ended survey responses and other unstructured feedback, and gives M&E planners thematic insights inside the platform. When the model is self-hosted, this data never leaves the platform.

### 7. Framework revisions

When a framework is revised mid-project, the AI compares the new version with the old one and proposes the changes: updated targets, new or removed indicators, new or changed forms. Forms get new versions, and past data stays tied to the version it was collected with.

## Universal by Design

| What varies between projects | How the platform handles it |
|---|---|
| Framework levels (Impact / Outcome / Output, Goal / Purpose / Output, SO / IR, Theory of Change…) | Each project defines its own level names; results form a tree of any depth |
| What is counted (people, households, businesses, schools, facilities, km of road…) | Entity types are defined per project, each with its own attributes |
| Breakdowns (sex, age, disability, region, sector, income group…) | Breakdown categories and their values are data per project, not columns |
| Indicator types | Counts, percentages and ratios, sums and averages, yes/no milestones, composite indexes, qualitative and manually entered indicators |
| Who runs and sees the project | An owner organization plus optional client and donor organizations; outside users (donors, partners, evaluators) get access to specific projects only |
| Reporting cycle | Set per project (monthly, quarterly, annual…) |
| Language and currency | Set per organization or project, including right-to-left languages |
| Comparing projects | An indicator library of standard indicators (SDG, donor core indicators or an organization's own set) lets results roll up across projects |

## Data Model

Every project is stored as rows in the same tables. JSON columns hold whatever varies between projects.

**Tenancy and access**
- `organization` → `project` (owner organization, plus optional client and donor organizations)
- `membership`: user, project and role. Access is enforced per project at the database level.

**The framework**
- `framework_document`: the uploaded file, its version and its processing status
- `framework_level`: the project's own level names
- `result`: the results tree (each row points to its parent)
- `indicator`: code, name, unit, baseline, target, status (draft / approved) and a `definition` JSON holding the calculation rule
- `indicator_library`: standard indicators that project indicators can link to
- `reporting_period`

**Data collection**
- `entity_type`: what the project counts, with an attribute schema in JSON
- `entity`: one row per real person, household, business…, with an identity key and its attributes in JSON
- `disaggregation`: the project's breakdown categories and their values
- `form` → `form_version` (with its `schema` JSON)
- `submission`: form version, entity, `data` JSON, who collected it and when

**AI and calculation**
- `ai_suggestion`: every draft the AI produces, with its review status and who approved it
- `open_question`: gaps and ambiguities flagged for the M&E lead
- `indicator_value`: calculated results per indicator, period and breakdown

**Rules carried over from earlier projects**
- Soft delete everywhere; nothing is ever hard-deleted.
- An insert-only audit log.
- Migrations are append-only: an applied migration is never edited, and every change is a new migration.

## Architecture & Tools

The platform runs on a self-hosted stack: a responsive front-end, a back-end API, an open-weight LLM and a database.

| Layer | Tool | Role |
|---|---|---|
| Front-end | Responsive web app | Upload frameworks, review AI drafts, render dynamic forms (offline-capable), show the dashboard |
| Back-end | API server | Orchestrates the AI pipeline, validates AI output, ingests submissions, runs the calculation engine |
| AI | Qwen (open-weight), served through an OpenAI-compatible API | Framework extraction, form generation, calculation rules, revision comparison, qualitative analysis |
| Database | PostgreSQL with JSONB (recommended, see Open Decisions) | Stores every project in one generic schema; JSON columns hold forms, submissions and calculation rules; row-level security keeps each organization's data separate |

## Open Decisions

- **Database engine.** PostgreSQL with JSONB is recommended: many organizations and field workers write at the same time, and row-level security keeps their data apart. SQLite was considered, but it allows only one writer at a time and has no row-level security, so it only suits a single-machine demo. Starting point: a local Supabase instance, which can be self-hosted later.
- **Where Qwen runs.** Self-hosted (for example with vLLM or Ollama) keeps all data inside the platform. A hosted Qwen API is simpler to start with, but project data would then be sent to a third party.

## First Milestone

1. Write the first migrations: tenancy and framework, then data collection.
2. Enter one real indicator from an existing framework by hand, collect test submissions, and confirm that the generic engine calculates it correctly, before any AI is involved.
3. Connect the AI so that it fills those same tables from an uploaded framework.
