#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.local-stack"
BACKEND_DIR="${ROOT_DIR}/backend"
FRONTEND_DIR="${ROOT_DIR}/frontend"

NATS_CONTAINER="${NATS_CONTAINER:-maintenance-wizard-nats}"
NATS_IMAGE="${NATS_IMAGE:-nats:2}"
NATS_HOST="${NATS_HOST:-127.0.0.1}"
NATS_PORT="${NATS_PORT:-4222}"
NATS_MONITOR_PORT="${NATS_MONITOR_PORT:-8222}"
NATS_URL="${NATS_URL:-nats://${NATS_HOST}:${NATS_PORT}}"
QDRANT_CONTAINER="${QDRANT_CONTAINER:-maintenance-wizard-qdrant}"
QDRANT_IMAGE="${QDRANT_IMAGE:-qdrant/qdrant:latest}"
QDRANT_HOST="${QDRANT_HOST:-127.0.0.1}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
QDRANT_URL="${QDRANT_URL:-http://${QDRANT_HOST}:${QDRANT_PORT}}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

BACKEND_LOG="${RUNTIME_DIR}/backend.log"
LEARNING_WORKER_LOG="${RUNTIME_DIR}/learning-worker.log"
FRONTEND_LOG="${RUNTIME_DIR}/frontend.log"
BACKEND_PID_FILE="${RUNTIME_DIR}/backend.pid"
LEARNING_WORKER_PID_FILE="${RUNTIME_DIR}/learning-worker.pid"
FRONTEND_PID_FILE="${RUNTIME_DIR}/frontend.pid"
NATS_STARTED_FILE="${RUNTIME_DIR}/nats.started"
QDRANT_STARTED_FILE="${RUNTIME_DIR}/qdrant.started"
STARTED_BACKEND=0
STARTED_LEARNING_WORKER=0
STARTED_FRONTEND=0

usage() {
  cat <<EOF
Usage: scripts/run-local-stack.sh [start|status|stop]

Commands:
  start   Start/reuse NATS JetStream, Qdrant, FastAPI backend, learning worker, and Vite frontend.
  status  Show health for NATS, Qdrant, backend, learning worker, streaming ingestion, learning, and frontend.
  stop    Stop backend/frontend/worker listeners and stop the named NATS/Qdrant containers.

Environment overrides:
  NATS_CONTAINER, NATS_IMAGE, NATS_HOST, NATS_PORT, NATS_MONITOR_PORT
  QDRANT_CONTAINER, QDRANT_IMAGE, QDRANT_HOST, QDRANT_PORT
  BACKEND_HOST, BACKEND_PORT, FRONTEND_HOST, FRONTEND_PORT

URLs:
  Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}
  Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}
  NATS:     ${NATS_URL}
  Qdrant:   ${QDRANT_URL}
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

url_ok() {
  curl -fsS "$1" >/dev/null 2>&1
}

demo_auth_token() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' < <(
    curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/api/auth/login" \
      -H "Content-Type: application/json" \
      -d '{"email":"admin@plant.local","password":"DemoPass123!"}'
  )
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts="${3:-40}"
  for _ in $(seq 1 "$attempts"); do
    if url_ok "$url"; then
      echo "${label} is ready: ${url}"
      return 0
    fi
    sleep 0.5
  done
  echo "${label} did not become ready: ${url}" >&2
  return 1
}

load_root_env() {
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${ROOT_DIR}/.env"
    set +a
  fi
}

pid_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

stop_process_tree() {
  local pid="$1"
  local label="$2"
  [[ -n "$pid" ]] || return 0
  kill -0 "$pid" >/dev/null 2>&1 || return 0

  local child
  for child in $(pgrep -P "$pid" 2>/dev/null || true); do
    stop_process_tree "$child" "$label"
  done

  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "Stopping ${label} process ${pid}"
    kill "$pid" >/dev/null 2>&1 || true
  fi
}

docker_container_exists() {
  docker ps -a --format '{{.Names}}' | grep -Fxq "$NATS_CONTAINER"
}

docker_container_running() {
  docker ps --format '{{.Names}}' | grep -Fxq "$NATS_CONTAINER"
}

qdrant_container_exists() {
  docker ps -a --format '{{.Names}}' | grep -Fxq "$QDRANT_CONTAINER"
}

qdrant_container_running() {
  docker ps --format '{{.Names}}' | grep -Fxq "$QDRANT_CONTAINER"
}

start_nats() {
  require_command docker
  if docker_container_running; then
    echo "NATS container already running: ${NATS_CONTAINER}"
    return 0
  fi
  if docker_container_exists; then
    echo "Starting existing NATS container: ${NATS_CONTAINER}"
    docker start "$NATS_CONTAINER" >/dev/null
  else
    echo "Starting NATS JetStream container: ${NATS_CONTAINER}"
    docker run -d --rm \
      --name "$NATS_CONTAINER" \
      -p "${NATS_PORT}:4222" \
      -p "${NATS_MONITOR_PORT}:8222" \
      "$NATS_IMAGE" -js -m 8222 >/dev/null
    touch "$NATS_STARTED_FILE"
  fi
  wait_for_url "http://${NATS_HOST}:${NATS_MONITOR_PORT}/healthz" "NATS"
}

