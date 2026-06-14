# AI-Powered Maintenance Wizard

Working prototype for an AI-powered maintenance decision-support system for steel manufacturing equipment.

The app helps maintenance engineers review plant health, diagnose equipment issues, inspect evidence, prioritize actions, ingest new maintenance context, export structured reports, and capture feedback that improves future recommendations.

## AI Capabilities

The AI layer is an audited maintenance copilot layered after deterministic backend controls. Raw IoT ingestion, anomaly scoring, risk calculation, role permissions, and persisted work-order updates stay in deterministic flows; AI explains, retrieves evidence, guides role-specific work, and helps turn reviewed outcomes into reusable learning material.

- Provider options: The backend selects the model runtime with `LLM_PROVIDER`. Use `mock` for deterministic offline development and tests, `openai` for OpenAI or any OpenAI-compatible endpoint such as LM Studio, vLLM, or a hosted gateway, and `ollama` for a local Ollama server. All live providers share the same structured-output validation, token limits, timeouts, streaming support, and deterministic fallback path. With `LLM_USE_ACTIVE_LEARNING_MODEL=true`, approved Learning Review promotions can change the served model id for `openai` or `ollama` calls without changing feature code; the `mock` provider intentionally ignores active-model resolution so regression tests stay stable.
- Role-aware assistants: Neo is the operational copilot for dashboard and work-order workflows. It gives role-specific welcomes, answers maintenance questions, renders asset/work-order/user tables, supports permission-checked commands such as asset summaries, work-order next steps, work-order creation/status actions, technician execution guidance, supervisor follow-up review, and admin user lookup/update flows. Morpheus is the diagnosis, RCA, and PM planning assistant: it combines asset health, alerts, work history, spares, retrieved evidence, feedback, risk, failure probability, and RUL context into probable root causes, immediate actions, planned actions, RCA/PM drafts, and confidence adjustments. Smith is the reliability, prediction, and execution-planning assistant: it explains degradation, risk, health score, remaining useful life, failure-probability drivers, cautions, recommended next steps, and technician-ready PM steps.
- Local LLM runtime: The recommended low-latency setup runs LM Studio on the same machine as the app with Qwen2.5 7B Instruct GGUF, preferably the balanced 4-bit `Q4_K_M` quantization. LM Studio exposes an OpenAI-compatible API at `http://localhost:1234/v1`, so the backend uses its normal `openai` adapter instead of a separate LM Studio-specific code path:

  ```env
  LLM_PROVIDER=openai
  OPENAI_API_KEY=lm-studio-local
  OPENAI_BASE_URL=http://localhost:1234/v1
  OPENAI_MODEL=qwen2.5-7b-instruct
  LLM_TIMEOUT_SECONDS=15
  LLM_STREAM_TIMEOUT_SECONDS=60
  LLM_STRUCTURED_MAX_TOKENS=300
  LLM_TEXT_MAX_TOKENS=600
  ```

  Load the model in LM Studio with a stable identifier such as `qwen2.5-7b-instruct`, high GPU offload such as `--gpu=max`, and a practical context length such as `4096`. The stable model id is important because it is the exact value the application sends as `OPENAI_MODEL`; if Learning Review later promotes an active model with `LLM_USE_ACTIVE_LEARNING_MODEL=true`, that promoted model id is sent to the same LM Studio OpenAI-compatible endpoint. Keeping the model local removes cloud round trips, while 4-bit quantization, GPU offload, short retrieved context, strict token caps, and streaming chat endpoints keep first-token and full-response latency low enough for the operational dashboard. Request/response JSON features use the shorter `LLM_TIMEOUT_SECONDS` because the backend must validate a complete structured object before merging it; Neo dashboard, technician, and supervisor chat use `LLM_STREAM_TIMEOUT_SECONDS` and stream tokens as they arrive so users see progress before the final app-owned structured event.
