# Maintenance Wizard Progress

## Goal

Implement a working AI-powered Maintenance Wizard prototype in `/Users/ragaven/work/ai-powered-maintenance-wizard` using FastAPI, React, SQLite, local retrieval, provider-agnostic LLM adapters, sample steel-plant maintenance data, dashboard, chat, diagnosis, risk scoring, recommendations, feedback, tests, and documentation.

## Milestones

- [x] Project scaffold
- [x] Backend FastAPI foundation
- [x] SQLite database models and persistence
- [x] Sample steel-plant maintenance data
- [x] Document ingestion and local vector retrieval
- [x] Initial keyword retrieval scaffold
- [x] LLM provider adapter scaffold
- [x] Live OpenAI/Ollama structured adapter support
- [x] Initial diagnosis and recommendation pipeline
- [x] Initial anomaly and risk scoring
- [x] Initial feedback loop
- [x] React dashboard
- [x] Chat and report UI
- [x] Initial tests
- [x] Documentation and demo script

## Latest Session Update

- Expanded the README `AI Capabilities` section with supported `mock`, `openai`, and `ollama` LLM provider modes; specific Neo, Morpheus, and Smith responsibilities; the local LM Studio + Qwen2.5 7B Instruct runtime path; the exact OpenAI-compatible application configuration; active learning model handoff; and the low-latency settings that matter for local operation. Shortened the later configuration note to avoid duplicating the same content.
- Merged PR #54 (`codex/role-responsive-playwright`) into `main`, fetched the merged `origin/main`, and created `codex/readme-ai-capabilities-merged-main` from that updated base before starting the README work.
- Added and refined a top-level README `AI Capabilities` section above `Current Capabilities`, covering role-aware assistants, evidence-grounded Qdrant RAG, Learning Review gates, PEFT tuning handoff, and how RAG plus PEFT improve short-term and long-term maintenance AI behavior.
- Removed the redundant README `LLM And Learning Behavior` section after reviewing the AI content again, leaving the top-level `AI Capabilities` section as the single README summary for role-aware assistants, RAG, Learning Review gates, and PEFT tuning. The detailed implementation notes remain in linked architecture/training docs instead of a second README AI section.

- Added Playwright role coverage for operator, maintenance technician, maintenance supervisor, maintenance engineer, reliability engineer, and admin using a shared mocked maintenance API fixture. Added responsive Playwright checks for dashboard, asset detail, work orders, ingestion, and learning review across desktop, tablet, and mobile viewports.
- Made the existing assistant stream E2E independent of a live backend by reusing the mocked auth/bootstrap fixture. Fixed responsive CSS regressions exposed by the new coverage: non-dashboard routes now collapse `.workArea.ingestionMode` at the tablet/mobile breakpoint, asset-detail summary panels reset grid placement, learning RAG controls collapse cleanly, file inputs clip safely, and mobile asset tabs/title wrap instead of causing document overflow.
- Verification passed for this slice with frontend unit tests, frontend build, full Playwright E2E coverage with 24 passing tests, and `git diff --check`.

- Continued G-016 on `codex/qdrant-learning-examples-isolated`: approved, judge-qualified learning examples are now synchronized into Qdrant as first-class RAG entries during learning refresh, reviewer approval changes, rejudge, and full RAG reindex flows. Retrieval now queries Qdrant for both document chunks and approved learning examples, keeps them separated by RAG kind, deduplicates sources, and retains SQLite/local-vector fallback for disconnected or test use.
- Added regression coverage for Qdrant learning-example retrieval hits and reviewer reindex syncing of approved learning examples. Updated README, RAG+PEFT+NATS design notes, goal tracker, rules, hooks, and `AGENTS.md` to reflect Qdrant-backed learning-example reuse, completion ETA updates, and close-after-use subagent handling.
- Verification passed for the Qdrant learning-example slice with backend compile, focused backend tests covering Qdrant learning-example retrieval/reindex sync, full backend API tests with 93 passing tests, and `git diff --check`.
- Continued G-016 on `codex/rag-migration-controls`: added schema version 14 RAG embedding profiles, embedding metadata on document chunks, active-profile filtering for retrieval fallback, OpenAI-compatible embedding profile configuration hooks, Qdrant collection shape/status checks, migration preview/run APIs, reviewer-audited profile activation/reindex/migration jobs, and Learning Review controls for selecting profiles, previewing migrations, running Qdrant migrations, and reindexing the current profile.
- Fixed a local Mac runtime migration issue where SQLite could not add `document_chunks.embedded_at` with `DEFAULT CURRENT_TIMESTAMP` on existing databases; the migration now adds a nullable column and backfills it. Cleared stale local pytest/uvicorn processes that were holding the current SQLite database and port 8000, then restarted the existing local stack on its original ports.
- Moved Postgres migration, object-store lifecycle/access-policy hardening, and environment-specific LM Studio/Ollama adapter-loader automation out of active G-016 completion scope and into future production phases so the current goal remains production-aligned but implementable on the local Mac stack.
- Verification passed for this slice with backend compile, backend API tests on an isolated SQLite database (`91 passed`), frontend unit tests (`17 passed`), frontend build, and Playwright E2E outside the sandbox against the current local app (`1 passed`).

- Continued G-016 with learning artifact lifecycle hardening. Added DB-backed cleanup preview/apply support for registered `learning_artifacts`, protected active/candidate/promoted model and verified deployment artifact references, kept non-filesystem stores read-only, role-gated destructive cleanup to admin/reliability-engineer with `LEARNING_ARTIFACT_CLEANUP_ENABLED=true`, and audited cleanup attempts as learning jobs.
- Added Learning Review artifact-store retention visibility and a dry-run cleanup preview showing eligible, protected, deleted, and warning states without exposing browser-side deletion controls.
- Tightened durable collaboration rules so split-safe work uses parallel agents whenever the tool is available, not only for large tasks.
- Updated README, RAG+PEFT+NATS design notes, and the goal tracker to reflect registry-first artifact cleanup.
- Verification passed for the artifact lifecycle slice: `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`, `backend/.venv/bin/pytest backend/tests/test_api.py -q` with 88 tests, `npm --prefix frontend run test` with 17 tests, `npm --prefix frontend run build`, `git diff --check`, and `npm --prefix frontend run test:e2e` after browser-launch escalation. The local stack health check passed with backend, frontend, NATS, Qdrant, and the learning worker running.

