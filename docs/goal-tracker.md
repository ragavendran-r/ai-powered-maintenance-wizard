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
- Latest completed formal Goal: implement missing feature coverage for frontend ingestion, recommendation visibility, and feedback reuse.
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

## Maintenance Rules For This File

- Add a new goal entry whenever the user asks to create or pursue a new multi-step goal.
- Update the status when a goal is completed, blocked, or superseded.
- Link the goal to PRs, commits, docs, tests, or verification evidence.
- Keep this file concise; put detailed command logs in `docs/progress.md`.
- At the end of each session, update both this file when goal state changes and `docs/progress.md` for session-level details.
