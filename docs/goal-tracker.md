# Goal Tracker

This file is the durable goal ledger for the Maintenance Wizard project. Use it to understand what goals have existed since project start, their status, related artifacts, verification, and follow-up state.

`docs/progress.md` remains the detailed session log. This file is the concise cross-session goal index.

## Status Legend

- `Complete`: Goal delivered and verified or intentionally closed.
- `Complete With Caveat`: Goal delivered, with an explicit limitation or external blocker.
- `In Progress`: Goal is currently being worked.
- `Blocked`: Goal cannot proceed without user input or an external state change.

## Current Goal State

- Active implementation goal: none.
- Latest completed tracked goal: G-014 local Kubernetes deployment script.
- Branch workflow rule: work intended for `main` must happen on a feature branch and merge through a PR.

## Goal Index

| ID | Goal | Status | Result | Primary Evidence |
| --- | --- | --- | --- | --- |
| G-001 | Convert the problem statement into an implementation plan and persistent tracking structure. | Complete | Created planning, progress, rules, hooks, and contributor guidance docs. | `docs/implementation-plan.md`, `docs/progress.md`, `AGENTS.md`, `docs/rules.md`, `docs/hooks.md` |
| G-002 | Build the initial AI-powered Maintenance Wizard hackathon prototype. | Complete | Implemented FastAPI backend, React frontend, SQLite persistence, sample steel-plant data, retrieval, LLM adapters, anomaly/RUL heuristics, recommendations, feedback, reports, tests, and docs. | Initial prototype commit `1eac0cc`; `docs/completion-audit.md`; `README.md` |
| G-003 | Create a private GitHub repository and enforce branch/PR guardrails. | Complete With Caveat | Created private repo and pushed initial bootstrap commit. Added local pre-push hook and PR guardrail docs. GitHub-side private repo branch protection/rulesets were blocked by current GitHub plan. | Repo `ragavendran-r/ai-powered-maintenance-wizard`; PR #1; `.githooks/pre-push`; `docs/hooks.md` |
| G-004 | Add an architecture diagram to explain the system. | Complete | Added Mermaid architecture/data-flow diagram covering frontend, API, ingestion, retrieval, anomaly/risk, LLM fallback, SQLite, reports, and feedback. | PR #2; `docs/architecture.md` |
| G-005 | Review feature coverage against the problem statement. | Complete | Verified the prototype covers diagnosis, root causes, RUL/risk heuristics, anomaly detection, prioritization, reports, reactive troubleshooting, and proactive planning, with caveats documented. | PR #3; `docs/progress.md`; `AGENTS.md` |
| G-006 | Review ingestion modes, LLM involvement, and continuous-improvement support. | Complete | Identified enabled ingestion modes, LLM call paths, and the gap that feedback was persisted but not yet reused. | PR #3; `docs/progress.md`; `AGENTS.md` |
| G-007 | Implement missing features from the audits. | Complete | Added frontend ingestion controls, full recommendation detail visibility, detailed engineer feedback capture, and feedback reuse in future recommendations, LLM prompt context, reports, and prediction drivers. | PR #4; commit `75ece10`; `frontend/src/App.tsx`; `backend/app/services/recommendations.py`; `backend/app/services/risk.py` |
| G-008 | Track all goals from project start in a separate markdown file. | Complete | Created this goal tracker as a standalone goal ledger. | `docs/goal-tracker.md` |
| G-009 | Review and update README and architecture docs. | Complete | Refreshed user-facing capabilities, ingestion examples, LLM boundaries, continuous-improvement behavior, API surface, data flow, and prototype limits. | `README.md`; `docs/architecture.md` |
| G-010 | Move ingestion into a separate left-nav view. | Complete | Moved document upload and JSON ingestion out of the asset detail panel into a dedicated Ingestion view accessible from the left navigation. | `frontend/src/App.tsx`; `frontend/src/App.test.tsx`; `frontend/src/styles.css` |
| G-011 | Add Hydraulic System and Overhead Crane assets. | Complete | Added two tracked steel-plant assets with alerts, sensor readings, spares, history, SOP/manual evidence, dashboard visibility, tests, and docs. | PR #9; `assets/sample_data/steel_plant_demo.json`; `frontend/src/App.test.tsx` |
| G-012 | Enable NATS JetStream IoT streaming ingestion. | Complete | Added optional durable NATS JetStream ingestion, validation, DLQ handling, `/api/streaming/status`, frontend status, tests, docs, and local stack runner. | PR #11; PR #12; PR #13; `docs/iot-streaming-ingestion-plan.md`; `scripts/run-local-stack.sh` |
| G-013 | Implement user login and role-based access control. | Complete | Added local SQLite users, bcrypt password hashes, JWT login, endpoint role guards, React login/session handling, role-gated navigation/actions, admin user management, tests, and docs. | `backend/app/core/auth.py`; `frontend/src/App.tsx`; `docs/auth-authorization-plan.md` |
| G-014 | Create a local Kubernetes deployment script. | Complete | Added and live-verified a Kind-based script that installs Kind when missing, creates a local cluster, deploys NATS, backend, and frontend, reports status, and deletes the cluster/runtime files. | `scripts/run-local-k8s.sh`; `README.md`; live Kind deployment |