- Continued G-016 with adapter runtime deployment tracking and promotion gating. Schema version 13 adds `learning_model_deployments`; Learning Review can queue adapter deployment jobs; the learning worker verifies manual/OpenAI-compatible/Ollama runtime deployments; adapter promotion now requires a verified runtime deployment when the model has an adapter artifact; and active real LLM serving resolution prefers verified deployment metadata such as served model, runtime provider, health status, and base URL.
- Updated Learning Review UI/API types to display runtime deployments, deploy candidates, and show verified deployment details in the serving-model status panel.
- Updated README, architecture, RAG+PEFT+NATS design, and goal tracker to reflect in-app runtime deployment tracking/gating.
- Added a durable NATS learning worker for G-016. The worker processes persisted learning job messages for refresh, judge, dataset, evaluation, and PEFT preparation paths; moves jobs through running/completed/failed states; publishes malformed jobs to DLQ; and can run as `python -m app.learning_worker`.
- Added schema version 11 with `learning_artifacts`, repository helpers, artifact counts, and Learning Review API/UI visibility for recent worker artifacts.
- Added local PEFT artifact preparation: queued PEFT jobs now produce a JSONL dataset artifact and training manifest with SHA-256 hashes and `training_status=awaiting_external_peft_trainer` when no trainer is configured, giving external LoRA/QLoRA trainers an auditable handoff without claiming model training happened inside the web app.
- Updated local stack to start the learning worker with NATS/Qdrant/backend/frontend, and updated local Kubernetes to run the worker as a backend sidecar sharing local SQLite state.
- Updated README, architecture, RAG+PEFT+NATS design, and goal tracker to reflect the worker and artifact registry. Remaining G-016 work is bundled trainer templates and production embeddings/Qdrant migration controls.
- Verification passed for the adapter runtime deployment slice: `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`, `backend/.venv/bin/pytest backend/tests/test_api.py` with 85 tests, `npm --prefix frontend run test` with 17 tests, `npm --prefix frontend run build`, `npm --prefix frontend run test:e2e` after browser-launch escalation, and `git diff --check`.

- Treated the app as production-targeted by default and persisted that rule in `docs/rules.md`.
- Made async learning enabled by default in backend configuration and local stack scripts.
- Added Qdrant as the production RAG vector database with `RAG_VECTOR_STORE=qdrant`, Qdrant REST indexing for uploaded/seeded document chunks, Qdrant-first retrieval, and SQLite/local-vector fallback only for tests or degraded disconnected use.
- Added vector-store status to Learning Review so reviewers can see the active RAG store, collection, and availability state.
- Updated local full-stack and local Kubernetes runners so production-like runs start/deploy Qdrant alongside NATS, backend, and frontend.
- Updated README, architecture, RAG+PEFT+NATS design, and goal tracker to describe Qdrant-backed RAG, async learning defaults, and remaining production work.

Checks run:

- `bash -n scripts/run-local-stack.sh`
- `bash -n scripts/run-local-k8s.sh`
- `PYTHONPYCACHEPREFIX=/tmp/maintenance-wizard-pycache python3 -m compileall backend/app`
- `backend/.venv/bin/pytest backend/tests/test_api.py`
- `npm --prefix frontend run test`
- `npm --prefix frontend run build`
- `npm --prefix frontend run test:e2e` with browser-launch escalation after the sandboxed Chromium run was blocked
- `git diff --check`
- Completion notification attempted with both local and repository helpers; delivery failed because `ntfy.sh` could not be resolved in this environment.

Next G-016 implementation items:

- Add durable NATS learning workers for judge, dataset, evaluation, and PEFT jobs.
- Add bundled PEFT trainer templates for local Qwen/SLM LoRA or QLoRA training.
- Add production embedding model selection/versioning and Qdrant collection migration controls.
- Track object-store bucket hardening, Postgres migration, and environment-specific LM Studio/Ollama loader integration as future production phases outside the current local-Mac-constrained G-016 scope.

## Current Status

An initial end-to-end prototype is implemented and verified, and current work is moving it toward production-ready architecture. It includes a FastAPI backend, React/Vite frontend, bundled sample data, SQLite persistence seeded from sample data, Qdrant-backed production RAG with SQLite/local-vector fallback, deterministic recommendation safeguards, rolling-baseline anomaly detection, risk/RUL heuristics, feedback persistence, async learning job records, Markdown report export, setup documentation, and local stack scripts.

The active goal is complete for a working hackathon prototype. Remaining items are production extensions, not blockers for the requested prototype.

## Completed

- Created Codex Goal for the project objective.
- Created `docs/implementation-plan.md` with the implementation plan.
- Created `docs/progress.md` for cross-session tracking.
- Updated `AGENTS.md` to require end-of-session progress updates.
- Added backend scaffold under `backend/` with FastAPI app, Pydantic schemas, service modules, and API tests.
- Added sample steel-plant data under `assets/sample_data/steel_plant_demo.json`.
- Added frontend scaffold under `frontend/` with React, TypeScript, Vite, dashboard UI, engineer query flow, recommendation panel, and feedback buttons.
- Added `.env.example`, `.gitignore`, `README.md`, `docs/architecture.md`, and `docs/demo_script.md`.
- Installed frontend and backend dependencies locally.
- Verified live backend and frontend interaction through the in-app browser.
- Added SQLite schema and repository layer for equipment, alerts, spares, maintenance events, documents, and feedback.
- Seeded SQLite from `assets/sample_data/steel_plant_demo.json` on startup.
- Refactored risk, retrieval, recommendation, ingestion, and feedback paths to use SQLite-backed repositories.
- Added ingestion tests proving documents and alerts persist through repository/API paths.
- Replaced deprecated FastAPI startup event with a lifespan handler.
- Added persisted `document_chunks` index with deterministic hashed embeddings.
- Refactored evidence retrieval to rank SQLite document chunks by local vector similarity plus lexical score, while preserving maintenance history evidence.
- Added tests for seeded chunks, ingested document chunks, and retrieval evidence from chunk ids.
- Implemented OpenAI-compatible and Ollama LLM clients with structured JSON validation.
- Added deterministic fallback for missing credentials, network errors, malformed JSON, and validation failures.
- Merged validated LLM suggestions into root causes, immediate actions, planned actions, confidence, and report summary.
- Added LLM adapter tests for mock, OpenAI parsing, OpenAI fallback, and Ollama parsing.
- Added persisted `sensor_readings` records seeded from sample time-series data.
- Added rolling-baseline anomaly detection using z-score, threshold breach, and trend delta.
- Added anomaly API endpoints for sensor readings and anomaly findings.
- Fed anomaly findings into health scoring, prediction probability, RUL drivers, and frontend asset detail UI.
- Added tests for seeded readings, anomaly detection, health anomaly notes, and prediction anomaly drivers.
- Added Markdown report export endpoint for structured maintenance decision reports.
- Added frontend export link in the recommendation panel.
- Added Vitest and Testing Library frontend tests for dashboard, anomaly rendering, diagnosis, evidence, and report export link.
- Added document file upload ingestion for text-like files and PDFs.
- Parsed uploaded files into SQLite documents and retrieval chunks.
- Added tests for text file upload, chunk indexing, retrieval over uploaded content, and unsupported file rejection.
- Added SQLite schema metadata, database status, init, and reset tooling.
- Added production hardening notes, submission packaging guide, and completion audit.
- Added `docs/rules.md` and `docs/hooks.md` for durable engineering rules, branch/PR guardrails, verification hooks, and handoff checks.

## Next Steps

1. Production extension: add stronger embedding model selection/versioning and Qdrant collection migration controls.
2. Optional production extension: add OCR for scanned PDFs.
3. Optional production extension: add authentication and role-based access control.

## Decisions

