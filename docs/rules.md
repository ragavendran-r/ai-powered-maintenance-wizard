# Project Rules

Use this file for durable product and engineering rules. Use `docs/hooks.md` for operational checks to run before or after work.

## Source Control

- Do not commit secrets, `.env`, local credentials, generated private data, virtual environments, dependency folders, build output, or local SQLite databases.
- Do not push directly to `main`.
- Work intended for `main` must be committed on a feature branch and raised as a pull request targeting `main`.
- Generated SQLite databases are runtime artifacts, not source artifacts.
- Pull request descriptions must not include verification steps, test commands, screenshots, logs, local file paths, or local image paths.

## Verification

- Spawn independent agents in parallel whenever the tool is available and the work can be split safely. Keep the main thread responsible for integrating, testing, documenting, and resolving conflicts from agent output.
- Backend changes require:
  - `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`
  - `cd backend && .venv/bin/pytest`
- Frontend changes require:
  - `cd frontend && npm run test`
  - `cd frontend && npm run build`
- UI layout, streaming, navigation, role visibility, or interaction changes require Playwright validation against the running local app:
  - `cd frontend && npm run test:e2e`
  - Prefer a focused Playwright spec for the changed workflow; keep screenshots, traces, and video as local failure artifacts rather than tracked files.
  - Run Playwright E2E outside the sandbox/elevated host context by default because sandboxed Chromium launch is blocked on this macOS environment.
- Documentation-only changes require a link/path sanity check for touched docs.
- Update `docs/progress.md` at the end of each implementation session with completed work, checks run, next steps, blockers, and decisions.
- Send desktop and mobile notifications when a requested task is complete.
- Whenever a task is completed, include a short pending-task update for the active goal with estimated time to complete the remaining work.

## Completion Notifications

- At the end of every completed task, send local desktop and mobile notifications before the final response when the host environment supports them.
- Prefer the repository helper:
  ```bash
  scripts/notify-complete.sh "Maintenance Wizard" "Task complete."
  ```
- For mobile notification delivery, set `MOBILE_NTFY_TOPIC` to an ntfy topic subscribed from the user's phone. Optionally set `MOBILE_NTFY_URL` for a self-hosted ntfy server.
- On macOS, desktop-only fallback is:
  ```bash
  osascript -e 'display notification "Task complete." with title "Maintenance Wizard"'
  ```
- If desktop or mobile notification fails or is unavailable, mention that in the final response.
- In the same completion response, include the active goal's remaining in-progress/pending tasks and practical ETA ranges.

## Product Behavior

- Treat the application as production-targeted, not prototype-only. Prefer robust backend design, clear UX, strong UI validation, and proven open-source infrastructure when those choices improve reliability, operability, or maintainability.
- Recommendations should include evidence/citations when available.
- The deterministic fallback path must keep working without LLM credentials.
- Uploaded documents must be parsed into SQLite documents and retrieval chunks.
- Feedback must be persisted so recommendation outcomes can support future learning.
- Training/tuning data must pass both gates before export or prompt reuse as high-confidence learning context: an LLM-as-a-Judge score at or above the configured threshold and explicit approval from an authorized reviewer.
- LLM-as-a-Judge output is advisory quality scoring, not an authorization mechanism. Role checks, schema validation, human approval, and deterministic workflow rules remain authoritative.
- Production continuous learning must follow the RAG + PEFT + NATS design: use RAG for immediate approved knowledge reuse, PEFT/LoRA adapters only from immutable approved datasets, and NATS JetStream for judge, dataset, evaluation, and tuning jobs that are too slow or risky for the web request path.
- Async learning is the production default. Local tests may force deterministic fallbacks, but product code and stack scripts should assume NATS-backed learning jobs are enabled and observable.
- Production RAG must use a real vector database. Qdrant is the default open-source vector DB for this project; SQLite/local-vector scoring is only a fallback for tests, disconnected development, or emergency degradation.
- Use LLMs/SLMs wherever they materially improve diagnosis, retrieval, summarization, guidance, review, or explanation quality. Keep authorization, lifecycle transitions, schema validation, and safety gates deterministic and server-side.
- Adapter promotion must require persisted model, prompt, dataset, evaluation, artifact, and reviewer-approval records, with rollback available by switching the active model version.
- Markdown report export should remain available for supervisor/demo handoff.

## UI Consistency

- Buttons must use the shared theme in `frontend/src/styles.css`: `textButton` for primary actions, `outlineButton` or `subtleButton` for secondary actions, `iconTextButton` for icon-plus-label actions, and `linkButton` only for low-emphasis navigation links.
- Do not add browser-default buttons. New button areas should inherit the shared radius, typography, icon spacing, focus state, and disabled state from the button theme.
- Keep the UI validation procedure current: when a faster or more reliable Playwright check is discovered, update `docs/hooks.md`, the relevant E2E spec, and this rule in the same implementation session.