- LLM-enhanced workflows: The application uses LLM/SLM calls where they add judgment, explanation, or language understanding around deterministic plant data. They enrich document ingestion into structured maintenance intelligence, normalize feedback and work history into reusable labels, rerank retrieved RAG evidence, classify anomaly context, explain prediction drivers, generate recommendation text, guide technician execution, help supervisors review follow-ups, create report learning notes, and score candidate learning examples with an LLM-as-a-Judge rubric. The backend still validates JSON schemas and keeps persisted actions, role permissions, risk scoring, IoT ingestion, and database writes deterministic.
- Evidence-grounded RAG: Production retrieval uses Qdrant for document chunks and approved learning examples, with SQLite-local vector scoring only as a fallback. Prompts can include asset state, alerts, risk/RUL drivers, spares, work history, manuals, SOPs, logs, feedback, and approved assistant interactions.
- Learning gates: Learning Review combines human approval with an LLM-as-a-Judge rubric before feedback, labels, work-order outcomes, documents, or assistant interactions can be reused for RAG or tuning. Reviewer controls also cover embedding profiles, Qdrant reindexing, and migration checks.
- PEFT tuning path: Approved, judge-qualified examples can become JSONL snapshots for parameter-efficient fine-tuning. NATS-backed learning jobs write dataset and manifest artifacts with hashes, can invoke the optional bundled Qwen/SLM LoRA or QLoRA trainer template or another external trainer, and register adapter candidates only after training artifacts exist.
- Practical impact: RAG improves recommendations immediately by grounding answers in current plant evidence. PEFT can later specialize a smaller local model on steel-maintenance terminology, status transitions, failure modes, and approved action patterns, with evaluation, deployment verification, promotion, and rollback remaining reviewer-controlled.

## Current Capabilities

- FastAPI backend with health, dashboard, asset list/detail section loading, equipment health, alert, chat, diagnosis, prediction, work order, preventive-maintenance planning, planning/scheduling/dispatch, spare reservation/procurement, assistant, report, feedback, and learning-review endpoints.
- React + TypeScript + Vite frontend for an operational dashboard, a company Assets table, lazy-loaded data-backed asset details, work-order queue/detail/execution/review screens, left-nav ingestion view, engineer chat, recommendation panel, report export, and detailed feedback controls.
- Sample steel-plant data for a hot strip mill drive, blast furnace blower, caster cooling pump, hot rolling hydraulic system, and melt shop overhead crane.
- SQLite-backed persistence seeded from five sample assets with equipment, asset profiles, asset metrics, recommendations, subsystems, reliability metrics, alerts, sensor readings, spares, maintenance events, work orders, PM templates, PM plans, planner schedules, dispatch metadata, spare reservations, reorder/procurement blockers, work logs, SOP/manual/log/history evidence, document chunks, document intelligence, maintenance labels, and feedback.
- Local document chunk index with deterministic embeddings, hybrid retrieval scoring, optional LLM/SLM reranking, and relevance reasons for offline retrieval-augmented answers.
- Time-series sensor readings with rolling-baseline anomaly detection, risk impact, and optional LLM/SLM context classification with inspection steps.
- Provider-agnostic LLM/SLM adapters for OpenAI and Ollama with structured JSON validation and deterministic fallback reasoning.
- Markdown maintenance report export.
- API and frontend ingestion for text/Markdown/CSV/log/JSON and embedded-text PDF documents.
- Structured JSON record ingestion for equipment, alerts, spares, sensor readings, and maintenance history.
- Async IoT streaming ingestion via NATS JetStream for plant applications and edge gateways.
- Production RAG backed by Qdrant vector database, with local SQLite vector scoring only as a fallback.
- Engineer feedback capture with equipment-linked root cause, action, outcome, and notes normalized into reusable maintenance labels for later recommendations, prediction drivers, and LLM-as-a-Judge training-example review.
- Learning Review workflow for admin/engineer reviewers to score feedback, labels, completed work orders, approved assistant interactions, and ingested documents with an LLM-as-a-Judge rubric before approving them for RAG reuse or local PEFT tuning snapshots.
- Durable NATS learning worker for queued judge/dataset/evaluation/PEFT jobs, including local PEFT dataset and training-manifest artifacts with content hashes, optional external trainer handoff, and a bundled Qwen/SLM LoRA or QLoRA trainer template.
- Local login and role-based authorization for steel-plant users with admin, engineer, technician, supervisor, planner, operator, and API-only service roles.
- Role-specific technician and supervisor LLM assistant flows for live work-order directions, problem-code suggestions, completion summaries, follow-up review, and draft follow-up work.
- Backend and frontend tests for core prototype behavior.