- Stack: FastAPI backend with React and TypeScript frontend.
- LLM integration: provider-agnostic adapter.
- Storage: SQLite plus local vector store.
- Scope: end-to-end hackathon prototype.
- Progress tracking: update this file at the end of each implementation session.
- Live LLM calls remain deferred in this slice; deterministic fallback reasoning is used so the app runs without secrets.
- Dev servers should bind to `127.0.0.1` in this environment; binding to `0.0.0.0` is blocked by sandbox permissions.
- SQLite database path defaults to `backend/data/maintenance_wizard.db` and can be overridden with `DATABASE_PATH`.
- Local retrieval uses deterministic hashed embeddings in SQLite for offline demo reliability; it is replaceable with a production embedding model later.
- LLM providers are now callable when configured, but fallback remains the default for reliable local demos without secrets.
- Anomaly detection uses rolling population z-score over recent readings and threshold breach flags; it is deterministic and explainable for demo use.
- The goal is considered complete as a working hackathon prototype; production hardening items are documented separately.
- Branch work intended for `main` must happen on a feature branch and be raised as a pull request targeting `main`.

## Open Questions

- None currently.

## Commands Run

- `pwd`
- `rg --files -uu`
- `ls -la`
- `file '/Users/ragaven/Downloads/AI Hackathon _ Round 2 - Agentic AI Challenge _ Problem Statement.docx (1)679a47f.pdf'`
- PDF text extraction using bundled Python runtime and `pypdf`
- `mkdir -p docs`
- `python3 -m compileall backend/app` failed due sandboxed bytecode cache permissions.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed.
- `npm install`
- `npm run build` failed once due TypeScript module resolution deprecation, then passed after updating `frontend/tsconfig.json`.
- `python3 -m venv .venv`
- `.venv/bin/pip install -r requirements.txt`
- `.venv/bin/pytest` passed with 5 tests.
- `curl -s http://127.0.0.1:8000/api/health` returned `{"status":"ok","service":"maintenance-wizard-api"}`.
- `curl -s http://127.0.0.1:8000/api/dashboard/summary` returned 3 equipment records and 3 active alerts.
- Started FastAPI at `http://127.0.0.1:8000`.
- Started Vite at `http://127.0.0.1:5173`.
- Added SQLite persistence files and repository layer.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed after SQLite refactor.
- `.venv/bin/pytest` passed with 7 tests.
- `npm run build` passed after SQLite refactor.
- Restarted FastAPI at `http://127.0.0.1:8000`.
- `curl -s -X POST http://127.0.0.1:8000/api/ingest/documents ...` returned `{"status":"stored","documents":1}`.
- Added SQLite `document_chunks` index and deterministic local embedding utilities.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed after retrieval-index refactor.
- `.venv/bin/pytest` passed with 9 tests.
- `npm run build` passed after retrieval-index refactor.
- Implemented live OpenAI/Ollama LLM adapter support with structured response validation.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed after LLM adapter refactor.
- `.venv/bin/pytest` passed with 13 tests.
- `npm run build` passed after LLM adapter refactor.
- Added time-series sensor readings and rolling-baseline anomaly detection.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed after anomaly refactor.
- `.venv/bin/pytest` passed with 17 tests.
- `npm run build` passed after anomaly UI update.
- Restarted FastAPI at `http://127.0.0.1:8000`.
- `curl -s http://127.0.0.1:8000/api/equipment/RM-DRIVE-01/anomalies` returned vibration and bearing-temperature anomaly findings.
- Browser verification confirmed the dashboard renders the Sensor Anomalies panel.
- Added Markdown report export and frontend export link.
- `.venv/bin/pytest` passed with 18 tests.
- `npm run test` passed with 2 frontend tests.
- `npm run build` passed after report export UI update.
- Restarted FastAPI at `http://127.0.0.1:8000`.
- `curl -s http://127.0.0.1:8000/api/reports/RM-DRIVE-01/markdown` returned a structured Markdown report.
- Added `python-multipart` and `pypdf` dependencies for document upload parsing.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed after document parser addition.
- `.venv/bin/pytest` passed with 20 tests.
- `npm run test` passed with 2 frontend tests.
- `npm run build` passed after document upload addition.
- Restarted FastAPI at `http://127.0.0.1:8000`.
- `curl -s -X POST http://127.0.0.1:8000/api/ingest/document-file ...` returned `{"status":"stored","documents":1,...}`.
- Added `python -m app.manage db-status`, `init-db`, and `reset-db`.
- `.venv/bin/python -m app.manage db-status` returned schema version `1` and seeded table counts.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app` passed after final tooling.
- `.venv/bin/pytest` passed with 21 tests.
- `npm run test` passed with 2 frontend tests.
- `npm run build` passed.
- Live API health and dashboard checks passed.
- Browser audit confirmed dashboard, sensor anomalies, engineer query, diagnosis, evidence, and export report flow.
- Added and refined `docs/rules.md` and `docs/hooks.md` with source-control, verification, progress, branch/PR, and handoff guardrails.

## Session Notes

### 2026-06-06

- Reviewed the problem statement PDF.
- Converted the high-level problem into an implementation plan.
- Created a Codex Goal for multi-session continuity.
- Added repository-tracked planning and progress files.
- Implemented the first working vertical slice across backend, frontend, sample data, tests, and docs.
- Verified the live UI shows API-connected dashboard data, supports diagnosis, and renders cited recommendations with feedback controls.
- Implemented SQLite persistence and repository boundaries.
- Verified backend tests, frontend build, and live SQLite-backed document ingestion.
- Implemented persisted local chunk/vector retrieval.
- Verified chunk persistence, ingested-document chunking, retrieval evidence, backend tests, and frontend build.
- Implemented live provider adapters with fallback-safe structured output handling.
- Verified LLM adapter parsing/fallback tests, backend test suite, and frontend build.
- Implemented time-series anomaly detection and anomaly-aware risk scoring.
- Verified anomaly API output, backend tests, frontend build, and browser-rendered Sensor Anomalies panel.
- Implemented Markdown report export and frontend test coverage.
- Verified backend tests, frontend tests, frontend build, and live Markdown report export.
- Implemented file upload document parsing and indexing.
- Verified upload parser tests, backend test suite, frontend tests, frontend build, and live multipart document upload.
- Implemented final database tooling, production hardening docs, submission guide, and completion audit.
- Verified backend compile, backend tests, frontend tests, frontend build, database status, live API, and browser workflow.
- Added durable rules and hooks documentation, including no direct commits/pushes to `main`.
- Created private GitHub repository `ragavendran-r/ai-powered-maintenance-wizard` and pushed initial commit `1eac0cc`.
- GitHub-side main branch protection could not be enabled because GitHub rejected branch protection and repository rulesets for this private repo on the current plan.
- Added a versioned local pre-push hook on branch `chore/github-guardrails` to block direct pushes to `main` or `master`.
- Updated `docs/architecture.md` with a Mermaid system diagram covering frontend, FastAPI APIs, ingestion, retrieval, anomaly/risk services, LLM fallback, SQLite persistence, reports, and feedback.
- Reviewed requested feature coverage against the current implementation. `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`, `.venv/bin/pytest`, `npm run test`, `npm run build`, and a FastAPI smoke check for diagnosis, prediction, anomalies, and Markdown reports passed. Main caveat: degradation/RUL and anomaly detection are heuristic prototype models, not calibrated production predictive models.
- Reviewed ingestion modes, LLM involvement, and continuous-improvement support. Current ingestion is available through startup fixture seeding, structured record API, JSON document API, and multipart document upload API; no frontend ingestion screen exists yet. LLMs are invoked through recommendation generation for diagnose/chat/report flows only. Feedback is stored for future learning but is not yet consumed by retrieval, prompts, ranking, or prediction.
- Implemented missing feature pass: frontend ingestion panel, expanded recommendation details, equipment-linked detailed feedback capture, feedback reuse in recommendation context/ranking, feedback-aware prediction drivers, updated documentation, and tests.
- Verification passed: `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`, `.venv/bin/pytest` with 23 tests, `npm run test` with 5 tests, `npm run build`, and live browser DOM checks for API-connected UI, diagnosis details, JSON ingestion, and detailed feedback fields. Browser screenshot capture timed out twice, so no screenshot artifact was saved.
- Merged PR #4 before new work, then created `docs/goal-tracker.md` as a separate goal ledger covering all goals and major session objectives from the beginning of the project.
- Merged PR #5 before new work, then refreshed `README.md` and `docs/architecture.md` to reflect the current ingestion UI, structured ingestion APIs, feedback-learning loop, LLM boundaries, schema version, API surface, and prototype limits.
- Added a durable completion-notification rule to `docs/rules.md`, `docs/hooks.md`, and `AGENTS.md` so a desktop notification is sent whenever a requested task is complete.
- Merged PR #7 before new work, then moved the complete ingestion section into a dedicated left-nav Ingestion view while keeping dashboard diagnosis and recommendation workflows separate. Verification passed with `npm run test`, `npm run build`, `git diff --check`, and browser DOM checks at `http://127.0.0.1:5173/`; PR #8 was opened from `feat/ingestion-view` to `main`.
- Merged PR #8 before new work, then added `HYD-SYS-04` Hot Rolling Hydraulic System and `OH-CRANE-05` Melt Shop Overhead Crane as tracked assets with alerts, anomaly-driving sensor readings, spares, maintenance history, SOP/manual retrieval evidence, frontend fallback data, dashboard full priority-list behavior, and docs. Verification passed with `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`, `.venv/bin/pytest` with 25 tests, `npm run test` with 5 tests, `npm run build`, database reset/status counts, live dashboard count check, and live diagnosis smoke checks for both assets. Opened PR #9 from `feat/add-equipment-assets` to `main`: `https://github.com/ragavendran-r/ai-powered-maintenance-wizard/pull/9`.
- Created the NATS JetStream async IoT streaming ingestion goal, documented the implementation plan in `docs/iot-streaming-ingestion-plan.md`, and started the prerequisite asset visibility fix before streaming implementation.
- Merged PR #10 with the streaming goal docs and asset visibility fix, then implemented optional NATS JetStream IoT streaming ingestion on `feat/nats-iot-streaming-ingestion`. Added backend configuration, schema version 3 `streaming_messages`, message validation/idempotency, durable consumer service, DLQ handling, retry/nak behavior, `/api/streaming/status`, frontend IoT Stream status panel, tests, and docs. Verification passed with backend compile, `.venv/bin/pytest` with 31 tests, `npm run test` with 5 tests, `npm run build`, live streaming status check, live dashboard `5 5` check, and live Vite source check. Opened PR #11: `https://github.com/ragavendran-r/ai-powered-maintenance-wizard/pull/11`.
- Live-tested the NATS IoT flow using Docker NATS JetStream and `nats-py`. Installed `nats-py` in the backend venv, started backend with `STREAMING_ENABLED=true`, fixed `ack_wait` compatibility for `nats-py`, verified valid sensor/alert messages were consumed and persisted, verified invalid messages incremented `failed_count` and were published to `steelplant.iot.dlq`, and added local smoke-test steps to `docs/iot-streaming-ingestion-plan.md`.
- Added `scripts/run-local-stack.sh` to run NATS JetStream, the streaming-enabled backend, and the Vite frontend from one command, with status/stop subcommands and local logs under `.local-stack/`. Opened PR #12: `https://github.com/ragavendran-r/ai-powered-maintenance-wizard/pull/12`.
- Added copy/paste sample NATS alert publish steps to `docs/iot-streaming-ingestion-plan.md` so the IoT flow can be tested quickly from a running local stack.
- Created Codex Goal G-013 for user login and role-based access control. Verified no open PRs before starting. Began documentation-first work on `auth-rbac-plan-docs` with a dedicated auth/RBAC implementation plan, goal tracker entry, README update, and architecture update.
- Implemented G-013 on `feat/auth-rbac`: added schema version 4 local users and auth audit tables, bcrypt password hashing, JWT login/current-user/logout endpoints, FastAPI role guards, admin user-management APIs, React login/session restoration/logout, role-gated navigation and actions, authenticated Markdown report download, admin Users view, auth config docs, and tests. Verification passed with backend compile, `.venv/bin/pytest` with 37 tests, `npm run test` with 7 tests, `npm run build`, and `git diff --check`.
- Fixed `scripts/run-local-stack.sh status` after auth enforcement so it obtains the seeded demo admin token before checking protected streaming status. Verified local stack status returns NATS health, backend health, authenticated streaming status, and frontend OK.
- Added a steel-plant favicon asset for the browser tab on `feat/steel-plant-favicon`, using a compact furnace/crane/molten-steel SVG badge linked from the Vite HTML entrypoint.
- Repositioned the dashboard diagnosis workflow on `feat/reposition-diagnosis-recommendation`: moved the `Diagnose` action above `Engineer Query`, moved the recommendation section into the middle asset detail pane at the bottom, changed the dashboard to a two-column layout, and added frontend regression assertions for the requested ordering.
- Created Codex Goal G-014 for a local Kubernetes deployment script. Started `feat/local-k8s-deploy` with a Kind-based runner that creates a disposable local cluster, builds/loads backend and frontend images, loads NATS, deploys all components, reports status, and deletes the cluster/runtime files from the same script.
- Completed G-014 documentation and verification tracking. Static script validation passed with `bash -n scripts/run-local-k8s.sh`, help output passed with `scripts/run-local-k8s.sh --help`, and `git diff --check` passed. Full live Kind deployment is pending because `kind` is not installed in this local environment; `scripts/run-local-k8s.sh status` correctly reports that missing prerequisite.
- Updated `scripts/run-local-k8s.sh` so the local Kubernetes runner installs Kind automatically when it is missing, preferring Homebrew and falling back to Go. `KIND_AUTO_INSTALL=false` preserves fail-fast behavior for locked-down environments.
- While running the Kubernetes stack, `kind load docker-image nats:2` failed on Docker image metadata. Added a direct containerd import fallback to `scripts/run-local-k8s.sh` so third-party images such as NATS can still load into the Kind node.
- While browser-testing the Kubernetes frontend, login failed due CORS because the backend allowed only the Vite dev origins. Added configurable `CORS_ALLOW_ORIGINS` support and set the Kubernetes backend deployment to allow the exposed frontend port.
- Updated the Kubernetes runner to restart backend and frontend deployments after applying manifests so reruns pick up rebuilt local images that use stable `:local-k8s` tags with `imagePullPolicy: Never`.
- Updated the dashboard diagnosis/query layout so `Diagnose` is centered in the detail pane, the Engineer Query send button aligns to the same centerline, and the query text box is a three-row textarea. Verified with frontend tests/build and live Kubernetes browser measurement.
- Fixed the Users administration view by changing dark status-action buttons to light teal action buttons and moving password reset into an overlay dialog opened only from the Reset action. Verified with frontend tests/build and the live Kubernetes browser view.
- Fixed `scripts/run-local-stack.sh stop` so it no longer depends only on stale/missing PID marker files. The stop command now also stops backend/frontend listeners on the configured ports and stops the named NATS container.
- Created a Codex goal for LLM/SLM leverage across predictive analytics, anomaly detection, and knowledge retrieval. Implemented on local branch `feat/llm-slm-leverage` after the first branch-creation approvals were rejected and the retry succeeded.
- Added generic structured LLM/SLM response support to the provider adapter while preserving deterministic mock fallback behavior.
- Added document intelligence extraction for ingested documents, persisted in schema version 5 `document_intelligence` records.
- Added maintenance history and feedback labeling into normalized `maintenance_labels` with failure mode, component, root cause, action class, outcome status, signal hints, and training usability.
- Added optional LLM/SLM retrieval reranking with evidence relevance reasons, anomaly context classification with inspection steps, and prediction/recommendation reasoning explanations.
- Wired labels into prediction drivers and bounded risk adjustment while keeping final anomaly scores, risk level, failure probability, and RUL deterministic.
- Updated frontend API types and UI displays for ingestion intelligence counts, anomaly context classes, recommendation reasoning explanations, and evidence relevance reasons.
- Updated `README.md` and `docs/architecture.md` for LLM/SLM leverage, schema version 5, new endpoints, data flow, and prototype boundaries.
- Verification passed: `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`, `cd backend && .venv/bin/pytest` with 40 tests, `cd frontend && npm run test` with 8 tests, and `cd frontend && npm run build`.
- Added `assets/ingestion_samples/` with upload-ready sample files for `sop`, `manual`, `log`, `alert`, `spares`, and `history` source types, plus a README mapping each source type to its file. Verified with `git diff --check`.
- Added `scripts/notify-complete.sh` and updated `docs/rules.md`, `docs/hooks.md`, and `AGENTS.md` so completed tasks send both desktop and mobile notifications when configured. Mobile delivery uses `MOBILE_NTFY_TOPIC`; if the mobile channel is not configured or fails, the final response must mention it.
- Persisted the local mobile notification topic in ignored `.env` as `MOBILE_NTFY_TOPIC=codex-alert` and updated `scripts/notify-complete.sh` to source `.env` automatically, so future task-completion notifications can use the same mobile topic without tracking the topic in Git.
- Installed a user-level notification command at `~/.local/bin/codex-notify-complete` and exported `MOBILE_NTFY_TOPIC=codex-alert` from `~/.local/bin/env`, which is sourced by the user's shell. Updated the project helper to delegate to the global command when available so desktop and mobile task-completion notifications can work across projects and future sessions.
- Investigated the reported `RM-DRIVE-01_SOP_main_drive_bearing_vibration.md` upload failure. The exact file uploaded successfully via `/api/ingest/document-file`, but backend logs showed intermittent `sqlite3.OperationalError: database is locked` on concurrent startup/auth/status requests. Fixed repository readiness so SQLite schema/seed initialization runs once per process behind a lock, added a concurrency regression test, restarted the local stack, and verified the exact sample upload returns `200 OK` with extracted document intelligence and no new lock errors.
- Verified every bundled ingestion sample file through the running local API, including `BF-BLOWER-02_MANUAL_inlet_guide_vane_actuator.txt`; all six returned `200 OK` with stored documents and extracted intelligence. Added frontend regression coverage that uploads all bundled samples with their intended source type and target asset, and excluded test files from the production TypeScript build so Node-only Vitest helpers do not affect app compilation.
- Started the reference-layout operations experience on `codex/operations-work-orders-ai`: added schema version 6 work-order and work-order-log tables with seeded demo orders; added repository/API support for work-order list, create, detail, update, and log operations; added technician and supervisor assistant endpoints with optional LLM/SLM structured output and deterministic fallback; added a redesigned operational dashboard, dedicated asset detail screen, work-order list/detail/execution/review screen, lightweight charts, AI explanation popover, technician assistant panel, and supervisor assistant panel. Verification passed with backend compile, backend tests (`45 passed`), frontend tests (`10 passed`), frontend build, live browser checks for dashboard/asset/work-order assistant flows, and mobile-width dashboard overflow check.
- Tightened work-order AI assistants on `codex/role-gated-work-order-ai-assistants`: added seeded `maintenance_technician` and `maintenance_supervisor` users, restricted technician and supervisor assistant APIs to their respective roles, kept work-order execution/review actions available to those roles, and hid non-matching assistant panels in the UI. Verification passed with backend compile, backend tests (`45 passed`), frontend tests (`12 passed`), frontend build, `git diff --check`, and a live browser smoke test confirming admin sees no assistant, technician sees only Technician AI Assistant, and supervisor sees only Supervisor AI Assistant.

