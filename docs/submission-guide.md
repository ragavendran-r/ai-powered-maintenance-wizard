# Hackathon Submission Guide

## Required Deliverables

- Source code: include `backend/`, `frontend/`, `assets/`, `docs/`, root config files, and this guide.
- Architecture explanation: use `docs/architecture.md`.
- Setup and run instructions: use `README.md`.
- Model and reasoning pipeline: describe retrieval, anomaly scoring, LLM adapters, fallback, and report generation.
- Sample input/output demonstration: use bundled sample data and the demo flow below.
- Screen recording: follow `docs/demo_script.md`.

## Packaging

From the parent directory of this repository:

```bash
zip -r ai-powered-maintenance-wizard.zip ai-powered-maintenance-wizard \
  -x "*/node_modules/*" \
  -x "*/.venv/*" \
  -x "*/dist/*" \
  -x "*/.pytest_cache/*" \
  -x "*/.pycache/*" \
  -x "*/backend/data/*.db" \
  -x "*/.env"
```

## Final Verification Commands

```bash
cd backend
source .venv/bin/activate
pytest
python -m app.manage db-status
```

```bash
cd frontend
npm run test
npm run build
```

## Demo Checklist

1. Start backend and frontend.
2. Show dashboard health, alerts, sensor anomalies, and spares.
3. Run diagnosis for `RM-DRIVE-01`.
4. Show cited SOP/manual/history evidence.
5. Export the Markdown maintenance report.
6. Upload a manual/SOP file through `POST /api/ingest/document-file`.
7. Submit feedback on a recommendation.
