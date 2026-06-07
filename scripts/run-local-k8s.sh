#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR="${ROOT_DIR}/.local-k8s"
CLUSTER_NAME="${K8S_CLUSTER_NAME:-maintenance-wizard-local}"
KUBE_CONTEXT="kind-${CLUSTER_NAME}"
NAMESPACE="${K8S_NAMESPACE:-maintenance-wizard}"

BACKEND_IMAGE="${BACKEND_IMAGE:-maintenance-wizard-backend:local-k8s}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-maintenance-wizard-frontend:local-k8s}"
NATS_IMAGE="${NATS_IMAGE:-nats:2}"
KIND_AUTO_INSTALL="${KIND_AUTO_INSTALL:-true}"

BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-18080}"
FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT:-18081}"
NATS_HOST_PORT="${NATS_HOST_PORT:-14222}"
NATS_MONITOR_HOST_PORT="${NATS_MONITOR_HOST_PORT:-18222}"

BACKEND_NODE_PORT="${BACKEND_NODE_PORT:-30080}"
FRONTEND_NODE_PORT="${FRONTEND_NODE_PORT:-30081}"
NATS_NODE_PORT="${NATS_NODE_PORT:-30422}"
NATS_MONITOR_NODE_PORT="${NATS_MONITOR_NODE_PORT:-30822}"

BACKEND_URL="http://127.0.0.1:${BACKEND_HOST_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_HOST_PORT}"
NATS_URL="nats://127.0.0.1:${NATS_HOST_PORT}"
NATS_MONITOR_URL="http://127.0.0.1:${NATS_MONITOR_HOST_PORT}"

