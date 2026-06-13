# AI-Powered Maintenance Wizard

Working prototype for an AI-powered maintenance decision-support system for steel manufacturing equipment.

The app helps maintenance engineers review plant health, diagnose equipment issues, inspect evidence, prioritize actions, ingest new maintenance context, export structured reports, and capture feedback that improves future recommendations.

## Current Capabilities

- FastAPI backend with health, dashboard, asset list/detail section loading, equipment health, alert, chat, diagnosis, prediction, work order, assistant, report, feedback, and learning-review endpoints.
- React + TypeScript + Vite frontend for an operational dashboard, a company Assets table, lazy-loaded data-backed asset details, work-order queue/detail/execution/review screens, left-nav ingestion view, engineer chat, recommendation panel, report export, and detailed feedback controls.
- Sample steel-plant data for a hot strip mill drive, blast furnace blower, caster cooling pump, hot rolling hydraulic system, and melt shop overhead crane.
- SQLite-backed persistence seeded from five sample assets with equipment, asset profiles, asset metrics, recommendations, subsystems, reliability metrics, alerts, sensor readings, spares, maintenance events, work orders, work logs, SOP/manual/log/history evidence, document chunks, document intelligence, maintenance labels, and feedback.
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
- Durable NATS learning worker for queued judge/dataset/evaluation/PEFT jobs, including local PEFT dataset and training-manifest artifacts with content hashes.
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

For local LM Studio inference, use the `openai` provider mode with `OPENAI_BASE_URL=http://localhost:1234/v1`. The recommended local model for this project is Qwen2.5 7B Instruct GGUF with a 4-bit quantization. Keep local response controls at `LLM_TIMEOUT_SECONDS=15`, `LLM_STREAM_TIMEOUT_SECONDS=60`, `LLM_STRUCTURED_MAX_TOKENS=300`, and `LLM_TEXT_MAX_TOKENS=600`; Neo streams dashboard, technician, and supervisor chat answers as tokens arrive and prompts the model to complete answers within that budget. See `docs/local-llm-lm-studio.md` for install, model, `.env`, and smoke-test steps.

When `LLM_USE_ACTIVE_LEARNING_MODEL=true`, real OpenAI-compatible or Ollama provider calls resolve the currently active `learning_model_versions` record before building the serving client. A promoted adapter candidate therefore changes the model id sent by Neo, Morpheus, Smith, recommendation, labeling, reranking, and document-intelligence calls without bypassing deterministic fallback or role checks. The `mock` provider intentionally ignores active model resolution so automated tests remain deterministic.

Provider responses must return the structured JSON contract requested by each feature. Recommendation generation expects `summary`, `probable_root_causes`, `immediate_actions`, `planned_actions`, and `confidence_adjustment`; document intelligence, maintenance labels, anomaly context, retrieval reranking, and reasoning explanations each use their own Pydantic-validated JSON schemas. Missing keys, malformed JSON, timeout, or network failure automatically fall back to deterministic local reasoning so the prototype remains runnable without secrets.

The backend creates and seeds `backend/data/maintenance_wizard.db` automatically on startup unless `DATABASE_PATH` is set to another SQLite file path. Asset-detail seed SQL loads normalized profile, metric, recommendation, subsystem, reliability, maintenance, work-order, and document evidence records for all five sample assets. Documents are chunked into `document_chunks` with deterministic local embeddings for retrieval.

Document upload supports `.txt`, `.md`, `.markdown`, `.csv`, `.log`, `.json`, and `.pdf`. Parsed text is stored in SQLite, indexed into retrieval chunks, and processed into document intelligence with summary, assets, components, failure modes, symptoms, safety constraints, spares, and thresholds.

Structured record ingestion supports `equipment`, `alerts`, `spares`, `sensor_readings`, and `maintenance_events`. Maintenance events and engineer feedback are normalized into maintenance labels with failure mode, component, root cause, action class, outcome status, signal hints, and training usability. Engineer feedback is stored with `equipment_id`, `status`, `corrected_diagnosis`, `actual_root_cause`, `action_taken`, `outcome`, and `notes`.