## Decision-Support Features

- Reactive troubleshooting through natural-language chat and diagnosis requests across the five tracked steel-plant assets.
- Root-cause suggestions merged from deterministic rules, retrieved evidence, prior feedback, and optional LLM output.
- Degradation and remaining useful life estimates using explainable heuristic risk drivers, normalized maintenance labels, and grounded reasoning explanations.
- Proactive abnormality detection through rolling baseline, z-score, threshold breach, trend-delta analysis, and context classification.
- Prioritized maintenance actions based on risk level, active alerts, equipment criticality, spares availability, lead time, maintenance history, and feedback signals.
- Work-order lifecycle support with WAPPR, APPR, WMATL, INPRG, COMP, and CLOSE status tracking, assignment, priority, problem code, recommended action, follow-up flags, and work logs.
- Preventive maintenance planning with seeded PM templates, Morpheus-drafted recurring or condition-based plans, monitoring thresholds, generated task lists, Smith technician-ready steps, and conversion from risk prediction into planned PM work orders.
- Structured Markdown report export with diagnosis, risk, RUL, root causes, immediate actions, planned actions, spares strategy, learning notes, evidence, and summary.
- Continuous-improvement loop through equipment-linked engineer feedback, maintenance labels, work-order outcomes, approved assistant interactions, and LLM-as-a-Judge scores reused in future recommendation ranking, RAG prompt context, JSONL tuning snapshots, reports, and prediction drivers.

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
- `docs/peft-training.md`: optional Qwen/SLM LoRA or QLoRA trainer template setup and worker contract.
- `docs/rag-peft-nats-learning-architecture.md`: production design for RAG, PEFT adapter tuning, and NATS-backed async learning jobs.
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

To run NATS JetStream, Qdrant, the streaming-enabled backend, and the frontend together:

```bash
scripts/run-local-stack.sh
```

Useful stack commands:

```bash
scripts/run-local-stack.sh status
scripts/run-local-stack.sh stop
```

The script requires Docker for the temporary `nats:2` and `qdrant/qdrant` containers, an installed backend venv, and installed frontend `node_modules`. It writes backend and frontend logs under `.local-stack/`.

`scripts/run-local-stack.sh status` uses the seeded demo admin login to check protected streaming status when local auth is enabled.

`scripts/run-local-stack.sh stop` stops backend/frontend listeners on the configured ports and stops the named local-stack NATS and Qdrant containers, even if `.local-stack` PID marker files are missing.

## Local Kubernetes Stack

To create a disposable local Kubernetes cluster and deploy NATS JetStream, Qdrant, the FastAPI backend, and the production-built frontend:

```bash
scripts/run-local-k8s.sh start
```

Useful Kubernetes stack commands:

```bash
scripts/run-local-k8s.sh status
scripts/run-local-k8s.sh stop
```

The script requires Docker, `kubectl`, `curl`, and `python3`. If `kind` is missing, the script installs it automatically with Homebrew when available, then falls back to `go install sigs.k8s.io/kind@latest` when Go is available. Set `KIND_AUTO_INSTALL=false` to fail fast instead. It creates a Kind cluster named `maintenance-wizard-local`, builds local backend/frontend images, loads those images plus `nats:2` and `qdrant/qdrant` into the cluster, applies Kubernetes deployments/services, and exposes:

- Frontend: `http://127.0.0.1:18081`
- Backend: `http://127.0.0.1:18080`
- NATS: `nats://127.0.0.1:14222`
- NATS monitor: `http://127.0.0.1:18222`
- Qdrant: `http://127.0.0.1:16333`

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

