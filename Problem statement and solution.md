# AI-Powered M&E Platform 

From a static Results Framework to a live tracking system: KPIs, field surveys and dashboards, generated and connected automatically ( YES ) .

## Problem Statement

Development projects define their KPIs in text-based Results Frameworks, but track them through a fragmented stack of survey tools and Power BI dashboards. This disconnect forces teams to extract indicators and map survey variables by hand. The result is rigid data pipelines that can't process qualitative feedback and that break whenever a project adapts.

## Solution

An AI-powered pipeline that turns static Results Frameworks into live tracking systems:

1. **Extract**: an LLM reads the planning document and pulls out the KPIs.
2. **Generate**: it auto-generates the field surveys needed to measure those KPIs, as JSON schemas.
3. **Map**: survey variables are linked back to their KPIs automatically.
4. **Adapt**: form structures and field responses are both stored as flexible JSON, so the database absorbs project changes without rigid migrations.
5. **Analyze**: AI is embedded in the dashboard, giving M&E teams a smart interface to query the data and analyze both quantitative metrics and qualitative community feedback.

The platform is universal and dynamic: it isn't built around one project's indicators, but adapts to whatever Results Framework is uploaded.

## Architecture & Tools

The application runs on a unified, fully self-hosted stack: a responsive front-end and a back-end that orchestrates an open-weight LLM (**Qwen**, served through an OpenAI-compatible API) and a **SQLite** database.

### End-to-end flow

1. **Upload**: the user uploads a Results Framework, and the front-end passes the document to the back-end.
2. **KPI extraction & survey generation**: Qwen extracts the core KPIs and generates a matching field survey as a JSON schema.
3. **Dynamic forms**: the front-end renders that JSON schema into an interactive data-collection form.
4. **Schema-less storage**: field submissions are stored as raw JSON in a SQLite text column, so surveys can change without any database migrations.
5. **KPI mapping**: using SQLite's built-in JSON functions (`json_extract`, etc.), the back-end maps survey variables back to the original KPIs to populate the live dashboard.
6. **Qualitative insights**: Qwen queries the same JSON fields to analyze unstructured, open-ended feedback and delivers thematic insights directly to M&E planners, without the data leaving the platform.

### Stack summary

| Layer | Tool | Role |
|---|---|---|
| Front-end | Responsive web app | Upload documents, render dynamic survey forms, display the KPI dashboard |
| Back-end | API server | Orchestrates the LLM, form generation, data ingestion and KPI mapping |
| AI | Qwen (open-weight, self-hosted) | KPI extraction, survey schema generation, qualitative/thematic analysis |
| Database | SQLite (JSON1) | Stores form schemas and responses as JSON; computes KPIs with JSON queries |
