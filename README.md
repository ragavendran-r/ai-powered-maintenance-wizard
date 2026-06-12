# AI-Powered Maintenance Wizard

Working prototype for an AI-powered maintenance decision-support system for steel manufacturing equipment.

The app helps maintenance engineers review plant health, diagnose equipment issues, inspect evidence, prioritize actions, ingest new maintenance context, export structured reports, and capture feedback that improves future recommendations.

## Current Capabilities

- FastAPI backend with health, dashboard, equipment health, alert, chat, diagnosis, prediction, work order, assistant, report, and feedback endpoints.
- React + TypeScript + Vite frontend for an operational dashboard, asset details, work-order queue/detail/execution/review screens, left-nav ingestion view, engineer chat, recommendation panel, report export, and detailed feedback controls.
- Sample steel-plant data for a hot strip mill drive, blast furnace blower, caster cooling pump, hot rolling hydraulic system, and melt shop overhead crane.
- SQLite-backed persistence seeded from five sample assets with equipment, alerts, sensor readings, spares, maintenance events, work orders, work logs, documents, document chunks, document intelligence, maintenance labels, and feedback.
- Local document chunk index with deterministic embeddings, hybrid retrieval scoring, optional LLM/SLM reranking, and relevance reasons for offline retrieval-augmented answers.
- Time-series sensor readings with rolling-baseline anomaly detection, risk impact, and optional LLM/SLM context classification with inspection steps.
- Provider-agnostic LLM/SLM adapters for OpenAI and Ollama with structured JSON validation and deterministic fallback reasoning.
- Markdown maintenance report export.
- API and frontend ingestion for text/Markdown/CSV/log/JSON and embedded-text PDF documents.
- Structured JSON record ingestion for equipment, alerts, spares, sensor readings, and maintenance history.
- Optional async IoT streaming ingestion via NATS JetStream for plant applications and edge gateways.
- Engineer feedback capture with equipment-linked root cause, action, outcome, and notes normalized into reusable maintenance labels for later recommendations and prediction drivers.
- Local login and role-based authorization for steel-plant users with admin, engineer, technician, supervisor, planner, operator, and API-only service roles.
- Role-specific technician and supervisor LLM assistant flows for live work-order directions, problem-code suggestions, completion summaries, follow-up review, and draft follow-up work.
- Backend and frontend tests for core prototype behavior.

## Decision-Support Features

- Reactive troubleshooting through natural-language chat and diagnosis requests across the five tracked steel-plant assets.
- Root-cause suggestions merged from deterministic rules, retrieved evidence, prior feedback, and optional LLM output.
- Degradation and remaining useful life estimates using explainable heuristic risk drivers, normalized maintenance labels, and grounded reasoning explanations.
- Proactive abnormality detection through rolling baseline, z-score, threshold breach, trend-delta analysis, and context classification.
- Prioritized maintenance actions based on risk level, active alerts, equipment criticality, spares availability, lead time, maintenance history, and feedback signals.
- Work-order lifecycle support with WAPPR, WMATL, APPR, INPRG, COMP, and CLOSE status tracking, assignment, priority, problem code, recommended action, follow-up flags, and work logs.
- Structured Markdown report export with diagnosis, risk, RUL, root causes, immediate actions, planned actions, spares strategy, learning notes, evidence, and summary.
- Continuous-improvement loop through equipment-linked engineer feedback reused in future recommendation ranking, LLM prompt context, normalized training labels, reports, and prediction drivers.

## Project Layout

```text
backend/              FastAPI application and tests
frontend/             React + Vite application
assets/sample_data/   Bundled steel-plant demo fixtures
backend/data/         Local SQLite database generated at runtime
docs/                 Architecture, planning, goal tracking, and progress docs
```

Important docs:

- `docs/architecture.md`: system architecture and data flow.
- `docs/auth-authorization-plan.md`: local login, roles, permissions, and test strategy.
- `docs/goal-tracker.md`: durable goal ledger from project start.
- `docs/progress.md`: session-level progress notes and verification history.
- `docs/demo_script.md`: suggested demo walkthrough.
- `docs/local-llm-lm-studio.md`: LM Studio setup for local OpenAI-compatible LLM inference.
- `docs/submission-guide.md`: hackathon packaging guide.
- `docs/production-hardening.md`: production-readiness gaps and next steps.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend URL: `http://localhost:8000`

Database utilities:

```bash
python -m app.manage db-status
python -m app.manage reset-db
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Useful API checks:

```bash
TOKEN=$(curl -s http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@plant.local","password":"DemoPass123!"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

curl http://localhost:8000/api/equipment/RM-DRIVE-01/anomalies \
  -H "Authorization: Bearer $TOKEN"
curl http://localhost:8000/api/equipment/RM-DRIVE-01/health \
  -H "Authorization: Bearer $TOKEN"
curl http://localhost:8000/api/streaming/status \
  -H "Authorization: Bearer $TOKEN"
curl http://localhost:8000/api/reports/RM-DRIVE-01/markdown \
  -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"equipment_id":"RM-DRIVE-01"}'
