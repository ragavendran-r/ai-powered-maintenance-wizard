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

## Current Status

An initial end-to-end prototype is implemented and verified. It includes a FastAPI backend, React/Vite frontend, bundled sample data, SQLite persistence seeded from sample data, deterministic recommendation logic, SQLite-backed document chunk retrieval, rolling-baseline anomaly detection, risk/RUL heuristics, feedback persistence, Markdown report export, setup documentation, and a demo script.

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

1. Optional production extension: replace deterministic embeddings with a production vector database.
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
- Added `scripts/run-local-stack.sh` to run NATS JetStream, the streaming-enabled backend, and the Vite frontend from one command, with status/stop subcommands and local logs under `.local-stack/`.
