# Repository Guidelines

## Project Structure & Module Organization

This repository is an implemented FastAPI + React prototype. Keep changes aligned with the existing layout:

- `backend/` for the FastAPI application, service modules, SQLite repository, and backend tests.
- `frontend/` for the React, TypeScript, and Vite application.
- `assets/` for static files such as images, fixtures, prompts, or sample data.
- `docs/` for design notes, architecture decisions, setup guides, and user-facing documentation.
- `scripts/` for local stack, Kubernetes, and notification helpers.
- Root configuration files such as `.env.example`, `README.md`, or CI workflows.

Prefer small modules named by responsibility, such as `maintenance_wizard.py`, `api_client.ts`, or `work_order_parser.test.ts`.

## Build, Test, and Development Commands

Use the existing backend and frontend commands:

- `cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`: install backend dependencies.
- `cd backend && source .venv/bin/activate && uvicorn app.main:app --reload`: run the backend at `http://localhost:8000`.
- `cd frontend && npm install`: install frontend dependencies.
- `cd frontend && npm run dev`: run the frontend at `http://localhost:5173`.
- `scripts/run-local-stack.sh start`: run the local full stack with NATS, backend, and frontend when dependencies are already installed.
- `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`: compile-check backend code.
- `cd backend && .venv/bin/pytest`: run backend tests.
- `cd frontend && npm run test && npm run build`: run frontend tests and build.

Avoid duplicate command paths. If a Makefile is added later, keep targets thin wrappers around underlying tools.

## Coding Style & Naming Conventions

Follow the formatter and linter configured by the stack. Until tooling exists, use these defaults:

- Use 2 spaces for JavaScript/TypeScript, JSON, YAML, and Markdown.
- Use 4 spaces for Python.
- Use `snake_case` for Python files and functions.
- Use `camelCase` for JavaScript/TypeScript variables and functions.
- Use `PascalCase` for classes, React components, and exported types.

Keep functions focused and avoid broad utility modules.

## Local LLM Configuration

The backend supports mock, OpenAI-compatible, and Ollama providers. Keep deterministic fallback behavior working for all LLM changes.

Recommended local setup for this Mac is LM Studio with Qwen2.5 7B Instruct GGUF:

- Use `LLM_PROVIDER=openai` for LM Studio because LM Studio exposes OpenAI-compatible endpoints.
- Set `OPENAI_BASE_URL=http://localhost:1234/v1`.
- Set `OPENAI_API_KEY` to a non-secret local placeholder such as `lm-studio-local`.
- Set `OPENAI_MODEL` to the exact model identifier shown by LM Studio, or load the model with a stable identifier such as `qwen2.5-7b-instruct`.
- Keep `.env` untracked; update `.env.example` and docs instead of committing local runtime values.
- See `docs/local-llm-lm-studio.md` for the full setup and smoke-test flow.

## Testing Guidelines

Add tests with new behavior. Place tests under `tests/` or beside source files using the chosen convention. Use behavior-focused names, for example `test_rejects_missing_asset_id` or `work-order-parser.test.ts`.

Cover parsing, validation, API boundaries, and error handling first. Add regression tests when practical.

## Commit & Pull Request Guidelines

Git history is not available in this workspace, so no existing convention can be inferred. Use concise, imperative commit messages, for example `Add work order parser` or `Fix retry handling`.

Pull requests should include:

- A short summary of the change.
- Tests run, with exact commands.
- Linked issues or task IDs when available.
- Screenshots or logs for UI or workflow changes.
- Notes about configuration, migrations, or follow-up work.

## Security & Configuration Tips

Do not commit secrets, local credentials, or generated private data. Provide `.env.example` for required configuration and document each variable. Keep large generated artifacts out of version control unless they are fixtures.

## Progress Tracking

Keep `docs/progress.md` updated at the end of each implementation session. Record completed work, tests or checks run, next steps, blockers, and any new decisions so future sessions can resume without rediscovery.

## Project Rules And Hooks

Follow `docs/rules.md` for durable engineering and product rules. Follow `docs/hooks.md` for branch, pull request, verification, notification, and demo handoff guardrails. In particular, do not commit or push directly to `main`; use a feature branch and raise a pull request targeting `main`. Send desktop and mobile notifications whenever a requested task is complete; if either notification channel is unavailable, not configured, or fails, mention that in the final response.

## Latest Session Progress

