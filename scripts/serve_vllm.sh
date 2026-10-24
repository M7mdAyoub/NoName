#!/usr/bin/env bash
# Serve Qwen3.5 with vLLM for this app (no Docker). Run it on a Linux machine with an NVIDIA GPU
# (or WSL2 with GPU support). See docs/VLLM.md for which model fits which GPU.
#
#   bash scripts/serve_vllm.sh                                        # FP8 model, 1 GPU, port 8001
#   MODEL=Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 bash scripts/serve_vllm.sh   # smaller GPU (24-32 GB)
#   GPUS=2 MODEL=Qwen/Qwen3.5-35B-A3B bash scripts/serve_vllm.sh      # full precision, 2 GPUs
#   API_KEY=some-secret bash scripts/serve_vllm.sh                    # require a key
#
# The first run installs vLLM into $VENV and downloads the model (tens of GB) from Hugging Face.
# Then the app needs, in its .env: LLM_BASE_URL=http://<this machine>:8001/v1 (and LLM_API_KEY
# if you set API_KEY). Check with: python scripts/check_llm.py
set -euo pipefail

MODEL="${MODEL:-Qwen/Qwen3.5-35B-A3B-FP8}"
SERVED_NAME="${SERVED_NAME:-qwen3.5}"    # must equal LLM_MODEL_EXTRACT in the app's .env
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8001}"                     # the app itself uses 8000
GPUS="${GPUS:-1}"                        # tensor parallel size: 1, 2, 4 or 8
MAX_LEN="${MAX_LEN:-32768}"              # context window; the app's prompts are much shorter
GPU_UTIL="${GPU_UTIL:-0.90}"
VENV="${VENV:-$HOME/.venvs/vllm}"

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "No NVIDIA driver found (nvidia-smi is missing). vLLM needs an NVIDIA GPU." >&2
  exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader

if [ ! -x "$VENV/bin/vllm" ]; then
  echo "Installing vLLM into $VENV (Qwen3.5 needs the nightly build) ..."
  if command -v uv >/dev/null 2>&1; then UV=(uv); else
    python3 -m pip install --user --quiet uv
    UV=(python3 -m uv)
  fi
  "${UV[@]}" venv "$VENV" --python 3.12
  "${UV[@]}" pip install --python "$VENV/bin/python" vllm --torch-backend=auto \
    --extra-index-url https://wheels.vllm.ai/nightly
fi

ARGS=(serve "$MODEL"
  --served-model-name "$SERVED_NAME"
  --host "$HOST" --port "$PORT"
  --tensor-parallel-size "$GPUS"
  --max-model-len "$MAX_LEN"
  --gpu-memory-utilization "$GPU_UTIL"
  --reasoning-parser qwen3        # any thinking goes to a separate field, never into the JSON
  --language-model-only)          # the app sends text only: skip the vision encoder, save memory
if [ -n "${API_KEY:-}" ]; then ARGS+=(--api-key "$API_KEY"); fi

echo "Serving $MODEL as '$SERVED_NAME' on http://$HOST:$PORT/v1 ($GPUS GPU(s)). Ctrl+C stops it."
exec "$VENV/bin/vllm" "${ARGS[@]}"