## Detailed Goal Notes

### G-001: Planning And Tracking

Requested outcome:

- Create a full implementation plan for the Maintenance Wizard problem statement.
- Decide whether the plan should be tracked as a Goal.
- Create markdown files for continuity and progress tracking.
- Keep progress updated at the end of each session.
- Add rules and hooks guidance for branch/PR workflow and verification.

Delivered:

- `docs/implementation-plan.md`
- `docs/progress.md`
- `docs/rules.md`
- `docs/hooks.md`
- `AGENTS.md` progress-tracking guidance

Status: `Complete`

### G-014: Local Kubernetes Deployment Script

Requested outcome:

- Create a new goal for local Kubernetes deployment.
- Add a local deployment script that creates and cleans up a local Kubernetes cluster.
- Deploy all project components from that script.

Delivered:

- Kind-based local Kubernetes cluster lifecycle.
- Automatic Kind installation when missing, using Homebrew first and Go as a fallback.
- Local Docker image build/load for backend and frontend, with a direct Kind node containerd import fallback when `kind load docker-image` fails on third-party image metadata.
- NATS JetStream, FastAPI backend, and frontend Kubernetes deployments and services.
- Local host port access for frontend, backend, NATS, and NATS monitor.
- Status command with authenticated streaming-status check.
- Configurable backend CORS origins so the Kubernetes frontend NodePort can call the backend NodePort.
- Backend/frontend rollout restart after manifest apply so reruns pick up rebuilt stable `:local-k8s` image tags.
- Stop command that deletes the Kind cluster and generated runtime files.

Verification recorded:

- `bash -n scripts/run-local-k8s.sh`
- `scripts/run-local-k8s.sh --help`
- `KIND_AUTO_INSTALL=false scripts/run-local-k8s.sh status` correctly reported missing local `kind` dependency without trying to install it.
- `scripts/run-local-k8s.sh start` installed Kind through Homebrew, created the local Kind cluster, built/loaded images, applied manifests, and rolled out NATS, backend, and frontend.
- `scripts/run-local-k8s.sh status` showed backend/frontend/NATS pods running, backend health OK, streaming status connected, frontend OK, and NATS monitor OK.
- Browser verification loaded `http://127.0.0.1:18081/` and signed in as the seeded demo admin.
- `git diff --check`

Status: `Complete`

### G-002: Initial Working Prototype

Requested outcome:

- Build a practical decision-support system for steel manufacturing maintenance engineers.
- Support diagnosis, root causes, degradation/RUL prediction, abnormality detection, risk assessment, prioritization, structured reports, and natural-language interaction.

Delivered:

- FastAPI backend with health, ingestion, dashboard, equipment, alert, anomaly, chat, diagnosis, prediction, feedback, and report endpoints.
- React/Vite frontend with dashboard, priority assets, asset details, engineer query, recommendation panel, feedback controls, and report export.
- SQLite persistence seeded from `assets/sample_data/steel_plant_demo.json`.
- Document ingestion and local retrieval over persisted chunks.
- Provider-agnostic LLM adapters for mock, OpenAI-compatible, and Ollama providers.
- Rolling-baseline anomaly detection and heuristic RUL/risk scoring.
- Markdown report export.
- Backend and frontend tests.

Verification recorded:

- Backend compile checks passed.
- Backend tests grew from 5 to 21 passing tests during the initial prototype.
- Frontend tests and build passed.
- Live API and browser workflow were verified.

Status: `Complete`

### G-003: GitHub Repository And Branch Guardrails

Requested outcome:

- Create a new private GitHub repo.
- Protect `main`.
- Push necessary project files.
- Prevent direct pushes to `main`; use branches and PRs.

Delivered:

- Created private repo: `ragavendran-r/ai-powered-maintenance-wizard`.
- Pushed initial bootstrap commit `1eac0cc` to create `main`.
- Added `.githooks/pre-push`.
- Added `docs/hooks.md` instructions for `git config core.hooksPath .githooks`.
- Opened and merged PR #1 for hook/guardrail docs.

Caveat:

- GitHub rejected branch protection and repository rulesets for this private repo on the current plan, requiring GitHub Pro or a public repo.

Status: `Complete With Caveat`

### G-004: Architecture Diagram

Requested outcome:

- Update the architecture markdown file with an appropriate diagram.

Delivered:

- Added a Mermaid system diagram to `docs/architecture.md`.
- Diagram covers React frontend, FastAPI APIs, ingestion, parser, retrieval, anomaly/risk services, LLM adapter/fallback, recommendation service, reports, feedback, repository layer, SQLite, and sample seeding.
- Opened and merged PR #2.

Status: `Complete`

### G-005: Feature Coverage Review

Requested outcome:

- Re-review the application against requested decision-support features.
- Verify faster diagnosis, root causes, degradation/RUL, abnormality detection, risk prioritization, reports, reactive troubleshooting, and proactive planning.

Delivered:

- Confirmed the feature coverage through code inspection and tests.
- Identified evaluator-facing UI gap: some recommendation fields were API/report-only before G-007.
- Recorded findings in progress docs.
- Opened and merged PR #3.

Verification recorded:

- `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`
- `.venv/bin/pytest`
- `npm run test`
- `npm run build`
- FastAPI smoke check for diagnosis, prediction, anomalies, and Markdown reports.

Status: `Complete`

### G-006: Ingestion, LLM, And Continuous-Improvement Review

Requested outcome:

- Identify ingestion modes.
- Identify where LLMs are involved.
- Determine how continuous improvement is enabled.

Delivered findings:

- Ingestion modes existed through startup fixture seeding, structured record API, JSON document API, and multipart document upload API.
- LLMs were involved in recommendation generation for diagnose/chat/report flows.
- Continuous improvement was only partially enabled before G-007: historical maintenance events were used, and feedback was stored, but feedback was not yet reused.

Status: `Complete`

### G-007: Missing Feature Implementation

Requested outcome:

- Create a new Goal and implement missing features from the audits.

Delivered:

- Frontend ingestion panel for document file upload and JSON document/record imports.
- Expanded recommendation panel with root causes, urgency, RUL, confidence, immediate actions, planned actions, spares strategy, learning notes, evidence, and report export.
- Detailed engineer feedback form for actual root cause, action taken, outcome, and notes.
- Equipment-linked feedback storage through `feedback.equipment_id`.
- Feedback reuse in:
  - recommendation root-cause ranking,
  - recommendation actions,
  - LLM prompt context,
  - Markdown reports,
  - prediction drivers.