NATS JetStream streaming ingestion is enabled in the local stack and should remain enabled for production. Set `STREAMING_ENABLED=true` and configure `NATS_URL` to consume IoT envelopes from `steelplant.iot.*` subjects into the same structured record tables used by JSON ingestion. The backend uses the `MW_IOT` stream, `maintenance-wizard-ingestor` durable consumer, explicit acknowledgments after persistence, and `steelplant.iot.dlq` for invalid messages.

The same NATS server also carries production learning jobs without mixing them with plant IoT payloads. Keep `LEARNING_ASYNC_ENABLED=true` to publish queued tuning jobs to `LEARNING_NATS_STREAM=MW_LEARNING` on `maintenance.learning.*` subjects. Run the worker with `python -m app.learning_worker`, or use the local stack scripts, to consume jobs with `LEARNING_NATS_CONSUMER=maintenance-wizard-learning-worker`. PEFT requests prepare a JSONL dataset and training manifest under `LEARNING_ARTIFACT_DIR`, then record artifact hashes for audit. When `LEARNING_PEFT_TRAINER_COMMAND` is configured, the worker invokes that external trainer with bounded timeout and registers the resulting adapter as a `candidate` model version only.

Learning artifacts default to local filesystem storage with `LEARNING_ARTIFACT_STORE=filesystem`. For production-like object storage, set `LEARNING_ARTIFACT_STORE=s3`, `LEARNING_ARTIFACT_S3_BUCKET`, and optionally `LEARNING_ARTIFACT_S3_ENDPOINT_URL` for MinIO or another S3-compatible store. The worker keeps local files for offline handoff, uploads each artifact through the S3-compatible client, and records `s3://` object URIs, object keys, storage backend, SHA-256 hashes, and local retained paths in `learning_artifacts`. External trainer output can be directed with `LEARNING_PEFT_OUTPUT_DIR`, and `LEARNING_PEFT_TRAINER_TIMEOUT_SECONDS` bounds the run.

Set `LEARNING_ARTIFACT_RETENTION_DAYS` above `0` to report expired local learning-artifact files in artifact-store lifecycle helpers and Learning Summary policy status. Cleanup is DB-backed and only considers registered `learning_artifacts`; it protects active, candidate, promoted, or verified-deployment adapter references. Learning Review exposes a dry-run cleanup preview for reviewers. File deletion requires an explicit non-dry-run caller with admin or reliability-engineer role and `LEARNING_ARTIFACT_CLEANUP_ENABLED=true`; non-filesystem stores remain read-only until production bucket lifecycle policies are configured.

Production RAG uses Qdrant as the vector database. Set `RAG_VECTOR_STORE=qdrant`, `RAG_QDRANT_URL=http://localhost:6333`, and `RAG_QDRANT_COLLECTION=maintenance_wizard_documents`. `RAG_EMBEDDING_PROVIDER`, `RAG_EMBEDDING_MODEL`, `RAG_EMBEDDING_VERSION`, `RAG_EMBEDDING_DIMENSIONS`, and `RAG_EMBEDDING_DISTANCE` describe the embedding profile attached to indexed chunks and surfaced in Learning Review. Uploaded and seeded document chunks are indexed into Qdrant when it is available; retrieval falls back to SQLite-local vectors only when the vector DB is unavailable or explicitly disabled for tests. Learning Review includes a reviewer-only RAG reindex action for rebuilding chunks and repopulating the configured collection after an embedding profile or collection migration.

The current SQLite schema version is `13`. Lightweight startup migrations add `feedback.equipment_id`, create asset detail tables, `document_intelligence`, `maintenance_labels`, `streaming_messages`, local auth tables, work orders, work-order logs, learning interactions, judged examples, dataset snapshots, model versions, prompt versions, evaluation runs, learning jobs, learning artifacts, model promotion audit records, and adapter runtime deployment records for older local databases. Full migration tooling is still a production hardening item.

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
| `planner@plant.local` | Dashboard, predictions, recommendations, reports |
| `operator@plant.local` | Read-only dashboard, alerts, health, anomalies |
| `iot-service@plant.local` | API-only ingestion identity |