### 2026-06-12

- Created branch `feat/lm-studio-local-llm` for LM Studio local LLM setup.
- Installed LM Studio via Homebrew cask; the app is now available at `/Applications/LM Studio.app`.
- Linked LM Studio's bundled CLI to `/opt/homebrew/bin/lms`; `lms --help` works and `lms server status` reports the server is not running.
- Updated `AGENTS.md` so it describes the actual FastAPI/React project layout, verification commands, and LM Studio local LLM conventions.
- Added LM Studio configuration guidance to `.env.example` and `README.md`.
- Added `docs/local-llm-lm-studio.md` with install, model selection, MacBook Air M4 sizing, `.env`, smoke-test, app verification, cost/license notes, and references.
- Updated ignored local `.env` to point the backend at LM Studio through `LLM_PROVIDER=openai`, `OPENAI_BASE_URL=http://localhost:1234/v1`, `OPENAI_API_KEY=lm-studio-local`, `OPENAI_MODEL=qwen2.5-7b-instruct`, and `LLM_TIMEOUT_SECONDS=45`.
- Downloaded `Qwen2.5 7B Instruct Q4_K_M [GGUF]` into LM Studio from `https://huggingface.co/Qwen/Qwen2.5-7B-Instruct-GGUF`; the model files are present under `~/.lmstudio/models/Qwen/Qwen2.5-7B-Instruct-GGUF/`.
- Verified LM Studio's OpenAI-compatible `/v1/models` endpoint from the host shows `qwen2.5-7b-instruct`.
- Updated backend settings so the repo-root `.env` is loaded reliably even when the backend is launched from `backend/`.
- Updated the OpenAI-compatible LLM adapter to request `response_format.type=json_schema`, which LM Studio accepts, instead of `json_object`, which LM Studio rejected.
- Verified `configured_llm_client()` from `backend/` reads the root `.env` and returns a live LM Studio response with `used_live_provider=true`, provider `openai`, model `qwen2.5-7b-instruct`, and a valid bounded confidence adjustment.
- Added a regression assertion that OpenAI-compatible requests send a JSON Schema response format, and forced API tests to use `LLM_PROVIDER=mock` so local `.env` values do not make normal tests call live local models.
- Verified tracked changes with `git diff --check`.
- Verified backend compile outside sandbox restrictions with `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`.
- Verified backend tests outside sandbox restrictions with `cd backend && LLM_PROVIDER=mock .venv/bin/pytest` (`45 passed`).
- Full `/api/diagnose` live smoke through FastAPI `TestClient` was stopped after running too long because the full recommendation path can trigger multiple local-model enrichment calls. The narrower backend LLM client smoke proves provider configuration and structured parsing; use shorter live endpoint checks or temporarily disable optional enrichment when doing repeated local model API testing.
- Converted the Technician AI Assistant and Supervisor AI Assistant from one-shot forms into chat-style transcripts with explicit `Send` buttons, while keeping `Submit completed work` as the technician work-order closeout action. The Engineer Query button now has a visible `Send` label, and the recommendation panel exposes the primary provider badge (`Live LLM` or fallback).
- Narrowed technician/supervisor LLM schemas to internal chatbot-only contracts so LM Studio/Qwen does not have to generate backend-owned evidence and work-order objects. Public API response shapes remain unchanged.
- Verified LM Studio server live outside the sandbox at `http://localhost:1234/v1/models` with `qwen2.5-7b-instruct`, and verified a direct JSON Schema chat completion from Qwen2.5.
- Verified app routes with LM Studio/Qwen2.5: Technician AI Assistant returned `provider=openai` and `used_live_provider=true`; Supervisor AI Assistant returned `provider=openai` and `used_live_provider=true`; Engineer Query returned recommendation `provider=openai` and `used_live_provider=true` while its secondary reasoning explanation fell back after the local route took several minutes.
- Restored the dashboard engineer-query experience as an always-visible right-pane chatbot named Neo. Neo is available to all signed-in dashboard users, uses the shared LLM adapter, and can return center-dashboard result tables for assets, work orders, or users with user data scoped by role.
- Verified Neo with backend tests (`47 passed`), frontend tests (`13 passed`), frontend build, backend compile, `git diff --check`, live operator browser smoke at `http://127.0.0.1:5173`, LM Studio `/v1/models` showing `qwen2.5-7b-instruct`, and a live `/api/neo/chat` response returning `used_live_provider=true` with a work-order table.
- Refined the dashboard Neo layout on `codex/neo-center-dashboard`: moved Neo into the dashboard center column, kept Equipment Efficiency in the right column, added a visible loading spinner/disabled composer while Neo waits for an LLM response, and changed table responses to compact chat summaries with full details shown only in the result table. Verification passed with frontend tests (`13 passed`), frontend build, `git diff --check`, and live browser checks for center/right layout, spinner state, compact transcript, and populated result table.
- Fixed Neo table-query latency on `codex/neo-centered-above-work-queue` by routing asset, work-order, and user table requests through deterministic repository queries instead of waiting on LM Studio/Qwen. Added role filters such as `list only operators`, kept non-table prompts on the LLM path, changed deterministic UI labels to `Dashboard data`, and made Neo's asset table use lightweight equipment/alert data. Verification passed with backend Neo tests (`4 passed`), full backend tests (`49 passed`), frontend tests (`13 passed`), frontend build, `git diff --check`, live API timing for assets/work orders/users/operators (`1-8 ms`, `provider=deterministic`, `used_live_provider=false`), and a headless Chrome screenshot at `/var/folders/31/d7kq0n_x3l9b_xt0vdzj8gvh0000gn/T/neo-operators-dashboard.png`.
- Diagnosed Neo general-query fallback on `codex/neo-general-query-fallback`: LM Studio's `/v1/models` endpoint was reachable, but chat completions timed out and `lms ps` reported the LM Studio daemon could not start/connect. Restarted the LM Studio server with `lms server stop` and `lms server start`, added plain-text LLM completion support for Neo general maintenance questions, shortened the Neo-specific completion budget, and added indexed evidence fallback for slow model responses. Verified the exact prompt `how to inspect Blast Furnace Combustion Air Blower` returned a live Qwen response through `/api/neo/chat` with `used_live_provider=true`, `provider=openai`, and `elapsedMs=16192`; backend compile, full backend tests (`50 passed`), and `git diff --check` passed.
- Formatted Neo general-query responses in the dashboard chat: live/fallback assistant text is rendered as headings, numbered lists, bullets, and bold inline text instead of exposing raw Markdown syntax. The evidence fallback now emits `Safety Checks`, `Inspection Steps`, `Closeout`, and `Evidence Used` sections. Verification passed with frontend tests (`14 passed`), frontend build, full backend tests (`50 passed`), `git diff --check`, and browser screenshot `/var/folders/31/d7kq0n_x3l9b_xt0vdzj8gvh0000gn/T/neo-formatted-response-scrolled.png`.
- Standardized application button styling by adding shared button theme variables and global primary/secondary/icon button variants in `frontend/src/styles.css`. Dashboard Neo Send, Quick actions, ingestion Upload/Import JSON, login/logout, report, modal, feedback, and user-management buttons now share consistent radius, weight, spacing, focus, disabled, and hover behavior. Added a durable button-variant rule to `docs/rules.md`. Verification passed with backend compile, full backend tests (`50 passed`), frontend tests (`14 passed`), frontend build, `git diff --check`, and browser screenshots `/var/folders/31/d7kq0n_x3l9b_xt0vdzj8gvh0000gn/T/button-theme-dashboard-actions.png` and `/var/folders/31/d7kq0n_x3l9b_xt0vdzj8gvh0000gn/T/button-theme-ingestion-actions.png`.
- Added PR-description guardrails to `AGENTS.md`, `docs/hooks.md`, and `docs/rules.md`: future pull request descriptions must not include verification steps, test commands, screenshots, logs, local file paths, or local image paths.
- Added streaming Neo responses on `codex/local-llm-15s-cap`: capped local LLM text/structured token budgets, exposed `/api/neo/chat/stream` as server-sent events, taught the frontend API client to consume SSE, updated Neo to render tokens as they arrive while keeping the composer disabled until completion, and documented the LM Studio 15-second response target. Verification passed with backend compile, targeted backend tests (`54 passed`), frontend tests (`14 passed`), frontend build, `git diff --check`, and a live browser check showing first streamed Neo text in about 5.1 seconds with the final response formatted without raw Markdown.
- Increased Neo's local free-text output budget on `codex/neo-complete-llm-output` from 250 to 600 tokens and tightened the prompt so Qwen completes the response within the configured limit instead of ending on an unfinished heading. Updated `.env.example`, README, and LM Studio docs to use `LLM_TEXT_MAX_TOKENS=600`; also updated the ignored local `.env` so the running stack uses the new budget. Verification passed with backend compile, targeted backend tests (`54 passed`), `git diff --check`, and a live browser check confirming the blower-inspection response finished without a trailing orphan heading.
- Renamed the role-specific work-order assistants on `codex/role-assistant-names`: the technician and supervisor assistants initially used separate visible names. Updated backend system prompts, React panel headings/transcript speaker labels, role-gated UI tests, README, local LM Studio docs, and architecture notes to clarify that both assistants use the shared LLM configuration.
- Streamed role-specific work-order assistant chat responses on a role-assistant streaming branch: added role-gated SSE endpoints, frontend streaming transcript updates, spinner/disabled Send states while awaiting first response, final structured event handling for app-owned work-order fields, and a separate local LLM stream timeout so slow LM Studio/Qwen first tokens do not immediately fall back. Verification passed with backend compile, backend/API/LLM tests (`56 passed`), frontend tests (`14 passed`), frontend build, `git diff --check`, stack status, and live browser checks confirming both role assistants showed spinners, streamed `Live LLM · openai` responses, and re-enabled Send after completion.
- Moved the role-specific work-order assistants into the Work Orders center pane above the work-order table on `codex/work-order-center-assistants`, with Neo-style composer controls that keep Send below the input. Added admin/supervisor assignment controls backed by a technician lookup API, filtered technician work-order lists to assigned work only, seeded `WO-8304` to the demo technician, and moved Submit completed work below the technician work-order table. Verification passed with backend compile, backend tests (`51 passed`), frontend tests (`14 passed`), frontend build, `git diff --check`, and live browser layout checks for supervisor and technician roles.
- Updated work-order workflow actions on `codex/work-order-quick-actions-approval`: moved Quick actions into the left navigation pane, tightened work-order table typography and columns to avoid horizontal scroll, limited Approve to `WAPPR` work orders only, added assigned-technician `Start work` from `APPR` or `WMATL` to `INPRG`, enforced assigned-technician update rules in the API, and scoped fallback work-order rows by technician assignment. Verification passed with backend compile, backend tests (`54 passed`), frontend tests (`14 passed`), frontend build, `git diff --check`, and live browser checks for admin and technician work-order actions.
- Started data-backed asset details on `codex/data-driven-assets-page`: added schema version 7 asset profile, metric snapshot, recommendation, subsystem, and reliability metric tables; added `assets/sample_data/asset_detail_seed.sql` for initial DB setup; seeded extra SOP/manual/log/history evidence; exposed `/api/assets` and `/api/assets/{equipment_id}`; added a left-nav Assets page with a company asset table; and rewired asset detail tabs to render API-provided profile, metrics, recommendations, maintenance history, work orders, performance charts, reliability, documents, retrieval evidence, and prediction drivers instead of frontend-authored detail values.
- Refined data-backed asset details on `codex/data-driven-assets-page`: corrected the Assets table grid placement so it sits beside the left navigation, added sectioned asset-detail API loading so Summary can render before heavier tabs, and removed duplicated Summary sections from Maintenance, Performance, Reliability, Documents, and Work Orders tabs.