- Created private GitHub repository `ragavendran-r/ai-powered-maintenance-wizard` and pushed initial commit `1eac0cc` to `main`.
- GitHub rejected private-repository branch protection and repository rulesets on the current plan, returning an upgrade requirement.
- Added a versioned local pre-push hook on branch `chore/github-guardrails`; enable it with `git config core.hooksPath .githooks`.
- Updated `docs/architecture.md` with a Mermaid system architecture diagram.
- Reviewed problem-statement feature coverage against the implemented app; backend compile, backend tests, frontend tests, frontend build, and API smoke checks passed. Coverage is complete for the hackathon prototype, with prediction and anomaly detection still heuristic/demo-grade.
- Reviewed ingestion modes, LLM involvement, and continuous-improvement support. Current ingestion is API/file/startup-seed based; LLM is used in recommendation generation paths; feedback is persisted but not yet fed back into ranking, prompts, or prediction models.
- Implemented the missing-feature pass on branch `feat/learning-ingestion-ui`: frontend ingestion controls, full recommendation detail visibility, detailed engineer feedback capture, and feedback reuse in future recommendations and prediction drivers. Tests/build passed; browser DOM verification passed; screenshot capture timed out.
- Added `docs/goal-tracker.md` as the standalone goal ledger after merging PR #4, preserving the branch/PR workflow.
- Refreshed `README.md` and `docs/architecture.md` after merging PR #5 so user-facing and system architecture docs match the current ingestion, LLM, feedback-learning, and schema behavior.
- Added a durable completion-notification rule requiring desktop and mobile notifications at the end of every completed task.
- Moved the complete ingestion section into a dedicated left-nav Ingestion view after merging PR #7, verified the frontend build/tests and browser DOM behavior, and opened PR #8 from `feat/ingestion-view` to `main`.
- Added two tracked sample assets, `HYD-SYS-04` Hot Rolling Hydraulic System and `OH-CRANE-05` Melt Shop Overhead Crane, with alerts, sensor readings, spares, maintenance history, SOP/manual evidence, dashboard visibility, tests, docs, and PR #9.
- Merged PR #10 for streaming-goal docs and asset visibility, then implemented optional NATS JetStream IoT streaming ingestion with `/api/streaming/status`, frontend IoT Stream status, schema version 3 audit records, tests, docs, and PR #11.
- Live-tested PR #11 with Docker NATS JetStream and `nats-py`; fixed `ack_wait` compatibility, verified valid sensor/alert ingestion, verified invalid-message DLQ handling, and documented the local smoke-test flow.
- Added `scripts/run-local-stack.sh` as the common local runner for Docker NATS JetStream, streaming-enabled FastAPI, and Vite, plus README/progress documentation and PR #12.
- Added quick sample NATS alert publish steps to `docs/iot-streaming-ingestion-plan.md` for testing the running IoT ingestion flow.
- Implemented G-013 user login and role-based access control on `feat/auth-rbac`: local SQLite users, bcrypt hashes, JWT auth, endpoint role guards, React login/session handling, role-gated UI, admin user management, authenticated report downloads, schema version 4 docs, passing backend/frontend verification, and an auth-aware local stack status check.
- Added a steel-plant favicon SVG linked from the frontend HTML entrypoint so the browser tab shows a plant-themed icon.
- Repositioned dashboard controls so `Diagnose` appears above `Engineer Query` and recommendation details render at the bottom of the middle asset detail pane, with frontend regression coverage.
- Created G-014 and added a Kind-based local Kubernetes deployment script for disposable cluster creation, all-component deployment, status checks, and cleanup.
- Completed G-014 with a verification caveat: script syntax/help and diff checks passed, but full live Kind cluster deployment is pending until `kind` is installed locally.
- Updated the local Kubernetes runner so it can install Kind automatically when missing, with `KIND_AUTO_INSTALL=false` available for fail-fast environments.
- Added a direct Kind node containerd image-import fallback in `scripts/run-local-k8s.sh` after `kind load docker-image nats:2` failed during local Kubernetes deployment.
- Added configurable backend `CORS_ALLOW_ORIGINS` and configured the local Kubernetes deployment to allow its frontend NodePort origin.
- Updated the local Kubernetes runner to restart backend/frontend deployments after applying manifests so stable local image tags are refreshed on reruns.
- Updated the diagnosis/query layout so the `Diagnose` button and Engineer Query send button share the detail-pane centerline, with a three-row query textarea.
- Fixed the Users administration view so status-action buttons are no longer black and password reset happens in a dedicated overlay dialog opened from Reset.
- Fixed `scripts/run-local-stack.sh stop` to stop configured backend/frontend port listeners and the named NATS container even when `.local-stack` PID marker files are missing.