usage() {
  cat <<EOF
Usage: scripts/run-local-k8s.sh [start|status|stop]

Commands:
  start   Create/reuse a local Kind cluster and deploy NATS, backend, and frontend.
  status  Show Kubernetes resources and live HTTP status checks.
  stop    Delete the local Kind cluster and temporary generated build files.

Environment overrides:
  K8S_CLUSTER_NAME, K8S_NAMESPACE
  BACKEND_HOST_PORT, FRONTEND_HOST_PORT, NATS_HOST_PORT, NATS_MONITOR_HOST_PORT
  BACKEND_NODE_PORT, FRONTEND_NODE_PORT, NATS_NODE_PORT, NATS_MONITOR_NODE_PORT
  BACKEND_IMAGE, FRONTEND_IMAGE, NATS_IMAGE
  KIND_AUTO_INSTALL=false to fail instead of installing Kind when missing

URLs after start:
  Frontend: ${FRONTEND_URL}
  Backend:  ${BACKEND_URL}
  NATS:     ${NATS_URL}
  NATS UI:  ${NATS_MONITOR_URL}
EOF
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

ensure_kind() {
  if command -v kind >/dev/null 2>&1; then
    return 0
  fi

  if [[ "$KIND_AUTO_INSTALL" != "true" ]]; then
    echo "Missing required command: kind" >&2
    echo "Install Kind manually or rerun with KIND_AUTO_INSTALL=true." >&2
    exit 1
  fi

  echo "Kind is not installed. Attempting to install Kind for the local Kubernetes stack."

  if command -v brew >/dev/null 2>&1; then
    echo "Installing Kind with Homebrew."
    if brew install kind; then
      if command -v kind >/dev/null 2>&1; then
        return 0
      fi
    else
      echo "Homebrew Kind installation failed; trying Go fallback if available."
    fi
  fi

  if command -v go >/dev/null 2>&1; then
    echo "Installing Kind with Go."
    if go install sigs.k8s.io/kind@latest; then
      local go_path=""
      go_path="$(go env GOPATH 2>/dev/null || true)"
      if [[ -n "$go_path" ]]; then
        export PATH="${go_path}/bin:${PATH}"
      fi
    else
      echo "Go Kind installation failed."
    fi
    if command -v kind >/dev/null 2>&1; then
      return 0
    fi
  fi

  echo "Could not install Kind automatically." >&2
  echo "Install Homebrew or Go, or install Kind manually and rerun this script." >&2
  exit 1
}

require_runtime() {
  require_command docker
  ensure_kind
  require_command kubectl
  require_command curl
  require_command python3
}

cluster_exists() {
  kind get clusters 2>/dev/null | grep -Fxq "$CLUSTER_NAME"
}

kubectl_cmd() {
  kubectl --context "$KUBE_CONTEXT" "$@"
}

write_kind_config() {
  mkdir -p "$RUNTIME_DIR"
  cat >"${RUNTIME_DIR}/kind-config.yaml" <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
    extraPortMappings:
      - containerPort: ${BACKEND_NODE_PORT}
        hostPort: ${BACKEND_HOST_PORT}
        listenAddress: "127.0.0.1"
        protocol: TCP
      - containerPort: ${FRONTEND_NODE_PORT}
        hostPort: ${FRONTEND_HOST_PORT}
        listenAddress: "127.0.0.1"
        protocol: TCP
      - containerPort: ${NATS_NODE_PORT}
        hostPort: ${NATS_HOST_PORT}
        listenAddress: "127.0.0.1"
        protocol: TCP
      - containerPort: ${NATS_MONITOR_NODE_PORT}
        hostPort: ${NATS_MONITOR_HOST_PORT}
        listenAddress: "127.0.0.1"
        protocol: TCP
EOF
}

create_cluster() {
  if cluster_exists; then
    echo "Kind cluster already exists: ${CLUSTER_NAME}"
    return 0
  fi
  write_kind_config
  echo "Creating Kind cluster: ${CLUSTER_NAME}"
  kind create cluster --name "$CLUSTER_NAME" --config "${RUNTIME_DIR}/kind-config.yaml"
}

write_dockerfiles() {
  mkdir -p "$RUNTIME_DIR"
  cat >"${RUNTIME_DIR}/backend.Dockerfile" <<'EOF'
FROM python:3.11-slim
WORKDIR /app/backend
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY assets /app/assets
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF

  cat >"${RUNTIME_DIR}/frontend.Dockerfile" <<'EOF'
FROM node:22-alpine AS build
WORKDIR /app
ARG VITE_API_BASE
ENV VITE_API_BASE=${VITE_API_BASE}
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
RUN printf '%s\n' \
  'server {' \
  '  listen 80;' \
  '  server_name _;' \
  '  root /usr/share/nginx/html;' \
  '  index index.html;' \
  '  location / { try_files $uri /index.html; }' \
  '}' > /etc/nginx/conf.d/default.conf
EXPOSE 80
EOF
}

build_images() {
  write_dockerfiles
  if ! docker image inspect "$NATS_IMAGE" >/dev/null 2>&1; then
    echo "Pulling NATS image: ${NATS_IMAGE}"
    docker pull "$NATS_IMAGE"
  fi
  echo "Building backend image: ${BACKEND_IMAGE}"
  docker build -f "${RUNTIME_DIR}/backend.Dockerfile" -t "$BACKEND_IMAGE" "$ROOT_DIR"
  echo "Building frontend image: ${FRONTEND_IMAGE}"
  docker build \
    -f "${RUNTIME_DIR}/frontend.Dockerfile" \
    --build-arg "VITE_API_BASE=${BACKEND_URL}" \
    -t "$FRONTEND_IMAGE" \
    "$ROOT_DIR"
}

load_images() {
  echo "Loading images into Kind cluster"
  load_image "$NATS_IMAGE"
  load_image "$BACKEND_IMAGE"
  load_image "$FRONTEND_IMAGE"
}

load_image() {
  local image="$1"
  if kind load docker-image "$image" --name "$CLUSTER_NAME"; then
    return 0
  fi

  echo "Kind image load failed for ${image}; retrying with direct containerd import."
  local node_container="${CLUSTER_NAME}-control-plane"
  local image_file=""
  image_file="$(printf '%s' "$image" | tr -c 'A-Za-z0-9_.-' '_')"
  local host_tar="${RUNTIME_DIR}/${image_file}.tar"
  local node_tar="/${image_file}.tar"

  docker save -o "$host_tar" "$image"
  docker cp "$host_tar" "${node_container}:${node_tar}"
  docker exec "$node_container" ctr --namespace=k8s.io images import --digests --snapshotter=overlayfs "$node_tar"
  docker exec "$node_container" rm -f "$node_tar"
  rm -f "$host_tar"
}

apply_manifests() {
  echo "Applying Kubernetes manifests in namespace: ${NAMESPACE}"
  kubectl_cmd apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: ${NAMESPACE}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nats
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: nats
  template:
    metadata:
      labels:
        app: nats
    spec:
      containers:
        - name: nats
          image: ${NATS_IMAGE}
          args: ["-js", "-m", "8222"]
          ports:
            - name: client
              containerPort: 4222
            - name: monitor
              containerPort: 8222
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8222
            initialDelaySeconds: 3
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: nats
  namespace: ${NAMESPACE}
spec:
  type: NodePort
  selector:
    app: nats
  ports:
    - name: client
      port: 4222
      targetPort: 4222
      nodePort: ${NATS_NODE_PORT}
    - name: monitor
      port: 8222
      targetPort: 8222
      nodePort: ${NATS_MONITOR_NODE_PORT}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: ${BACKEND_IMAGE}
          imagePullPolicy: Never
          ports:
            - containerPort: 8000
          env:
            - name: STREAMING_ENABLED
              value: "true"
            - name: NATS_URL
              value: "nats://nats.${NAMESPACE}.svc.cluster.local:4222"
            - name: AUTH_ENABLED
              value: "true"
            - name: AUTH_SEED_DEMO_USERS
              value: "true"
            - name: CORS_ALLOW_ORIGINS
              value: "http://localhost:${FRONTEND_HOST_PORT},http://127.0.0.1:${FRONTEND_HOST_PORT},http://localhost:5173,http://127.0.0.1:5173"
            - name: JWT_SECRET_KEY
              value: "maintenance-wizard-local-k8s-secret-change-me"
            - name: DATABASE_PATH
              value: "/data/maintenance_wizard.db"
          volumeMounts:
            - name: backend-data
              mountPath: /data
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          livenessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 20
            periodSeconds: 20
      volumes:
        - name: backend-data
          emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: ${NAMESPACE}
spec:
  type: NodePort
  selector:
    app: backend
  ports:
    - name: http
      port: 8000
      targetPort: 8000
      nodePort: ${BACKEND_NODE_PORT}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: frontend
  namespace: ${NAMESPACE}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: frontend
  template:
    metadata:
      labels:
        app: frontend
    spec:
      containers:
        - name: frontend
          image: ${FRONTEND_IMAGE}
          imagePullPolicy: Never
          ports:
            - containerPort: 80
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 3
            periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: frontend
  namespace: ${NAMESPACE}
spec:
  type: NodePort
  selector:
    app: frontend
  ports:
    - name: http
      port: 80
      targetPort: 80
      nodePort: ${FRONTEND_NODE_PORT}
EOF
  kubectl_cmd -n "$NAMESPACE" rollout restart deployment/backend deployment/frontend
}

wait_for_rollouts() {
  echo "Waiting for Kubernetes rollouts"
  kubectl_cmd -n "$NAMESPACE" rollout status deployment/nats --timeout=180s
  kubectl_cmd -n "$NAMESPACE" rollout status deployment/backend --timeout=240s
  kubectl_cmd -n "$NAMESPACE" rollout status deployment/frontend --timeout=180s
}

demo_auth_token() {
  python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])' < <(
    curl -fsS "${BACKEND_URL}/api/auth/login" \
      -H "Content-Type: application/json" \
      -d '{"email":"admin@plant.local","password":"DemoPass123!"}'
  )
}