- SQLite schema metadata updated to version `2` with a lightweight `feedback.equipment_id` migration.
- Opened and merged PR #4.

Verification recorded:

- `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`
- `.venv/bin/pytest` passed with 23 tests.
- `npm run test` passed with 5 tests.
- `npm run build` passed.
- Live browser DOM verification passed for API-connected UI, diagnosis details, JSON ingestion, and detailed feedback fields.
- Browser screenshot capture timed out twice; no screenshot artifact was saved.

Status: `Complete`

### G-008: Goal Tracker

Requested outcome:

- Track all goals from the beginning in a separate goal tracker markdown file.

Delivered in this branch:

- Created `docs/goal-tracker.md`.
- Consolidated formal project goals and major session objectives from the start of the project through PR #4.

Status: `Complete`

### G-009: README And Architecture Refresh

Requested outcome:

- Review and update the README and architecture markdown files.

Delivered in this branch:

- Updated `README.md` to describe the current app as a working prototype rather than a scaffold.
- Added clearer decision-support features, important docs, ingestion examples, structured record ingestion details, SQLite schema version, LLM boundaries, and learning-loop behavior.
- Updated `docs/architecture.md` with a more complete diagram, API surface, data flow, LLM boundaries, continuous-improvement behavior, and corrected prototype limits.

Status: `Complete`

### G-010: Separate Ingestion View

Requested outcome:

- Move the complete ingestion section to a separate new view accessible from the left navigation.

Delivered in this branch:

- Added left navigation with `Dashboard` and `Ingestion` views.
- Removed the ingestion form from the dashboard asset detail panel.
- Added a dedicated Ingestion view containing the existing document file upload and JSON document/record import workflows.
- Kept target equipment context visible in the ingestion view.
- Updated frontend tests to require navigation before ingestion controls are available.
- Opened PR #8 from `feat/ingestion-view` to `main`: `https://github.com/ragavendran-r/ai-powered-maintenance-wizard/pull/8`.
- Verified with `npm run test`, `npm run build`, `git diff --check`, and browser DOM checks at `http://127.0.0.1:5173/`.

Status: `Complete`

### G-011: Add Hydraulic System And Overhead Crane Assets

Requested outcome:

- Add two more equipment assets to tracking and maintenance: one Hydraulic System and one Overhead Crane.
- Add necessary changes across the application to support these assets.

Delivered in this branch:

- Added `HYD-SYS-04` Hot Rolling Hydraulic System and `OH-CRANE-05` Melt Shop Overhead Crane to the seeded steel plant fixture.
- Added active alert context, anomaly-driving sensor readings, spare constraints, maintenance history, SOP/manual documents, and retrieval chunks for both assets.
- Updated the dashboard summary to return all tracked assets sorted by risk priority so the left navigation can expose the full five-asset set.
- Updated frontend fallback dashboard data so offline/sample mode also lists all five assets.
- Added backend tests covering seeded counts, dashboard visibility, health, prediction, diagnosis, and retrieval evidence for the new assets.
- Updated README, architecture, and demo documentation to describe the five-asset demo set.
- Opened PR #9 from `feat/add-equipment-assets` to `main`: `https://github.com/ragavendran-r/ai-powered-maintenance-wizard/pull/9`.

Verification recorded:

- `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`
- `.venv/bin/pytest` passed with 25 tests.
- `npm run test` passed with 5 tests.
- `npm run build` passed.
- `python -m app.manage reset-db` reported 5 equipment records, 5 alerts, 39 sensor readings, 7 spares, 4 maintenance events, and 8 documents/chunks.
- Live dashboard check returned 5 tracked assets and 5 priority-list entries.
- Live diagnosis checks for `HYD-SYS-04` and `OH-CRANE-05` returned critical risk with asset-specific SOP/manual/history evidence.

Status: `Complete`

### G-012: NATS JetStream IoT Streaming Ingestion

Requested outcome:

