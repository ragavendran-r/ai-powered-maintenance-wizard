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

- Before committing, confirm the current branch is not `main` or `master`.
- If on `main` or `master`, create or switch to a feature branch before committing.
- Do not push directly to `main` or `master`.
- Push the feature branch and open a pull request targeting `main`.

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

Before backend changes:

- Inspect whether the change affects API routes, Pydantic schemas, SQLite schema, repository methods, retrieval, or frontend API types.
- If SQLite schema changes, update `backend/app/data/database.py`, tests, `docs/architecture.md`, and reset/status guidance.

After backend changes:

```bash
PYTHONPYCACHEPREFIX=.pycache python3 -m compileall backend/app
cd backend && .venv/bin/pytest
```

Before frontend changes:

- Inspect `frontend/src/services/api.ts` for API type impact.
- Check whether the workflow needs UI test coverage in `frontend/src/App.test.tsx`.

After frontend changes:

```bash
cd frontend && npm run test && npm run build
```

After docs or progress changes:

- Re-read touched docs for stale paths, commands, links, and status language.
- Ensure `docs/progress.md` records completed work, checks run, and next steps.

Before demo or handoff:

```bash
cd backend && .venv/bin/python -m app.manage db-status
curl http://127.0.0.1:8000/api/health
```

Before final completion claims:

- Verify backend tests, frontend tests, frontend build, live API health, and browser UI flow.
- Confirm `docs/completion-audit.md` still matches the implemented behavior.
- Confirm remaining items are optional production extensions rather than blockers for the working prototype.
