# Hackathon Submission Guide

## Required Deliverables

- Source code: include `backend/`, `frontend/`, `assets/`, `docs/`, root config files, and this guide.
- Architecture explanation: use `docs/architecture.md`.
- Setup and run instructions: use `README.md`.
- Model and reasoning pipeline: describe Qdrant RAG, anomaly scoring, LLM adapters, deterministic fallback, Neo/Morpheus/Smith assistants, Learning Review gates, and report generation.
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

1. Start the local full stack with `scripts/run-local-stack.sh start`, or start backend and frontend separately.
2. Sign in as `admin@plant.local` with `DemoPass123!`.
3. Show dashboard health, alerts, sensor anomalies, and spares.
4. Run diagnosis for `RM-DRIVE-01`.
5. Show cited SOP/manual/history evidence and provider/fallback labels.
6. Show Work Execution and Planning role flows for technician, supervisor, and planner users.
7. Export structured maintenance insight Markdown from Reports.
8. Upload a manual/SOP file through the Ingestion view or `POST /api/ingest/document-file`.
9. Show Learning and Tuning with Qdrant RAG status, judged examples, datasets, jobs, artifacts, PEFT hooks, and promotion gates.
10. Submit feedback on a recommendation.
