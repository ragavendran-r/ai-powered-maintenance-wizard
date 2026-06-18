#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
if [[ -x "${ROOT_DIR}/.venv-peft/bin/python" ]]; then
  DEFAULT_CONVERT_PYTHON="${ROOT_DIR}/.venv-peft/bin/python"
else
  DEFAULT_CONVERT_PYTHON="python3"
fi
SERVER_BIN="${LLAMA_CPP_SERVER_BIN:-llama-server}"
HOST="${LLAMA_CPP_HOST:-127.0.0.1}"
PORT="${LLAMA_CPP_PORT:-8080}"
BASE_URL="http://${HOST}:${PORT}"
PID_FILE="${LLAMA_CPP_PID_FILE:-backend/data/runtime/llama_cpp_adapter.pid}"
LOG_FILE="${LLAMA_CPP_LOG_FILE:-backend/data/runtime/llama_cpp_adapter.log}"
ADAPTER_GGUF="${LLAMA_CPP_ADAPTER_GGUF_PATH:-}"
BASE_MODEL="${LLAMA_CPP_BASE_MODEL_PATH:-}"
HF_REPO="${LLAMA_CPP_HF_REPO:-}"
HF_FILE="${LLAMA_CPP_HF_FILE:-}"
ALIAS="${MW_ADAPTER_SERVED_MODEL_NAME:-${LLAMA_CPP_ALIAS:-}}"
CONVERT_PYTHON="${LLAMA_CPP_CONVERT_PYTHON:-${DEFAULT_CONVERT_PYTHON}}"

if [[ -z "${ALIAS}" ]]; then
  echo "MW_ADAPTER_SERVED_MODEL_NAME or LLAMA_CPP_ALIAS is required" >&2
  exit 2
fi

if [[ -z "${BASE_MODEL}" && -z "${HF_REPO}" ]]; then
  echo "LLAMA_CPP_BASE_MODEL_PATH or LLAMA_CPP_HF_REPO is required for the GGUF base model" >&2
  exit 2
fi

if [[ -n "${BASE_MODEL}" && ! -f "${BASE_MODEL}" ]]; then
  echo "LLAMA_CPP_BASE_MODEL_PATH does not exist: ${BASE_MODEL}" >&2
  exit 2
fi

if ! command -v "${SERVER_BIN}" >/dev/null 2>&1; then
  echo "llama.cpp server binary not found: ${SERVER_BIN}" >&2
  echo "Set LLAMA_CPP_SERVER_BIN or install llama-server on PATH." >&2
  exit 2
fi

mkdir -p "$(dirname "${PID_FILE}")" "$(dirname "${LOG_FILE}")"

if [[ -z "${ADAPTER_GGUF}" && -n "${MW_ADAPTER_ARTIFACT_URI:-}" && -f "${MW_ADAPTER_ARTIFACT_URI}" ]]; then
  ADAPTER_GGUF="${MW_ADAPTER_ARTIFACT_URI}"
fi

if [[ -z "${ADAPTER_GGUF}" && -n "${MW_ADAPTER_ARTIFACT_URI:-}" && -f "${MW_ADAPTER_ARTIFACT_URI%/}/adapter.gguf" ]]; then
  ADAPTER_GGUF="${MW_ADAPTER_ARTIFACT_URI%/}/adapter.gguf"
fi

if [[ -z "${ADAPTER_GGUF}" ]]; then
  CONVERT_SCRIPT="${LLAMA_CPP_CONVERT_LORA_SCRIPT:-}"
  if [[ -z "${CONVERT_SCRIPT}" ]]; then
    cat >&2 <<'MSG'
LLAMA_CPP_ADAPTER_GGUF_PATH is empty and LLAMA_CPP_CONVERT_LORA_SCRIPT is not set.
Set LLAMA_CPP_ADAPTER_GGUF_PATH to a converted GGUF LoRA adapter, or point
LLAMA_CPP_CONVERT_LORA_SCRIPT at llama.cpp/convert_lora_to_gguf.py.
MSG
    exit 2
  fi
  if [[ -z "${MW_ADAPTER_ARTIFACT_URI:-}" || ! -d "${MW_ADAPTER_ARTIFACT_URI}" ]]; then
    echo "MW_ADAPTER_ARTIFACT_URI must point to the trained PEFT adapter directory for conversion" >&2
    exit 2
  fi
  if [[ ! -f "${CONVERT_SCRIPT}" ]]; then
    echo "LLAMA_CPP_CONVERT_LORA_SCRIPT does not exist: ${CONVERT_SCRIPT}" >&2
    exit 2
  fi
  ADAPTER_GGUF="${MW_ADAPTER_ARTIFACT_URI%/}/adapter.gguf"
  "${CONVERT_PYTHON}" "${CONVERT_SCRIPT}" "${MW_ADAPTER_ARTIFACT_URI}" --outfile "${ADAPTER_GGUF}"
fi

if [[ ! -f "${ADAPTER_GGUF}" ]]; then
  echo "GGUF LoRA adapter does not exist: ${ADAPTER_GGUF}" >&2
  exit 2
fi

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}")"
  if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" >/dev/null 2>&1; then
    kill "${OLD_PID}" >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do
      kill -0 "${OLD_PID}" >/dev/null 2>&1 || break
      sleep 0.25
    done
  fi
fi

read -r -a EXTRA_ARGS <<< "${LLAMA_CPP_EXTRA_ARGS:-}"
MODEL_ARGS=()
if [[ -n "${BASE_MODEL}" ]]; then
  MODEL_ARGS=(--model "${BASE_MODEL}")
else
  MODEL_ARGS=(--hf-repo "${HF_REPO}")
  if [[ -n "${HF_FILE}" ]]; then
    MODEL_ARGS+=(--hf-file "${HF_FILE}")
  fi
fi

nohup "${SERVER_BIN}" \
  "${MODEL_ARGS[@]}" \
  --lora "${ADAPTER_GGUF}" \
  --alias "${ALIAS}" \
  --host "${HOST}" \
  --port "${PORT}" \
  ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"} \
  >"${LOG_FILE}" 2>&1 </dev/null &
SERVER_PID="$!"
echo "${SERVER_PID}" > "${PID_FILE}"
disown "${SERVER_PID}" >/dev/null 2>&1 || true

for _ in $(seq 1 120); do
  if curl -fsS "${BASE_URL}/v1/health" >/dev/null 2>&1 || curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    echo "llama.cpp adapter runtime ready at ${BASE_URL}/v1 with alias ${ALIAS}"
    exit 0
  fi
  if ! kill -0 "${SERVER_PID}" >/dev/null 2>&1; then
    echo "llama-server exited before becoming healthy; see ${LOG_FILE}" >&2
    tail -80 "${LOG_FILE}" >&2 || true
    exit 1
  fi
  sleep 1
done

echo "llama-server did not become healthy at ${BASE_URL}; see ${LOG_FILE}" >&2
tail -80 "${LOG_FILE}" >&2 || true
exit 1
