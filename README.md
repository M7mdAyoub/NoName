# AI-powered M&E platform

Upload a project's results framework (logframe) and get a working monitoring system. An LLM
drafts the results, indicators, data-collection forms and calculation rules; a person reviews
and publishes them; field data comes in through the forms; and a deterministic engine computes
every indicator for the dashboard. **The AI proposes, a person approves, the engine
calculates**: no published number ever comes from the model.

Stack: Python 3.12 · FastAPI · SQLite · any OpenAI-compatible LLM (e.g. Qwen via Ollama or
vLLM). A built-in mock model means everything runs without one.

## Quick start
Needs **Git**, **Python 3.12+** and **Node.js 20+** (for the Arabic frontend). Nothing else.

```bash
git clone https://github.com/M7mdAyoub/Qiyas.git
cd Qiyas
python scripts/setup.py
```
`setup.py` creates `.venv` and installs the Python packages into it, creates `.env` from
`.env.example`, sets up the database and builds the frontend. Then start the app:

```bash
.venv/Scripts/python scripts/dev.py      # Windows
.venv/bin/python scripts/dev.py          # macOS / Linux
```
and open **http://127.0.0.1:8000/** (the Arabic app, served at `/app/`). Try it with
`tests/fixtures/sample_logframe_with_forms.xlsx`. Without a language model the app reads the files
with built-in rules and says so on screen; to use Qwen3.5 see [Using a real model](#using-a-real-model-vllm).

Also available: http://127.0.0.1:8000/classic (the earlier English demo page) and
http://127.0.0.1:8000/docs (the API). Run every other script the same way, with the `.venv` Python
(`.venv/Scripts/python scripts/check.py`, ...). After changing the frontend, rebuild it with
`npm run build` in `outputs/impactos-frontend` (or run `scripts/setup.py` again).

To work on the frontend with hot reload, run `scripts/dev.py --frontend` and open
http://127.0.0.1:5173/. The dev server forwards API calls to port 8000 (set `VITE_API_TARGET` to
use another server); `npm test` in `outputs/impactos-frontend` runs its tests.

The flow in the app: **Framework** (upload and extract) → **Review** (results, indicators, rules,
open questions, publish) → **Form builder** → **Forms and data** (fill published forms) →
**Overview** (KPI tracking).

A sample framework is in `tests/fixtures/sample_logframe.xlsx`;
`tests/fixtures/sample_logframe_with_forms.xlsx` adds two form sheets. Forms already in the
uploaded files (one sheet or table per questionnaire) become the project's forms, and the AI only
designs forms for indicators none of them covers. The form builder (with a live preview) is for
checking and editing those forms or building new ones. The overview tracks every KPI against its
target and shows which form feeds it. To run the whole flow
end-to-end against a running API on an empty database:
```bash
python scripts/demo.py
```

## Using a real model (vLLM)
The app talks to any OpenAI-compatible server; the setup here is **Qwen3.5-35B-A3B on vLLM**, without
Docker. It needs an NVIDIA GPU with about 24–48 GB of memory (depending on the model build), on
Linux or WSL2. Full guide: [docs/VLLM.md](docs/VLLM.md). In short:

```bash
bash scripts/serve_vllm.sh            # on the GPU machine: installs vLLM, downloads and serves the model on :8001
```
then in the app's `.env` set `LLM_BASE_URL=http://<gpu-machine>:8001/v1` (or `http://localhost:8001/v1`
on the same machine), check it with `python scripts/check_llm.py`, and restart the app.

## Checks
```bash
python scripts/check.py
```
Runs lint, formatting, type checks, tests, and the migration and route checks.

More detail: [docs/MVP.md](docs/MVP.md) (scope and rules) and [docs/HANDOFF.md](docs/HANDOFF.md)
(build notes and formats).