curl -X POST http://localhost:8000/api/equipment/RM-DRIVE-01/maintenance-labels \
  -H "Authorization: Bearer $TOKEN"
curl http://localhost:8000/api/equipment/RM-DRIVE-01/document-intelligence \
  -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/api/ingest/document-file \
  -H "Authorization: Bearer $TOKEN" \
  -F source_type=sop \
  -F equipment_id=RM-DRIVE-01 \
  -F title="Uploaded SOP" \
  -F file=@/path/to/manual-or-sop.pdf
```

Structured JSON ingestion examples:

```bash
curl -X POST http://localhost:8000/api/ingest/documents \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"documents":[{"id":"DOC-NEW","source_type":"sop","equipment_id":"RM-DRIVE-01","title":"Inspection SOP","content":"Inspect coupling alignment when vibration rises."}]}'

curl -X POST http://localhost:8000/api/ingest/records \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"alerts":[{"id":"ALT-NEW","equipment_id":"RM-DRIVE-01","timestamp":"2026-06-06T09:00:00+05:30","signal":"drive_end_vibration","value":8.3,"unit":"mm/s","threshold":7.1,"severity":"high","message":"Drive end vibration above advisory threshold"}]}'
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://localhost:5173`

## Local Full Stack

To run NATS JetStream, the streaming-enabled backend, and the frontend together:

```bash
scripts/run-local-stack.sh
```

Useful stack commands:

```bash
scripts/run-local-stack.sh status
scripts/run-local-stack.sh stop
```

The script requires Docker for the temporary `nats:2` container, an installed backend venv, and installed frontend `node_modules`. It writes backend and frontend logs under `.local-stack/`.

`scripts/run-local-stack.sh status` uses the seeded demo admin login to check protected streaming status when local auth is enabled.

`scripts/run-local-stack.sh stop` stops backend/frontend listeners on the configured ports and stops the named local-stack NATS container, even if `.local-stack` PID marker files are missing.

## Local Kubernetes Stack

To create a disposable local Kubernetes cluster and deploy NATS JetStream, the FastAPI backend, and the production-built frontend:

```bash
scripts/run-local-k8s.sh start
```

Useful Kubernetes stack commands:

```bash
scripts/run-local-k8s.sh status
scripts/run-local-k8s.sh stop
```

The script requires Docker, `kubectl`, `curl`, and `python3`. If `kind` is missing, the script installs it automatically with Homebrew when available, then falls back to `go install sigs.k8s.io/kind@latest` when Go is available. Set `KIND_AUTO_INSTALL=false` to fail fast instead. It creates a Kind cluster named `maintenance-wizard-local`, builds local backend/frontend images, loads those images plus `nats:2` into the cluster, applies Kubernetes deployments/services, and exposes:

- Frontend: `http://127.0.0.1:18081`
- Backend: `http://127.0.0.1:18080`
- NATS: `nats://127.0.0.1:14222`
- NATS monitor: `http://127.0.0.1:18222`

`scripts/run-local-k8s.sh stop` deletes the Kind cluster and generated `.local-k8s/` runtime files.

## Configuration

Copy `.env.example` to `.env` when configuring real providers.

```bash
cp .env.example .env
```

Supported LLM provider values:

- `mock`: deterministic local fallback for development.
- `openai`: OpenAI-compatible chat completions adapter using `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL`.
- `ollama`: Ollama chat adapter using `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

For local LM Studio inference, use the `openai` provider mode with `OPENAI_BASE_URL=http://localhost:1234/v1`. The recommended local model for this project is Qwen2.5 7B Instruct GGUF with a 4-bit quantization. Keep local response controls at `LLM_TIMEOUT_SECONDS=15`, `LLM_STRUCTURED_MAX_TOKENS=300`, and `LLM_TEXT_MAX_TOKENS=600`; Neo streams general dashboard answers as tokens arrive and prompts the model to complete answers within that budget. See `docs/local-llm-lm-studio.md` for install, model, `.env`, and smoke-test steps.

Provider responses must return the structured JSON contract requested by each feature. Recommendation generation expects `summary`, `probable_root_causes`, `immediate_actions`, `planned_actions`, and `confidence_adjustment`; document intelligence, maintenance labels, anomaly context, retrieval reranking, and reasoning explanations each use their own Pydantic-validated JSON schemas. Missing keys, malformed JSON, timeout, or network failure automatically fall back to deterministic local reasoning so the prototype remains runnable without secrets.

The backend creates and seeds `backend/data/maintenance_wizard.db` automatically on startup unless `DATABASE_PATH` is set to another SQLite file path. Documents are chunked into `document_chunks` with deterministic local embeddings for retrieval.