start_qdrant() {
  require_command docker
  if qdrant_container_running; then
    echo "Qdrant container already running: ${QDRANT_CONTAINER}"
    return 0
  fi
  if qdrant_container_exists; then
    echo "Starting existing Qdrant container: ${QDRANT_CONTAINER}"
    docker start "$QDRANT_CONTAINER" >/dev/null
  else
    echo "Starting Qdrant vector database container: ${QDRANT_CONTAINER}"
    docker run -d --rm \
      --name "$QDRANT_CONTAINER" \
      -p "${QDRANT_PORT}:6333" \
      "$QDRANT_IMAGE" >/dev/null
    touch "$QDRANT_STARTED_FILE"
  fi
  wait_for_url "${QDRANT_URL}/readyz" "Qdrant"
}

start_backend() {
  if url_ok "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health"; then
    echo "Backend already responding: http://${BACKEND_HOST}:${BACKEND_PORT}"
    return 0
  fi
  if [[ ! -x "${BACKEND_DIR}/.venv/bin/uvicorn" ]]; then
    echo "Backend venv is missing. Run: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
    exit 1
  fi
  echo "Starting FastAPI backend with STREAMING_ENABLED=true and LEARNING_ASYNC_ENABLED=true"
  (
    cd "$BACKEND_DIR"
    load_root_env
    env STREAMING_ENABLED=true \
      LEARNING_ASYNC_ENABLED=true \
      NATS_URL="$NATS_URL" \
      RAG_VECTOR_STORE=qdrant \
      RAG_QDRANT_URL="$QDRANT_URL" \
      .venv/bin/uvicorn app.main:app --reload --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ) >"$BACKEND_LOG" 2>&1 &
  echo "$!" >"$BACKEND_PID_FILE"
  STARTED_BACKEND=1
  wait_for_url "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health" "Backend"
}

start_learning_worker() {
  if pid_running "$LEARNING_WORKER_PID_FILE"; then
    echo "Learning worker already running: $(cat "$LEARNING_WORKER_PID_FILE")"
    return 0
  fi
  if [[ ! -x "${BACKEND_DIR}/.venv/bin/python" ]]; then
    echo "Backend venv is missing. Run: cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt" >&2
    exit 1
  fi
  echo "Starting learning worker with LEARNING_ASYNC_ENABLED=true"
  (
    cd "$BACKEND_DIR"
    load_root_env
    env LEARNING_ASYNC_ENABLED=true \
      NATS_URL="$NATS_URL" \
      RAG_VECTOR_STORE=qdrant \
      RAG_QDRANT_URL="$QDRANT_URL" \
      .venv/bin/python -m app.learning_worker
  ) >"$LEARNING_WORKER_LOG" 2>&1 &
  echo "$!" >"$LEARNING_WORKER_PID_FILE"
  STARTED_LEARNING_WORKER=1
}

start_frontend() {
  if url_ok "http://${FRONTEND_HOST}:${FRONTEND_PORT}/"; then
    echo "Frontend already responding: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
    return 0
  fi
  if [[ ! -d "${FRONTEND_DIR}/node_modules" ]]; then
    echo "Frontend dependencies are missing. Run: cd frontend && npm install" >&2
    exit 1
  fi
  echo "Starting Vite frontend"
  (
    cd "$FRONTEND_DIR"
    npm run dev -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) >"$FRONTEND_LOG" 2>&1 &
  echo "$!" >"$FRONTEND_PID_FILE"
  STARTED_FRONTEND=1
  wait_for_url "http://${FRONTEND_HOST}:${FRONTEND_PORT}/" "Frontend"
}

start_stack() {
  require_command curl
  mkdir -p "$RUNTIME_DIR"
  rm -f "$NATS_STARTED_FILE" "$QDRANT_STARTED_FILE"
  start_nats
  start_qdrant
  start_backend
  start_learning_worker
  start_frontend
  echo
  echo "Local stack is running."
  echo "Frontend: http://${FRONTEND_HOST}:${FRONTEND_PORT}"
  echo "Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
  echo "NATS:     ${NATS_URL}"
  echo "Qdrant:   ${QDRANT_URL}"
  if [[ "$STARTED_BACKEND" -eq 1 || "$STARTED_LEARNING_WORKER" -eq 1 || "$STARTED_FRONTEND" -eq 1 ]]; then
    echo
    echo "Logs:"
    [[ "$STARTED_BACKEND" -eq 1 ]] && echo "  Backend:  ${BACKEND_LOG}"
    [[ "$STARTED_LEARNING_WORKER" -eq 1 ]] && echo "  Worker:   ${LEARNING_WORKER_LOG}"
    [[ "$STARTED_FRONTEND" -eq 1 ]] && echo "  Frontend: ${FRONTEND_LOG}"
    echo
    echo "Press Ctrl-C to stop processes started by this script."
    wait_for_children
  else
    echo
    echo "All services were already running; no new foreground process is being held."
  fi
}

