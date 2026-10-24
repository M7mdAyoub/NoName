# AI-powered M&E platform

Upload a project's results framework (logframe) and get a working monitoring system. An LLM
drafts the results, indicators, data-collection forms and calculation rules; a person reviews
and publishes them; field data comes in through the forms; and a deterministic engine computes
every indicator for the dashboard. **The AI proposes, a person approves, the engine
calculates**: no published number ever comes from the model.

Stack: Python 3.12 · FastAPI · SQLite · any OpenAI-compatible LLM (e.g. Qwen via Ollama or
vLLM). A built-in mock model means everything runs without one.

## Setup
Requires Python 3.12 or newer.

```bash
git clone https://github.com/M7mdAyoub/NoName.git
cd NoName
python -m venv .venv
```
Activate the environment (Windows: `.venv\Scripts\activate`, macOS/Linux:
`source .venv/bin/activate`), then install and configure:
```bash
pip install -r requirements.txt
pip install -e .
cp .env.example .env
```
Edit `.env` if needed (the defaults work for local use with the mock model).

## Run
```bash
python scripts/dev.py
```
This applies the database migrations and starts the API on http://127.0.0.1:8000 with the
background worker. Open that address for the demo page (upload a framework, review and publish,
submit data, view the dashboard) or http://127.0.0.1:8000/docs for the API.

A sample framework is in `tests/fixtures/sample_logframe.xlsx`. To run the whole flow
end-to-end against a running API on an empty database:
```bash
python scripts/demo.py
```

## Using a real model
Set these in `.env`:
```
LLM_MODE=real
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL_EXTRACT=qwen2.5:14b-instruct
```

## Checks
```bash
python scripts/check.py
```
Runs lint, formatting, type checks, tests, and the migration and route checks.

More detail: [docs/MVP.md](docs/MVP.md) (scope and rules) and [docs/HANDOFF.md](docs/HANDOFF.md)
(build notes and formats).