Document upload supports `.txt`, `.md`, `.markdown`, `.csv`, `.log`, `.json`, and `.pdf`. Parsed text is stored in SQLite, indexed into retrieval chunks, and processed into document intelligence with summary, assets, components, failure modes, symptoms, safety constraints, spares, and thresholds.

Structured record ingestion supports `equipment`, `alerts`, `spares`, `sensor_readings`, and `maintenance_events`. Maintenance events and engineer feedback are normalized into maintenance labels with failure mode, component, root cause, action class, outcome status, signal hints, and training usability. Engineer feedback is stored with `equipment_id`, `status`, `corrected_diagnosis`, `actual_root_cause`, `action_taken`, `outcome`, and `notes`.

NATS JetStream streaming ingestion is disabled by default. Set `STREAMING_ENABLED=true` and configure `NATS_URL` to consume IoT envelopes from `steelplant.iot.*` subjects into the same structured record tables used by JSON ingestion. The backend uses the `MW_IOT` stream, `maintenance-wizard-ingestor` durable consumer, explicit acknowledgments after persistence, and `steelplant.iot.dlq` for invalid messages.

The current SQLite schema version is `6`. Lightweight startup migrations add `feedback.equipment_id`, create `document_intelligence`, `maintenance_labels`, `streaming_messages`, local auth tables, work orders, and work-order logs for older local databases. Full migration tooling is still a production hardening item.

## Authentication And Authorization

The app uses local SQLite users, bcrypt password hashes, JWT bearer tokens, FastAPI role guards, and React role-aware navigation. `/api/health` and `/api/auth/login` are public. Maintenance data, ingestion, diagnosis, reports, feedback, streaming status, and user management require a bearer token and role permission.

Demo users are seeded when `AUTH_SEED_DEMO_USERS=true`; all use password `DemoPass123!`.

| User | Role |
| --- | --- |
| `admin@plant.local` | Full access and user management |
| `maintenance@plant.local` | Diagnosis, reports, predictions, feedback |
| `technician@plant.local` | Work-order execution and Smith technician AI assistant |
| `supervisor@plant.local` | Work-order review and Trinity supervisor AI assistant |
| `reliability@plant.local` | Diagnosis, reports, feedback, ingestion, streaming status |
| `planner@plant.local` | Dashboard, predictions, recommendations, reports |
| `operator@plant.local` | Read-only dashboard, alerts, health, anomalies |
| `iot-service@plant.local` | API-only ingestion identity |

Set `JWT_SECRET_KEY` to a strong secret outside local demos. External OIDC/SAML SSO remains a production hardening item.

## LLM And Learning Behavior

LLMs/SLMs are invoked only after deterministic ingestion and validation. They can enrich document ingestion with structured intelligence, normalize maintenance events and feedback into labels, rerank retrieved evidence, classify anomaly context, explain predictions/recommendations, guide technicians through work-order execution, and help supervisors review follow-ups. Smith, the technician assistant, is visible and callable only for `maintenance_technician`; Trinity, the supervisor assistant, is visible and callable only for `maintenance_supervisor`. Both use the same shared LLM provider, timeout, and token-limit configuration. They are not the source of truth for raw IoT ingestion, anomaly scores, risk scoring, RUL calculation, work-order persistence, or status changes.

LLMs are not involved in NATS IoT streaming ingestion. Streaming payloads are validated deterministically and persisted before later diagnosis, chat, report, and recommendation flows use the updated data.

When configured, recommendation prompts include equipment context, selected alert, symptoms/query, computed risk, failure probability, RUL, retrieved evidence, normalized maintenance labels, and recent engineer feedback notes. The backend validates structured JSON before merging LLM suggestions into deterministic recommendations.

Engineer feedback improves future behavior without retraining. Accepted or corrected feedback can promote known root causes and confirmed actions, appear as learning notes in reports, produce normalized labels, and add prediction drivers for the relevant equipment.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

```bash
cd frontend
npm run test
npm run build
```

## Demo Flow

1. Start the FastAPI backend.
2. Start the Vite frontend.
3. Sign in as `admin@plant.local` with `DemoPass123!`.
4. Open the dashboard and review high-risk assets.
5. Select the hot strip mill main drive.
6. Ask why the drive is vibrating or run diagnosis.
7. Review sensor anomalies, cited evidence, root causes, immediate and planned actions, spares strategy, feedback controls, and Markdown report export.
8. Open the Ingestion view from the left navigation and import an SOP/manual/log or paste JSON records/documents.
9. Open the Users view as admin to review role-based access.
10. Submit detailed feedback with actual root cause, action taken, and outcome; run diagnosis again to see learning notes included.

## Progress Tracking

Update `docs/progress.md` at the end of each implementation session with completed work, checks run, next steps, blockers, and decisions.

## Submission And Hardening

- Hackathon packaging guide: `docs/submission-guide.md`
- Production hardening notes: `docs/production-hardening.md`
- IoT streaming ingestion plan: `docs/iot-streaming-ingestion-plan.md`
- Authentication and authorization plan: `docs/auth-authorization-plan.md`
