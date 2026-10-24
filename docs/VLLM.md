# Running the language model with vLLM (no Docker)

The app works without a model: with `LLM_BASE_URL` empty it reads frameworks and forms with its
built-in rules (the upload screen says "وضع الاختبار"). For real AI extraction, run
**Qwen3.5-35B-A3B** with [vLLM](https://docs.vllm.ai) on a machine with an NVIDIA GPU and point
the app at it. The app only needs the URL; it can run on the same machine or on any laptop that
can reach the GPU server.

## 1. Pick the model for your GPU

The model has 35 B parameters (3 B active per token, so it is fast once loaded), but all weights
must fit in GPU memory, plus room for the context cache.

| `MODEL` | Weights | GPU memory needed |
|---|---|---|
| `Qwen/Qwen3.5-35B-A3B-FP8` (default) | about 36 GB | one 48 GB GPU (L40S, RTX 6000 Ada, A6000) or an 80 GB one (A100, H100) |
| `Qwen/Qwen3.5-35B-A3B-GPTQ-Int4` | about 20 GB | one 24–32 GB GPU (RTX 4090, RTX 5090) |
| `Qwen/Qwen3.5-35B-A3B` (full precision) | about 72 GB | two 80 GB GPUs (`GPUS=2`) |

A laptop without an NVIDIA GPU cannot run it (vLLM needs NVIDIA and Linux). Use a desktop with a
big GPU, a university server, or a rented cloud GPU (RunPod, Lambda, Vast.ai, … — pick an Ubuntu
image with an NVIDIA driver).

## 2. Start vLLM on the GPU machine

Needs: Linux (or WSL2 with GPU support on Windows), an NVIDIA driver (`nvidia-smi` works),
Python 3.12 available to `uv` (the script installs `uv` if needed), internet access to download
the model from Hugging Face.

```bash
git clone https://github.com/M7mdAyoub/Qiyas.git
cd Qiyas
bash scripts/serve_vllm.sh
```

The first run installs vLLM (the nightly build: Qwen3.5 needs it) into `~/.venvs/vllm` and
downloads the model, which takes a while. It is ready when the log says
`Application startup complete`. It serves an OpenAI-compatible API at
`http://<machine>:8001/v1`.

Options (environment variables, all optional):

| Variable | Default | What it does |
|---|---|---|
| `MODEL` | `Qwen/Qwen3.5-35B-A3B-FP8` | Which weights to load (see the table above). |
| `GPUS` | `1` | Number of GPUs to split the model over (1, 2, 4 or 8). |
| `PORT` | `8001` | Port of the model API (the app itself uses 8000). |
| `SERVED_NAME` | `qwen3.5` | Name the app asks for; must equal `LLM_MODEL_EXTRACT` in `.env`. |
| `MAX_LEN` | `32768` | Context window. Lower it if you run out of GPU memory. |
| `API_KEY` | none | Require this key on every request (set `LLM_API_KEY` to the same value). |

Example: `MODEL=Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 API_KEY=change-this bash scripts/serve_vllm.sh`.

## 3. Point the app at it

On the machine that runs the app, in `.env` (created by `python scripts/setup.py`):

```
LLM_BASE_URL=http://localhost:8001/v1        # same machine; else http://<gpu-server>:8001/v1
LLM_API_KEY=change-this                      # only if you started vLLM with API_KEY
```

The other model settings in `.env.example` already match the script: `LLM_MODEL_EXTRACT=qwen3.5`
and `LLM_EXTRA_BODY={"chat_template_kwargs": {"enable_thinking": false}}`, which turns off
Qwen3.5's thinking step (the app asks for short JSON answers, and thinking would make every call
much slower).

Check the connection, then restart the app:

```bash
python scripts/check_llm.py      # Windows: .venv\Scripts\python scripts\check_llm.py
```

It sends one small request through the app's own client and says what to fix if it fails. After
a restart, new uploads are extracted by the model: the upload screen no longer shows the test-mode
notice, and "إعادة الاستخراج" re-reads an earlier upload with it (before anything is published).

## Hosted instead: Groq (no GPU)

Any OpenAI-compatible service works. For Groq, in `.env` (key from https://console.groq.com/keys):

```
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_API_KEY=gsk_...
LLM_MODEL_EXTRACT=qwen/qwen3.8-27b
LLM_EXTRA_BODY={"reasoning_effort": "none"}
LLM_STRICT_SCHEMA=true
LLM_MAX_CONCURRENCY=1
LLM_IS_EXTERNAL=true
```

`LLM_STRICT_SCHEMA=true` is needed: in its default "best effort" JSON mode Groq often returns
broken JSON for this model. The client waits and resends when Groq answers 429 (rate limit); on
the free tier a full extraction can still take a few minutes. Uploaded documents are sent to Groq.

## Remote GPU servers: keep the port private

Uploaded documents are sent to the model server (answers in fields marked as personal data never
are). Do not open port 8001 to the internet without `API_KEY`. The simplest safe setup is an SSH
tunnel from the app machine:

```bash
ssh -N -L 8001:localhost:8001 user@gpu-server
```

and then `LLM_BASE_URL=http://localhost:8001/v1`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `check_llm.py`: cannot reach the server | vLLM still starting, wrong host/port, firewall, or the SSH tunnel is down. |
| 404 / model not found | `LLM_MODEL_EXTRACT` must equal `SERVED_NAME` (the script prints the name). |
| 401 | `LLM_API_KEY` must equal the `API_KEY` vLLM was started with. |
| CUDA out of memory at start | Use a smaller `MODEL`, lower `MAX_LEN`, or add GPUs (`GPUS=2`). |
| Unknown or unsupported model architecture | An old vLLM: delete `~/.venvs/vllm` and run the script again (it installs the nightly build). |
| Every call is slow | Check that `LLM_EXTRA_BODY` in `.env` turns thinking off; check the GPU is used (`nvidia-smi`). |
| Extraction fails after 3 attempts per step | See the upload's `extraction.problems`; lower `LLM_MAX_CONCURRENCY` if the GPU is overloaded. |