show_urls() {
  echo
  echo "Local Kubernetes deployment is running."
  echo "Frontend: ${FRONTEND_URL}"
  echo "Backend:  ${BACKEND_URL}"
  echo "NATS:     ${NATS_URL}"
  echo "NATS UI:  ${NATS_MONITOR_URL}"
  echo
  echo "Demo login: admin@plant.local / DemoPass123!"
}

start_stack() {
  require_runtime
  create_cluster
  build_images
  load_images
  apply_manifests
  wait_for_rollouts
  show_urls
}

status_stack() {
  require_runtime
  if ! cluster_exists; then
    echo "Kind cluster is not running: ${CLUSTER_NAME}"
    exit 1
  fi
  kubectl_cmd -n "$NAMESPACE" get pods,svc
  echo
  echo "Backend health:"
  curl -fsS "${BACKEND_URL}/api/health" || true
  echo
  echo "Streaming status:"
  local token=""
  if token="$(demo_auth_token 2>/dev/null)"; then
    curl -fsS "${BACKEND_URL}/api/streaming/status" -H "Authorization: Bearer ${token}" || true
  else
    echo "could not obtain demo admin token"
  fi
  echo
  echo "Frontend:"
  if curl -fsS "${FRONTEND_URL}/" >/dev/null; then
    echo "ok: ${FRONTEND_URL}"
  else
    echo "not responding: ${FRONTEND_URL}"
  fi
  echo
  echo "NATS monitor:"
  curl -fsS "${NATS_MONITOR_URL}/healthz" || true
  echo
}

stop_stack() {
  ensure_kind
  if cluster_exists; then
    echo "Deleting Kind cluster: ${CLUSTER_NAME}"
    kind delete cluster --name "$CLUSTER_NAME"
  else
    echo "Kind cluster is not running: ${CLUSTER_NAME}"
  fi
  rm -rf "$RUNTIME_DIR"
  echo "Removed local Kubernetes runtime files: ${RUNTIME_DIR}"
}

COMMAND="${1:-start}"
case "$COMMAND" in
  start)
    start_stack
    ;;
  status)
    status_stack
    ;;
  stop)
    stop_stack
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage
    exit 1
    ;;
esac