Set `JWT_SECRET_KEY` to a strong secret outside local demos. External OIDC/SAML SSO remains a production hardening item.

## LLM And Learning Behavior

LLMs/SLMs are invoked only after deterministic ingestion and validation. They can enrich document ingestion with structured intelligence, normalize maintenance events and feedback into labels, rerank retrieved evidence, classify anomaly context, explain predictions/recommendations, guide technicians through work-order execution, and help supervisors review follow-ups. Neo presents role-aware modes: the technician mode is visible and callable only for `maintenance_technician`, and the supervisor mode is visible and callable only for `maintenance_supervisor`. Both modes share the same LLM provider, model, token-limit, and streaming configuration as dashboard Neo, and stream visible chat responses before sending final structured app updates. Dashboard Neo starts with a deterministic role-aware welcome that highlights immediate attention items such as assigned technician work, supervisor approvals/follow-ups, engineering asset reviews, or read-only operator watch items. It also has deterministic, role-aware commands for backend asset summaries, work-order next steps, work-order creation/status actions, and admin user retrieval/updates. Neo is not the source of truth for raw IoT ingestion, anomaly scores, risk scoring, or RUL calculation; persisted actions still go through the backend repository and role checks.

LLMs are not involved in NATS IoT streaming ingestion. Streaming payloads are validated deterministically and persisted before later diagnosis, chat, report, and recommendation flows use the updated data.

When configured, recommendation prompts include equipment context, selected alert, symptoms/query, computed risk, failure probability, RUL, retrieved evidence, normalized maintenance labels, and recent engineer feedback notes. The backend validates structured JSON before merging LLM suggestions into deterministic recommendations.

Engineer feedback improves future behavior before retraining through RAG and ranking. Accepted or corrected feedback can promote known root causes and confirmed actions, appear as learning notes in reports, produce normalized labels, and add prediction drivers for the relevant equipment.

The learning pipeline uses an LLM-as-a-Judge quality gate before data can be reused for training or tuning. Candidate examples are generated from accepted/corrected feedback, usable maintenance labels, completed work orders, approved assistant interactions, and ingested documents. The judge scores each example from 0.0 to 1.0, labels it as `training_worthy`, `review`, or `reject`, records a rationale/provider, and falls back to a deterministic rubric if the local LLM is unavailable. Dataset snapshots include only examples that are both human-approved and above the configured judge threshold, defaulting to `0.65`.

The architecture is RAG + PEFT-ready rather than one or the other. Judge-qualified, approved examples are immediately available to retrieval and recommendation prompts, while the same examples can be exported as JSONL snapshots for offline/local adapter tuning. This keeps live recommendations auditable and reversible while allowing later Qwen/SLM LoRA or other PEFT jobs to use only curated maintenance content.

For production, the learning/tuning path uses a persisted learning-job model and NATS JetStream as the async job backbone rather than running large judging, dataset, evaluation, or PEFT jobs in the web request path. The current app records reviewer learning actions in `learning_jobs`, exposes recent job status in Learning Review, can queue PEFT tuning jobs against approved dataset/model/prompt versions, provides evaluation-gated adapter promotion and rollback controls with audit records, tracks adapter runtime deployments separately from promotion state, shows the active serving LLM configuration selected from approved model versions and verified deployments, and reports artifact-store and PEFT trainer status. Set `LEARNING_ASYNC_ENABLED=true` to publish queued jobs to the separate `maintenance.learning.*` NATS subjects. The worker consumes those jobs, updates job status, writes PEFT dataset/manifest artifacts, uploads them to filesystem or S3-compatible storage, optionally runs a configured external trainer, records trainer logs and adapter manifests, registers trained outputs as candidate model versions, and can verify manually recorded or OpenAI/Ollama-compatible adapter runtime deployments before promotion. Bundled trainer templates and adapter runtime deployment tracking/gating are represented in the app; the remaining production integration is the environment-specific loader that makes approved adapter artifacts available to LM Studio, Ollama, or another serving runtime. See `docs/rag-peft-nats-learning-architecture.md`.

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