- Enable async streaming messages from steel-plant IoT applications as an ingestion source.
- Use an appropriate production-ready broker; NATS JetStream is selected for the first implementation.
- First fix visibility of the two newly added assets in the UI.

Delivered:

- Document the NATS JetStream ingestion goal and architecture.
- Make the left-nav priority asset list explicitly show all five tracked assets.
- Added a backend streaming ingestion worker using a durable NATS JetStream pull consumer.
- Added deterministic message envelope validation, derived IDs for sensor/alert messages, existing-equipment checks, SQLite persistence through structured ingestion paths, idempotency audit records, retry/nak behavior, and dead-letter publishing for invalid messages.
- Added `GET /api/streaming/status` and a read-only IoT Stream status panel in the frontend Ingestion view.
- Added backend/frontend tests and live verification.
- Opened PR #11 from `feat/nats-iot-streaming-ingestion` to `main`: `https://github.com/ragavendran-r/ai-powered-maintenance-wizard/pull/11`.

Verification recorded:

- `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`
- `.venv/bin/pytest` passed with 31 tests.
- `npm run test` passed with 5 tests.
- `npm run build` passed.
- Live `GET /api/streaming/status` returned disabled NATS status with stream `MW_IOT`.
- Live dashboard check returned 5 tracked assets and 5 priority-list entries.
- Live Vite source check confirmed the `IoT Stream` status panel and `Priority Assets` UI are being served.

Status: `Complete`

### G-013: User Login And Role-Based Access Control

Requested outcome:

- Create a new goal and plan for user login.
- Support different steel-plant users with role-specific access.
- Implement authentication and authorization after documenting the plan.
- Update documentation to GitHub, then proceed with implementation through the branch and PR workflow.

Delivered:

- Local SQLite-backed users with bcrypt password hashes.
- JWT bearer-token login and current-user session endpoint.
- Role guards across FastAPI endpoints.
- React login, session restoration, logout, role-aware navigation and actions, authenticated report export, and admin user management.
- Demo user seed data for admin, maintenance engineer, reliability engineer, planner, operator, and API-only IoT service roles.
- Backend and frontend tests covering `401`, `403`, role access, user management, and UI role gating.

Verification recorded:

- `PYTHONPYCACHEPREFIX=.pycache .venv/bin/python -m compileall app`
- `.venv/bin/pytest` passed with 37 tests.
- `npm run test` passed with 7 tests.
- `npm run build` passed.
- `git diff --check` passed.

Status: `Complete`

### G-015: LLM/SLM Leverage For Analytics And Retrieval

Requested outcome:

- Implement LLM/SLM leverage across predictive analytics, anomaly detection, knowledge retrieval, feedback learning, and explanations.
- Keep deterministic scoring and fallback behavior intact.

Delivered:

- Generic structured LLM/SLM adapter support for Pydantic-validated response contracts.
- Document intelligence extraction for ingested documents, persisted in schema version 5.
- Normalized maintenance labels from maintenance history and engineer feedback.
- LLM/SLM retrieval reranking with evidence relevance reasons.
- Anomaly context classification and recommended inspection steps.
- Prediction and recommendation reasoning explanations.
- Prediction drivers that include normalized labels with bounded risk influence.
- Frontend display of ingestion intelligence counts, anomaly context, reasoning explanations, and relevance reasons.
- README, architecture, progress, backend tests, and frontend tests updated.

Verification recorded:

- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`
- `cd backend && .venv/bin/pytest` passed with 40 tests.
- `cd frontend && npm run test` passed with 8 tests.
- `cd frontend && npm run build` passed.

Status: `Complete`

## Maintenance Rules For This File

- Add a new goal entry whenever the user asks to create or pursue a new multi-step goal.
- Update the status when a goal is completed, blocked, or superseded.
- Link the goal to PRs, commits, docs, tests, or verification evidence.
- Keep this file concise; put detailed command logs in `docs/progress.md`.
- At the end of each session, update both this file when goal state changes and `docs/progress.md` for session-level details.