For local LM Studio inference, use the `openai` provider mode with the low-latency Qwen2.5 7B Instruct settings summarized in `AI Capabilities`. See `docs/local-llm-lm-studio.md` for install, model loading, `.env`, and smoke-test steps.

When `LLM_USE_ACTIVE_LEARNING_MODEL=true`, real OpenAI-compatible or Ollama provider calls resolve the currently active `learning_model_versions` record before building the serving client. A promoted adapter candidate therefore changes the model id sent by Neo, Morpheus, Smith, recommendation, labeling, reranking, and document-intelligence calls without bypassing deterministic fallback or role checks. The `mock` provider intentionally ignores active model resolution so automated tests remain deterministic.

Provider responses must return the structured JSON contract requested by each feature. Recommendation generation expects `summary`, `probable_root_causes`, `immediate_actions`, `planned_actions`, and `confidence_adjustment`; document intelligence, maintenance labels, anomaly context, retrieval reranking, and reasoning explanations each use their own Pydantic-validated JSON schemas. Missing keys, malformed JSON, timeout, or network failure automatically fall back to deterministic local reasoning so the prototype remains runnable without secrets.

The backend creates and seeds `backend/data/maintenance_wizard.db` automatically on startup unless `DATABASE_PATH` is set to another SQLite file path. Asset-detail seed SQL loads normalized profile, metric, recommendation, subsystem, reliability, maintenance, work-order, and document evidence records for all five sample assets. Documents are chunked into `document_chunks` with deterministic local embeddings for retrieval.

Document upload supports `.txt`, `.md`, `.markdown`, `.csv`, `.log`, `.json`, and `.pdf`. Parsed text is stored in SQLite, indexed into retrieval chunks, and processed into document intelligence with summary, assets, components, failure modes, symptoms, safety constraints, spares, and thresholds.

Structured record ingestion supports `equipment`, `alerts`, `spares`, `work_order_spares`, `sensor_readings`, and `maintenance_events`. Maintenance events and engineer feedback are normalized into maintenance labels with failure mode, component, root cause, action class, outcome status, signal hints, and training usability. Engineer feedback is stored with `equipment_id`, `status`, `corrected_diagnosis`, `actual_root_cause`, `action_taken`, `outcome`, and `notes`.

NATS JetStream streaming ingestion is enabled in the local stack and should remain enabled for production. Set `STREAMING_ENABLED=true` and configure `NATS_URL` to consume IoT envelopes from `steelplant.iot.*` subjects into the same structured record tables used by JSON ingestion. The backend uses the `MW_IOT` stream, `maintenance-wizard-ingestor` durable consumer, explicit acknowledgments after persistence, and `steelplant.iot.dlq` for invalid messages.

The same NATS server also carries production learning jobs without mixing them with plant IoT payloads. Keep `LEARNING_ASYNC_ENABLED=true` to publish queued tuning jobs to `LEARNING_NATS_STREAM=MW_LEARNING` on `maintenance.learning.*` subjects. Run the worker with `python -m app.learning_worker`, or use the local stack scripts, to consume jobs with `LEARNING_NATS_CONSUMER=maintenance-wizard-learning-worker`. PEFT requests prepare a JSONL dataset and training manifest under `LEARNING_ARTIFACT_DIR`, then record artifact hashes for audit. When `LEARNING_PEFT_TRAINER_COMMAND` is configured, the worker invokes that external trainer with bounded timeout and registers the resulting adapter as a `candidate` model version only.

Learning artifacts default to local filesystem storage with `LEARNING_ARTIFACT_STORE=filesystem`. For production-like object storage, set `LEARNING_ARTIFACT_STORE=s3`, `LEARNING_ARTIFACT_S3_BUCKET`, and optionally `LEARNING_ARTIFACT_S3_ENDPOINT_URL` for MinIO or another S3-compatible store. The worker keeps local files for offline handoff, uploads each artifact through the S3-compatible client, and records `s3://` object URIs, object keys, storage backend, SHA-256 hashes, and local retained paths in `learning_artifacts`. External trainer output can be directed with `LEARNING_PEFT_OUTPUT_DIR`, and `LEARNING_PEFT_TRAINER_TIMEOUT_SECONDS` bounds the run.