### 2026-06-13

- Fixed asset-detail tab whitespace and Morpheus diagnosis streaming on `codex/data-driven-assets-page`: asset tab content now stays directly under the tab row, Summary no longer shows duplicated maintenance/performance sections, Morpheus uses `/api/diagnose/stream` with the same shared local LLM streaming client pattern as Neo, the Diagnose action shows a spinner/disabled state while streaming, and streamed Markdown now appends tokens without inserting artificial newlines. Verification passed with backend compile, backend tests (`66 passed`), frontend tests (`15 passed`), frontend build, `git diff --check`, a live localhost SSE check returning immediate Morpheus events and Qwen tokens, and in-app browser checks for tab spacing, spinner state, streamed output, and formatted Morpheus response.
- Restricted Create work order actions to relevant work-order action roles on `codex/data-driven-assets-page`: global Quick actions, asset recommended actions, and Morpheus recommendation actions now render only for admin, maintenance engineer, maintenance technician, maintenance supervisor, reliability engineer, and planner roles. Added a defensive frontend create guard and backend/UI regression coverage for operator denial. Verification passed with backend compile, backend tests (`67 passed`), frontend tests (`15 passed`), frontend build, `git diff --check`, and browser checks confirming admin visibility and operator hiding on dashboard and asset detail.
- Consolidated visible work-order assistant identity under Neo on `codex/data-driven-assets-page`: technician and supervisor work-order assistant modes keep their role-gated workflows, structured final events, and streaming LLM configuration, but the UI, backend prompts, tests, and current docs now present the assistant as Neo.
- Completed the data-backed asset-detail seed coverage on `codex/data-driven-assets-page`: Summary now loads only summary datasets, every company asset has seeded maintenance history, related work order, performance readings, reliability metrics, and SOP/manual/log/history evidence, and asset API tests now prove sectioned loading and read-role protection including API-only denial. Updated README and architecture notes for schema version 7 and seed SQL behavior. Verification passed with backend compile, backend tests (`69 passed`), frontend tests (`15 passed`), frontend build, `git diff --check`, database seed-count audit, and browser checks for the Assets table beside the left nav plus the Continuous Caster Cooling Water Pump Summary, Maintenance, Performance, Reliability, Documents, and Work Orders tabs.
- Added page-following auto-scroll for Neo, Morpheus, and Smith streamed assistant panels and named the Reliability failure-prediction assistant Smith. Installed Playwright E2E validation, added `npm run test:e2e` and `npm run test:e2e:ui`, configured screenshots/traces/video on failure, and added a focused assistant-scroll smoke that mocks slow LLM streams while testing the real UI. Updated `AGENTS.md`, `docs/rules.md`, and `docs/hooks.md` so Playwright is the default validation path for future UI layout, streaming, navigation, role visibility, and interaction changes. Verification passed with frontend tests (`15 passed`), frontend build, `git diff --check`, local stack startup/status, and Playwright E2E (`1 passed`).
- Expanded dashboard Neo into a role-aware company command surface on `codex/data-driven-assets-page`: Neo can now retrieve asset maintenance, performance, reliability, and document summaries from backend data; provide assigned-work next steps for technicians; create critical-asset work orders for authorized roles; approve/start/complete work orders through guarded status rules; and let admins update user activation/role data. Deterministic table/action routes avoid waiting on the LLM for backend data operations, while general maintenance questions still use the shared streaming LLM path. Verification passed with targeted Neo backend tests (`13 passed`), full backend API tests (`68 passed`), frontend tests (`15 passed`), frontend build, and Playwright E2E (`1 passed` after rerunning with browser-launch escalation).
- Moved initial demo user records out of Python constants and into `assets/sample_data/users_seed.sql`. The database initializer now executes that SQL seed only when `AUTH_SEED_DEMO_USERS=true`, preserving the same eight demo accounts and `DemoPass123!` password while keeping initial user data in the seed-script set. Verification passed with full backend API tests (`68 passed`).
- Added role-aware Neo welcome behavior on `codex/data-driven-assets-page`: `/api/neo/welcome` now returns an immediate attention summary and table for each logged-in user role, including assigned technician work with completion guidance, supervisor approval/follow-up queues, engineering/planner asset review items, and read-only operator watch items. The dashboard loads that welcome after login/session restore and resets it on logout. Verification passed with targeted backend welcome tests (`3 passed`), full backend API tests (`71 passed`), frontend tests (`16 passed`), frontend build, and Playwright E2E (`1 passed` after browser-launch escalation).
- Added LLM-as-a-Judge scoring to the continuous-learning pipeline on `codex/data-driven-assets-page`: candidate examples are generated from accepted/corrected feedback, maintenance labels, completed work orders, approved assistant interactions, and documents; each example stores judge score, label, rationale, provider, and live/fallback status; approved examples below the default training threshold are blocked from export; recommendations and retrieval use only approved judge-qualified examples. Added reviewer APIs and UI for refreshing examples, rerunning the judge, toggling approval, creating/downloading JSONL snapshots, and tracking seeded model/prompt versions. Added `scripts/export-learning-dataset.py` for backend-venv JSONL export to support offline/local PEFT tuning. Updated README, architecture, and durable rules to describe the RAG + PEFT-ready flow and the rule that judge scoring is advisory while human approval and role checks remain authoritative. Verification passed with backend compile, backend tests (`75 passed`), frontend tests (`17 passed`), frontend build, `git diff --check`, JSONL export using the backend virtualenv, and Playwright E2E (`1 passed` after browser-launch escalation).
- Expanded the active continuous-learning goal into a production-ready RAG + PEFT + NATS design: added `docs/rag-peft-nats-learning-architecture.md`, updated README and architecture docs to include NATS-backed async learning jobs, added durable rules for RAG/PEFT/NATS learning and adapter promotion gates, and updated `docs/goal-tracker.md` with G-016 as the active in-progress goal. Added model-version registration and evaluation-run APIs/UI so adapter candidates and quality metrics can be tracked before promotion. Remaining production work is durable NATS learning workers, persisted job records, artifact storage, PEFT execution/orchestration, adapter promotion/rollback controls, and Postgres migration for multi-worker production use.
- Implemented the first production async-learning bridge for G-016: schema version 10 adds `learning_jobs`, repository helpers persist job input/output refs and status transitions, Learning Review actions now record refresh/judge/dataset/evaluation/adapter jobs, `/api/learning/jobs` lists job history, and `/api/learning/jobs/peft` queues a PEFT tuning request for the selected dataset/model/prompt. Added `LEARNING_ASYNC_ENABLED`, `LEARNING_NATS_STREAM`, `LEARNING_NATS_SUBJECT_PREFIX`, and `LEARNING_NATS_DLQ_SUBJECT`; when async learning is enabled, queued PEFT jobs are published to the `MW_LEARNING` NATS stream. The Learning Review UI now shows recent jobs and has a Queue PEFT tuning job action. Verification passed with backend compile, backend tests (`76 passed` including async publish coverage), frontend tests (`17 passed` after one timing-only rerun), frontend build, `git diff --check`, and Playwright E2E (`1 passed` after browser-launch escalation). Remaining production work is durable learning worker processes, artifact storage, PEFT execution/orchestration, adapter promotion/rollback controls, and Postgres migration for multi-worker deployment.
- Continued G-016 on `codex/learning-promotion-controls`: exposed evaluation-gated adapter promotion and rollback controls in Learning Review, added promotion audit history to the UI, added frontend API coverage for promotion endpoints, and updated docs so schema version 12 and promotion audit records are reflected. Verification passed with backend compile, backend tests (`78 passed`), frontend tests (`17 passed`), frontend build, and `git diff --check`.
- Continued G-016 on `codex/learning-promotion-controls`: added active promoted model-version resolution for real LLM providers, so Neo, Morpheus, Smith, recommendation, labeling, reranking, and document-intelligence clients use the active approved model id while `mock` remains deterministic for tests. Learning Review now displays the serving LLM source, provider, model, active version, and adapter path. Verification passed with backend compile, targeted backend learning tests (`6 passed`), full backend tests (`78 passed`), frontend tests (`17 passed`), frontend build, and `git diff --check`.
- Continued G-016 on `codex/learning-promotion-controls`: added a configurable learning artifact store with local filesystem as the default and S3-compatible storage for production-like MinIO/S3 deployments. PEFT worker artifacts now keep SHA-256 hashes, storage backend metadata, retained local paths, and `s3://` object URIs when configured. Learning Review now surfaces artifact-store status beside vector DB and serving-model status. Verification passed with backend compile, backend tests (`79 passed`), frontend tests (`17 passed`), frontend build, and `git diff --check`.
- Continued G-016 on `codex/learning-promotion-controls`: added optional external PEFT trainer execution for worker-processed tuning jobs. When `LEARNING_PEFT_TRAINER_COMMAND` is configured, the worker runs it without a shell, passes dataset/manifest/output locations through environment variables, enforces a timeout, stores trainer logs and adapter manifests, and registers the trained output as a candidate model version for evaluation-gated promotion. Learning Review now shows PEFT trainer mode/status. Verification passed with backend compile, backend tests (`80 passed`), frontend tests (`17 passed` after isolated rerun; the first concurrent run hit timing-only Vitest per-test timeouts), frontend build, and `git diff --check`.
- Continued G-016 on `codex/rag-embedding-versioning`: added production RAG embedding profile/version configuration and Learning Review visibility, reviewer-triggered RAG reindexing, Qdrant collection vector-size/migration status, embedding metadata on indexed chunks, learning-artifact retention policy status and dry-run cleanup helpers, and an optional Qwen/SLM LoRA/QLoRA trainer template for PEFT worker jobs. Added the durable project rule to use parallel agents for sizable split-safe tasks whenever available.
- Continued G-016 on `codex/learning-review-qdrant-validation`: Learning Review now reports approved learning-example Qdrant sync results after reviewer-triggered RAG reindex, and a focused Playwright E2E validates the UI against mocked Learning Review APIs. Verified with focused frontend test, full frontend test suite, frontend build, `git diff --check`, and Playwright E2E against a temporary isolated Vite server on port 5174. Remaining goal work is the final production-readiness audit and any real-stack Qdrant Learning Review smoke gaps.
- Centralized frontend role capability checks in `frontend/src/permissions.ts` and rewired navigation/action rendering in `App.tsx` to consume the shared permission map. Verification passed with frontend tests (`17 passed`), frontend build, and Playwright E2E (`1 passed`).
- Updated work-order UI on `codex/work-order-status-execution`: work-order status codes now render as readable label-only fixed-width badges with descriptions outside the badge, status timeline/detail/table copy uses shared status metadata, technician accounts see a step-by-step execution workflow card above Neo chat, application content typography now uses one shared 12px content font size while leaving headers, titles, and left navigation distinct, and the top header API status section has been removed. Verification passed with frontend tests (`17 passed`), frontend build, and Playwright E2E (`2 passed`).
- Cleaned up status rendering on `codex/status-labels-everywhere`: assistant markdown, assistant detail bullets, Neo result tables, supervisor fallback risk text, and status badge tooltips now translate work-order lifecycle codes to readable labels before display while preserving API payload codes for state transitions. Verification passed with frontend tests (`17 passed`), frontend build, Playwright E2E (`2 passed`), `git diff --check`, and a live browser check confirming the supervisor attention table shows labels with no raw lifecycle codes.

### 2026-06-14

- Broke `frontend/src/App.tsx` into routed feature modules on `codex/routed-feature-modules`: Dashboard, Assets, AssetDetail, WorkOrders, Ingestion, LearningReview, Users, and Auth now live under `frontend/src/routes/`; shared app model helpers, work-order status formatting, assistant rendering, and reusable UI components moved into dedicated modules while App keeps shell state, navigation, data loading, and route selection. Verification passed with frontend tests (`17 passed`), frontend build, `git diff --check`, Playwright E2E (`2 passed`), and an in-app browser smoke check of the login route.
