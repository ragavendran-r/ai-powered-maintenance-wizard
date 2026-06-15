# Hooks And Guardrails

These hooks are repository guardrails to follow manually or automate in Git/CI once the folder is initialized as a Git repository.

Enable versioned local Git hooks after cloning:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```

## Branch And PR Guard

Purpose: prevent direct work on `main` and require changes to reach `main` through a pull request.

Required behavior:

- Run Git operations outside the sandbox/elevated host context by default in this macOS workspace so repository locks, hooks, GitHub CLI calls, and branch operations use the real host environment.
- Before committing, confirm the current branch is not `main` or `master`.
- If on `main` or `master`, create or switch to a feature branch before committing.
- Do not push directly to `main` or `master`.
- Push the feature branch and open a pull request targeting `main`.
- After requested changes or fixes pass the relevant verification, merge the pull request when GitHub reports it mergeable unless the user explicitly asks to leave it open.
- Keep pull request descriptions concise: include summary, linked task or issue IDs if any, and configuration/migration/follow-up notes if relevant.
- Do not add verification steps, test commands, screenshots, logs, local file paths, or local image paths to pull request descriptions.

Suggested local pre-commit hook:

```bash
#!/usr/bin/env bash
set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"

if [ "$branch" = "main" ] || [ "$branch" = "master" ]; then
  echo "Direct commits on $branch are blocked. Create a feature branch and raise a PR to main."
  exit 1
fi
```

Implemented pre-push hook: `.githooks/pre-push`

Reference behavior:

```bash
#!/usr/bin/env bash
set -euo pipefail

while read -r local_ref local_sha remote_ref remote_sha; do
  if [ "$remote_ref" = "refs/heads/main" ] || [ "$remote_ref" = "refs/heads/master" ]; then
    echo "Direct pushes to main/master are blocked. Push a feature branch and open a PR."
    exit 1
  fi
done
```

## Verification Hooks

Before split-safe implementation or review work:

- Spawn independent agents in parallel whenever the tool is available. Use them for bounded audits, implementation slices, or validation passes, while keeping final integration and verification in the main thread.

Before backend changes:

- Inspect whether the change affects API routes, Pydantic schemas, SQLite schema, repository methods, retrieval, or frontend API types.
- If SQLite schema changes, update `backend/app/data/database.py`, tests, `docs/architecture.md`, and reset/status guidance.
- For small or tightly scoped backend changes, run focused backend tests that cover the touched behavior first. Use the full backend suite for broad, shared, risky, or release-level changes.

After backend changes:

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app
cd backend && .venv/bin/pytest
```

Before frontend changes:

- Inspect `frontend/src/services/api.ts` for API type impact.
- Check whether the workflow needs UI test coverage in `frontend/src/App.test.tsx`.
- For small or tightly scoped frontend changes, run focused frontend tests or specs that cover the touched behavior first. Use the full frontend suite for broad, shared, risky, or release-level changes.

After frontend changes:

```bash
cd frontend && npm run test && npm run build
```

For UI layout, streaming, navigation, role visibility, or interaction changes:

```bash
cd frontend && npm run test:e2e
```

Validation procedure:

- Use Playwright as the default UI validation tool because it supports repeatable browser flows, DOM/layout assertions, screenshots, traces, and video on failure.
- Run Playwright E2E outside the sandbox/elevated host context by default. On this macOS environment, sandboxed Chromium launch fails on Mach port permissions, so do not spend a run on the sandboxed path unless the host setup changes.
- Keep Playwright tests focused on the changed workflow; mock slow LLM streaming endpoints inside the test when validating scroll, spinner, formatting, or layout behavior.
- Prefer assertions for visible text, role-specific controls, scroll position, viewport position, and absence of horizontal overflow before relying on screenshots.
- Use screenshots/video/trace as local failure artifacts for diagnosis, not as pull request description content.
- When a faster or more reliable UI validation technique is found, update this procedure and the relevant Playwright spec before marking the task complete.

After docs or progress changes:

- Re-read touched docs for stale paths, commands, links, and status language.
- Ensure `docs/progress.md` records completed work, checks run, and next steps.

After completing any requested task:

```bash
scripts/notify-complete.sh "Maintenance Wizard" "Task complete."
```

For mobile delivery, set `MOBILE_NTFY_TOPIC` to an ntfy topic subscribed from the user's phone. If desktop or mobile notification delivery is unavailable, not configured, or fails, note that in the final response.

In the same completion update, list the active goal's remaining in-progress and pending tasks with practical ETA ranges so the user can track what is left.

Before demo or handoff:

```bash
cd backend && .venv/bin/python -m app.manage db-status
curl http://127.0.0.1:8000/api/health
```

Before final completion claims:

- Verify backend tests, frontend tests, frontend build, live API health, and browser UI flow.
- Confirm `docs/completion-audit.md` still matches the implemented behavior.
- Confirm remaining items are optional production extensions rather than blockers for the working prototype.