Set `LEARNING_ARTIFACT_RETENTION_DAYS` above `0` to report expired local learning-artifact files in artifact-store lifecycle helpers and Learning Summary policy status. Cleanup is DB-backed and only considers registered `learning_artifacts`; it protects active, candidate, promoted, or verified-deployment adapter references. Learning Review exposes a dry-run cleanup preview for reviewers. File deletion requires an explicit non-dry-run caller with admin or reliability-engineer role and `LEARNING_ARTIFACT_CLEANUP_ENABLED=true`; non-filesystem stores remain read-only in the app.

Production RAG uses Qdrant as the vector database. Set `RAG_VECTOR_STORE=qdrant`, `RAG_QDRANT_URL=http://localhost:6333`, and `RAG_QDRANT_COLLECTION=maintenance_wizard_documents`. `RAG_EMBEDDING_PROVIDER`, `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_VERSION`, `RAG_EMBEDDING_DIMENSIONS`, and `RAG_EMBEDDING_DISTANCE` describe the embedding profile attached to indexed chunks and surfaced in Learning Review. Uploaded and seeded document chunks are indexed into Qdrant when it is available. Approved, judge-qualified learning examples are also synchronized into Qdrant as separate RAG entries during learning refresh, approval changes, rejudge, and reviewer reindex flows. Retrieval queries Qdrant for both plant documents and approved learning examples, then falls back to SQLite-local vectors only when the vector DB is unavailable or explicitly disabled for tests. Learning Review includes a reviewer-only RAG reindex action for rebuilding chunks and repopulating the configured collection after an embedding profile or collection migration.

The current SQLite schema version is `19`. Lightweight startup migrations add `feedback.equipment_id`, create asset detail tables, `document_intelligence`, `maintenance_labels`, `streaming_messages`, local auth tables, work orders, work-order planning/dispatch metadata, work-order spare reservations with reorder/procurement/substitute/blocker fields, work-order logs, RCA cases, PM templates and PM plans, learning interactions, judged examples, dataset snapshots, model versions, prompt versions, evaluation runs, learning jobs, learning artifacts, model promotion audit records, adapter runtime deployment records, and RAG embedding profile metadata for older local databases.

The current production-aligned learning scope is intentionally constrained to what can run on the local Mac stack: SQLite, Qdrant, NATS, filesystem/S3-compatible artifact registration, local PEFT trainer hooks, and OpenAI-compatible or Ollama-style LLM serving. Future production phases track Postgres migration, bucket-native object-store lifecycle/access hardening, and environment-specific adapter-loader automation for LM Studio/Ollama or another serving runtime.

## Authentication And Authorization

The app uses local SQLite users, bcrypt password hashes, JWT bearer tokens, FastAPI role guards, and React role-aware navigation. `/api/health` and `/api/auth/login` are public. Maintenance data, ingestion, diagnosis, reports, feedback, streaming status, and user management require a bearer token and role permission.

Demo users are loaded from `assets/sample_data/users_seed.sql` when `AUTH_SEED_DEMO_USERS=true`; all use password `DemoPass123!`.

| User | Role |
| --- | --- |
| `admin@plant.local` | Full access and user management |
| `maintenance@plant.local` | Diagnosis, reports, predictions, feedback |
| `technician@plant.local` | Work-order execution and Neo technician AI assistant |
| `supervisor@plant.local` | Work-order review and Neo supervisor AI assistant |
| `reliability@plant.local` | Diagnosis, reports, feedback, ingestion, streaming status |
| `planner@plant.local` | Dashboard, predictions, recommendations, reports, maintenance scheduling and dispatch |
| `operator@plant.local` | Read-only dashboard, alerts, health, anomalies |
| `iot-service@plant.local` | API-only ingestion identity |

Set `JWT_SECRET_KEY` to a strong secret outside local demos. External OIDC/SAML SSO remains a production hardening item.

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
