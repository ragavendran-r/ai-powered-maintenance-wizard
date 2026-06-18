#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEFAULT_MODEL_ALIAS="maintenance-wizard-qwen-lora-LJOB-7B7B7B7B7B7B"
DEFAULT_BASE_MODEL_PATH="${HOME}/.lmstudio/models/Qwen/Qwen2.5-7B-Instruct-GGUF/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf"
DEFAULT_HF_REPO="Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"
DEFAULT_PEFT_ADAPTER_DIR="${ROOT_DIR}/backend/data/learning_adapters/LJOB-7B7B7B7B7B7B/adapter"
DEFAULT_CONVERT_PYTHON="python3"
if [[ -x "${ROOT_DIR}/.venv-peft/bin/python" ]]; then
  DEFAULT_CONVERT_PYTHON="${ROOT_DIR}/.venv-peft/bin/python"
fi

load_env_defaults() {
  local env_file="$1"
  local line key value
  while IFS= read -r line || [[ -n "${line}" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -z "${line}" || "${line}" == \#* || "${line}" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    key="${key%"${key##*[![:space:]]}"}"
    value="${value#"${value%%[![:space:]]*}"}"
    value="${value%"${value##*[![:space:]]}"}"
    [[ "${key}" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ -z "${!key+x}" ]]; then
      if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
        value="${value:1:${#value}-2}"
      fi
      export "${key}=${value}"
    fi
  done < "${env_file}"
}

if [[ -f "${ROOT_DIR}/.env" ]]; then
  load_env_defaults "${ROOT_DIR}/.env"
fi

SERVER_BIN="${LLAMA_CPP_SERVER_BIN:-llama-server}"
HOST="${LLAMA_CPP_HOST:-127.0.0.1}"
PORT="${LLAMA_CPP_PORT:-8080}"
BASE_URL="http://${HOST}:${PORT}"
BASE_MODEL="${LLAMA_CPP_BASE_MODEL_PATH:-}"
if [[ -z "${BASE_MODEL}" && -f "${DEFAULT_BASE_MODEL_PATH}" ]]; then
  BASE_MODEL="${DEFAULT_BASE_MODEL_PATH}"
fi
HF_REPO="${LLAMA_CPP_HF_REPO:-${DEFAULT_HF_REPO}}"
HF_FILE="${LLAMA_CPP_HF_FILE:-}"
ADAPTER_GGUF="${LLAMA_CPP_ADAPTER_GGUF_PATH:-}"
CONVERT_SCRIPT="${LLAMA_CPP_CONVERT_LORA_SCRIPT:-}"
CONVERT_PYTHON="${LLAMA_CPP_CONVERT_PYTHON:-${DEFAULT_CONVERT_PYTHON}}"
PEFT_ADAPTER_DIR="${MW_ADAPTER_ARTIFACT_URI:-${DEFAULT_PEFT_ADAPTER_DIR}}"
ALIAS="${LLAMA_CPP_ALIAS:-${OPENAI_MODEL:-${DEFAULT_MODEL_ALIAS}}}"
PID_FILE="${LLAMA_CPP_PID_FILE:-${ROOT_DIR}/backend/data/runtime/llama_cpp_adapter.pid}"
LOG_FILE="${LLAMA_CPP_LOG_FILE:-${ROOT_DIR}/backend/data/runtime/llama_cpp_adapter.log}"
CTX_SIZE="${LLAMA_CPP_CTX_SIZE:-4096}"
PARALLEL="${LLAMA_CPP_PARALLEL:-2}"
N_GPU_LAYERS="${LLAMA_CPP_N_GPU_LAYERS:-}"
EXTRA_ARGS="${LLAMA_CPP_EXTRA_ARGS:-}"

usage() {
  cat <<EOF
Usage: scripts/peft/start_llama_cpp_qwen_adapter.sh [--check|--stop|--status]

Starts llama.cpp's OpenAI-compatible llama-server with a Qwen2.5 GGUF base model
and a GGUF LoRA adapter. The script reads .env first, then environment overrides.

Required model inputs:
  Either LLAMA_CPP_BASE_MODEL_PATH=/path/to/qwen2.5-7b-instruct.gguf
  or     LLAMA_CPP_HF_REPO=Qwen/Qwen2.5-7B-Instruct-GGUF:Q4_K_M with optional LLAMA_CPP_HF_FILE=...

Required adapter input:
  LLAMA_CPP_ADAPTER_GGUF_PATH=/path/to/adapter.gguf
  or MW_ADAPTER_ARTIFACT_URI=/path/to/peft/adapter plus LLAMA_CPP_CONVERT_LORA_SCRIPT=/path/to/llama.cpp/convert_lora_to_gguf.py

Useful variables:
  LLAMA_CPP_SERVER_BIN       llama-server binary path or command name
  LLAMA_CPP_CONVERT_PYTHON   Python executable for adapter conversion; defaults to .venv-peft/bin/python when present
  LLAMA_CPP_ALIAS            served model alias; defaults to OPENAI_MODEL or ${DEFAULT_MODEL_ALIAS}
  LLAMA_CPP_HOST             default 127.0.0.1
  LLAMA_CPP_PORT             default 8080
  LLAMA_CPP_CTX_SIZE         default 4096
  LLAMA_CPP_PARALLEL         default 2
  LLAMA_CPP_N_GPU_LAYERS     optional Metal/CUDA offload layer count, for example 99
  LLAMA_CPP_EXTRA_ARGS       optional extra llama-server flags

Commands:
  --check   Validate inputs and print the resolved llama-server command.
  --status  Check the local llama.cpp endpoint and model list.
  --stop    Stop the pid recorded in LLAMA_CPP_PID_FILE.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 2
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

stop_server() {
  if [[ ! -f "${PID_FILE}" ]]; then
    echo "No llama.cpp pid file found: ${PID_FILE}"
    return 0
  fi
  local pid
  pid="$(cat "${PID_FILE}")"
  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" >/dev/null 2>&1; then
    echo "No running llama.cpp process for pid file: ${PID_FILE}"
    rm -f "${PID_FILE}"
    return 0
  fi
  echo "Stopping llama.cpp process ${pid}"
  kill "${pid}" >/dev/null 2>&1 || true
  for _ in $(seq 1 30); do
    kill -0 "${pid}" >/dev/null 2>&1 || break
    sleep 0.2
  done
  rm -f "${PID_FILE}"
}

status_server() {
  echo "Endpoint: ${BASE_URL}/v1"
  if curl -fsS "${BASE_URL}/v1/models"; then
    echo
    return 0
  fi
  if curl -fsS "${BASE_URL}/health"; then
    echo
    return 0
  fi
  echo "llama.cpp endpoint is not responding."
  return 1
}

resolve_adapter() {
  if [[ -n "${ADAPTER_GGUF}" ]]; then
    [[ -f "${ADAPTER_GGUF}" ]] || die "LLAMA_CPP_ADAPTER_GGUF_PATH does not exist: ${ADAPTER_GGUF}"
    return 0
  fi

  [[ -n "${PEFT_ADAPTER_DIR}" ]] || die "Set LLAMA_CPP_ADAPTER_GGUF_PATH, or set MW_ADAPTER_ARTIFACT_URI plus LLAMA_CPP_CONVERT_LORA_SCRIPT."
  [[ -d "${PEFT_ADAPTER_DIR}" ]] || die "MW_ADAPTER_ARTIFACT_URI is not a directory: ${PEFT_ADAPTER_DIR}"
  [[ -n "${CONVERT_SCRIPT}" ]] || die "LLAMA_CPP_CONVERT_LORA_SCRIPT is required to convert a PEFT adapter directory."
  [[ -f "${CONVERT_SCRIPT}" ]] || die "LLAMA_CPP_CONVERT_LORA_SCRIPT does not exist: ${CONVERT_SCRIPT}"

  ADAPTER_GGUF="${PEFT_ADAPTER_DIR%/}/adapter.gguf"
  if [[ ! -f "${ADAPTER_GGUF}" ]]; then
    echo "Converting PEFT adapter to GGUF: ${ADAPTER_GGUF}"
    "${CONVERT_PYTHON}" "${CONVERT_SCRIPT}" "${PEFT_ADAPTER_DIR}" --outfile "${ADAPTER_GGUF}"
  fi
}

build_command() {
  require_command "${SERVER_BIN}"
  [[ -n "${ALIAS}" ]] || die "LLAMA_CPP_ALIAS or OPENAI_MODEL cannot be empty."

  MODEL_ARGS=()
  if [[ -n "${BASE_MODEL}" ]]; then
    [[ -f "${BASE_MODEL}" ]] || die "LLAMA_CPP_BASE_MODEL_PATH does not exist: ${BASE_MODEL}"
    MODEL_ARGS=(--model "${BASE_MODEL}")
  else
    [[ -n "${HF_REPO}" ]] || die "Set LLAMA_CPP_BASE_MODEL_PATH or LLAMA_CPP_HF_REPO for the Qwen2.5 GGUF base model."
    MODEL_ARGS=(--hf-repo "${HF_REPO}")
    if [[ -n "${HF_FILE}" ]]; then
      MODEL_ARGS+=(--hf-file "${HF_FILE}")
    fi
  fi

  resolve_adapter

  SERVER_ARGS=(
    "${SERVER_BIN}"
    "${MODEL_ARGS[@]}"
    --lora "${ADAPTER_GGUF}"
    --alias "${ALIAS}"
    --host "${HOST}"
    --port "${PORT}"
    --ctx-size "${CTX_SIZE}"
    --parallel "${PARALLEL}"
  )
  if [[ -n "${N_GPU_LAYERS}" ]]; then
    SERVER_ARGS+=(--n-gpu-layers "${N_GPU_LAYERS}")
  fi
  if [[ -n "${EXTRA_ARGS}" ]]; then
    read -r -a EXTRA_ARG_ARRAY <<< "${EXTRA_ARGS}"
    SERVER_ARGS+=("${EXTRA_ARG_ARRAY[@]}")
  fi
}

case "${1:-}" in
  -h|--help)
    usage
    exit 0
    ;;
  --stop)
    stop_server
    exit 0
    ;;
  --status)
    status_server
    exit $?
    ;;
esac

build_command

if [[ "${1:-}" == "--check" ]]; then
  printf 'Resolved command:'
  printf ' %q' "${SERVER_ARGS[@]}"
  printf '\n'
  echo "OpenAI-compatible base URL: ${BASE_URL}/v1"
  echo "Served alias: ${ALIAS}"
  echo "Adapter GGUF: ${ADAPTER_GGUF}"
  exit 0
fi

mkdir -p "$(dirname "${PID_FILE}")" "$(dirname "${LOG_FILE}")"
stop_server

echo "Starting llama.cpp Qwen2.5 adapter runtime"
echo "Base URL: ${BASE_URL}/v1"
echo "Served alias: ${ALIAS}"
echo "Adapter: ${ADAPTER_GGUF}"
echo "Log: ${LOG_FILE}"

nohup "${SERVER_ARGS[@]}" >"${LOG_FILE}" 2>&1 </dev/null &
SERVER_PID="$!"
echo "${SERVER_PID}" >"${PID_FILE}"
disown "${SERVER_PID}" >/dev/null 2>&1 || true

for _ in $(seq 1 120); do
  if curl -fsS "${BASE_URL}/v1/models" >/dev/null 2>&1 || curl -fsS "${BASE_URL}/health" >/dev/null 2>&1; then
    echo "llama.cpp runtime ready at ${BASE_URL}/v1 with alias ${ALIAS}"
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