wait_for_children() {
  trap stop_started EXIT INT TERM
  local backend_pid=""
  local learning_worker_pid=""
  local frontend_pid=""
  [[ -f "$BACKEND_PID_FILE" ]] && backend_pid="$(cat "$BACKEND_PID_FILE")"
  [[ -f "$LEARNING_WORKER_PID_FILE" ]] && learning_worker_pid="$(cat "$LEARNING_WORKER_PID_FILE")"
  [[ -f "$FRONTEND_PID_FILE" ]] && frontend_pid="$(cat "$FRONTEND_PID_FILE")"
  while true; do
    local any_running=0
    if [[ -n "$backend_pid" ]] && kill -0 "$backend_pid" >/dev/null 2>&1; then
      any_running=1
    fi
    if [[ -n "$learning_worker_pid" ]] && kill -0 "$learning_worker_pid" >/dev/null 2>&1; then
      any_running=1
    fi
    if [[ -n "$frontend_pid" ]] && kill -0 "$frontend_pid" >/dev/null 2>&1; then
      any_running=1
    fi
    [[ "$any_running" -eq 1 ]] || break
    sleep 1
  done
}

stop_pid_file() {
  local pid_file="$1"
  local label="$2"
  if pid_running "$pid_file"; then
    local pid
    pid="$(cat "$pid_file")"
    stop_process_tree "$pid" "$label"
  fi
  rm -f "$pid_file"
}

stop_port_listeners() {
  local port="$1"
  local label="$2"

  if ! command -v lsof >/dev/null 2>&1; then
    echo "Cannot inspect ${label} port ${port}; lsof is not installed" >&2
    return 0
  fi

  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return 0
  fi

  local pid
  for pid in $pids; do
    stop_process_tree "$pid" "$label"
  done
}

stop_started() {
  stop_pid_file "$BACKEND_PID_FILE" "backend"
  stop_pid_file "$LEARNING_WORKER_PID_FILE" "learning worker"
  stop_pid_file "$FRONTEND_PID_FILE" "frontend"
  stop_port_listeners "$BACKEND_PORT" "backend"
  stop_port_listeners "$FRONTEND_PORT" "frontend"
  if command -v docker >/dev/null 2>&1 && docker_container_running; then
    echo "Stopping NATS container ${NATS_CONTAINER}"
    docker stop "$NATS_CONTAINER" >/dev/null 2>&1 || true
  fi
  if command -v docker >/dev/null 2>&1 && qdrant_container_running; then
    echo "Stopping Qdrant container ${QDRANT_CONTAINER}"
    docker stop "$QDRANT_CONTAINER" >/dev/null 2>&1 || true
  fi
  rm -f "$NATS_STARTED_FILE" "$QDRANT_STARTED_FILE"
}

show_status() {
  require_command curl
  require_command python3
  echo "NATS monitor:"
  curl -fsS "http://${NATS_HOST}:${NATS_MONITOR_PORT}/healthz" || true
  echo
  echo "Qdrant:"
  curl -fsS "${QDRANT_URL}/readyz" || true
  echo
  echo "Backend health:"
  curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health" || true
  echo
  echo "Learning worker:"
  if pid_running "$LEARNING_WORKER_PID_FILE"; then
    echo "ok: pid $(cat "$LEARNING_WORKER_PID_FILE")"
  else
    echo "not running"
  fi
  echo
  echo "Streaming status:"
  local token=""
  if token="$(demo_auth_token 2>/dev/null)"; then
    curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/api/streaming/status" \
      -H "Authorization: Bearer ${token}" || true
    echo
    echo "Learning summary:"
    curl -fsS "http://${BACKEND_HOST}:${BACKEND_PORT}/api/learning/summary" \
      -H "Authorization: Bearer ${token}" || true
  else
    echo "could not obtain demo admin token"
  fi
  echo
  echo "Frontend:"
  if url_ok "http://${FRONTEND_HOST}:${FRONTEND_PORT}/"; then
    echo "ok: http://${FRONTEND_HOST}:${FRONTEND_PORT}/"
  else
    echo "not responding: http://${FRONTEND_HOST}:${FRONTEND_PORT}/"
  fi
}

COMMAND="${1:-start}"
case "$COMMAND" in
  start)
    start_stack
    ;;
  status)
    show_status
    ;;
  stop)
    stop_started
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
