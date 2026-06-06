# Project Rules

Use this file for durable product and engineering rules. Use `docs/hooks.md` for operational checks to run before or after work.

## Source Control

- Do not commit secrets, `.env`, local credentials, generated private data, virtual environments, dependency folders, build output, or local SQLite databases.
- Do not push directly to `main`.
- Work intended for `main` must be committed on a feature branch and raised as a pull request targeting `main`.
- Generated SQLite databases are runtime artifacts, not source artifacts.

## Verification

- Backend changes require:
  - `PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app`
  - `cd backend && .venv/bin/pytest`
- Frontend changes require:
  - `cd frontend && npm run test`
  - `cd frontend && npm run build`
- Documentation-only changes require a link/path sanity check for touched docs.
- Update `docs/progress.md` at the end of each implementation session with completed work, checks run, next steps, blockers, and decisions.
- Send a desktop notification when a requested task is complete.

## Completion Notifications

- At the end of every completed task, send a local desktop notification before the final response when the host environment supports it.
- On macOS, use:
  ```bash
  osascript -e 'display notification "Task complete." with title "Maintenance Wizard"'
  ```
- If desktop notification fails or is unavailable, mention that in the final response.

## Product Behavior

- Recommendations should include evidence/citations when available.
- The deterministic fallback path must keep working without LLM credentials.
- Uploaded documents must be parsed into SQLite documents and retrieval chunks.
- Feedback must be persisted so recommendation outcomes can support future learning.
- Markdown report export should remain available for supervisor/demo handoff.
