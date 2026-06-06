# AI-Powered Maintenance Wizard

Working prototype for an AI-powered maintenance decision-support system for steel manufacturing equipment.

The app helps maintenance engineers review plant health, diagnose equipment issues, inspect evidence, prioritize actions, ingest new maintenance context, export structured reports, and capture feedback that improves future recommendations.

## Current Capabilities

- FastAPI backend with health, dashboard, equipment health, alert, chat, diagnosis, prediction, report, and feedback endpoints.
- React + TypeScript + Vite frontend for a maintenance dashboard, left-nav ingestion view, engineer chat, recommendation panel, report export, and detailed feedback controls.
- Sample steel-plant data for a hot strip mill drive, blast furnace blower, caster cooling pump, hot rolling hydraulic system, and melt shop overhead crane.
- SQLite-backed persistence seeded from five sample assets with equipment, alerts, sensor readings, spares, maintenance events, documents, document chunks, and feedback.
- Local document chunk index with deterministic embeddings for offline retrieval-augmented answers.
- Time-series sensor readings with rolling-baseline anomaly detection and risk impact.
- Provider-agnostic LLM adapters for OpenAI and Ollama with structured JSON validation and deterministic fallback reasoning.
- Markdown maintenance report export.
- API and frontend ingestion for text/Markdown/CSV/log/JSON and embedded-text PDF documents.
- Structured JSON record ingestion for equipment, alerts, spares, sensor readings, and maintenance history.
- Engineer feedback capture with equipment-linked root cause, action, outcome, and notes reused in later recommendations and prediction drivers.
- Backend and frontend tests for core prototype behavior.

## Decision-Support Features

- Reactive troubleshooting through natural-language chat and diagnosis requests across the five tracked steel-plant assets.
- Root-cause suggestions merged from deterministic rules, retrieved evidence, prior feedback, and optional LLM output.
- Degradation and remaining useful life estimates using explainable heuristic risk drivers.
- Proactive abnormality detection through rolling baseline, z-score, threshold breach, and trend-delta analysis.
- Prioritized maintenance actions based on risk level, active alerts, equipment criticality, spares availability, lead time, maintenance history, and feedback signals.
- Structured Markdown report export with diagnosis, risk, RUL, root causes, immediate actions, planned actions, spares strategy, learning notes, evidence, and summary.
- Continuous-improvement loop through equipment-linked engineer feedback reused in future recommendation ranking, LLM prompt context, reports, and prediction drivers.

## Project Layout

```text
backend/              FastAPI application and tests
frontend/             React + Vite application
assets/sample_data/   Bundled steel-plant demo fixtures
backend/data/         Local SQLite database generated at runtime
docs/                 Architecture, planning, goal tracking, and progress docs
```

Important docs:

- `docs/architecture.md`: system architecture and data flow.
- `docs/goal-tracker.md`: durable goal ledger from project start.
- `docs/progress.md`: session-level progress notes and verification history.
- `docs/demo_script.md`: suggested demo walkthrough.
- `docs/submission-guide.md`: hackathon packaging guide.
- `docs/production-hardening.md`: production-readiness gaps and next steps.

## Backend Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Backend URL: `http://localhost:8000`

Database utilities:

```bash
python -m app.manage db-status
python -m app.manage reset-db
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Useful API checks:

```bash
curl http://localhost:8000/api/equipment/RM-DRIVE-01/anomalies
curl http://localhost:8000/api/equipment/RM-DRIVE-01/health
curl http://localhost:8000/api/reports/RM-DRIVE-01/markdown
curl -X POST http://localhost:8000/api/predict \
  -H "Content-Type: application/json" \
  -d '{"equipment_id":"RM-DRIVE-01"}'
curl -X POST http://localhost:8000/api/ingest/document-file \
  -F source_type=sop \
  -F equipment_id=RM-DRIVE-01 \
  -F title="Uploaded SOP" \
  -F file=@/path/to/manual-or-sop.pdf
```

Structured JSON ingestion examples:

```bash
curl -X POST http://localhost:8000/api/ingest/documents \
  -H "Content-Type: application/json" \
  -d '{"documents":[{"id":"DOC-NEW","source_type":"sop","equipment_id":"RM-DRIVE-01","title":"Inspection SOP","content":"Inspect coupling alignment when vibration rises."}]}'

curl -X POST http://localhost:8000/api/ingest/records \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"id":"ALT-NEW","equipment_id":"RM-DRIVE-01","timestamp":"2026-06-06T09:00:00+05:30","signal":"drive_end_vibration","value":8.3,"unit":"mm/s","threshold":7.1,"severity":"high","message":"Drive end vibration above advisory threshold"}]}'
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Frontend URL: `http://localhost:5173`

## Configuration

Copy `.env.example` to `.env` when configuring real providers.

```bash
cp .env.example .env
```

Supported LLM provider values:

- `mock`: deterministic local fallback for development.
- `openai`: OpenAI-compatible chat completions adapter using `OPENAI_API_KEY`, `OPENAI_MODEL`, and `OPENAI_BASE_URL`.
- `ollama`: Ollama chat adapter using `OLLAMA_BASE_URL` and `OLLAMA_MODEL`.

Provider responses must return structured JSON with `summary`, `probable_root_causes`, `immediate_actions`, `planned_actions`, and `confidence_adjustment`. Missing keys, malformed JSON, timeout, or network failure automatically fall back to deterministic local reasoning so the prototype remains runnable without secrets.

The backend creates and seeds `backend/data/maintenance_wizard.db` automatically on startup unless `DATABASE_PATH` is set to another SQLite file path. Documents are chunked into `document_chunks` with deterministic local embeddings for retrieval.

Document upload supports `.txt`, `.md`, `.markdown`, `.csv`, `.log`, `.json`, and `.pdf`. Parsed text is stored in SQLite and indexed into retrieval chunks.

Structured record ingestion supports `equipment`, `alerts`, `spares`, `sensor_readings`, and `maintenance_events`. Engineer feedback is stored with `equipment_id`, `status`, `corrected_diagnosis`, `actual_root_cause`, `action_taken`, `outcome`, and `notes`.

The current SQLite schema version is `2`. A lightweight startup migration adds `feedback.equipment_id` for older local databases. Full migration tooling is still a production hardening item.

## LLM And Learning Behavior

LLMs are invoked only through recommendation generation, which is used by diagnosis, chat, and report flows. They are not used for raw ingestion, anomaly detection, risk scoring, RUL calculation, or feedback storage.

When configured, the LLM prompt includes equipment context, selected alert, symptoms/query, computed risk, failure probability, RUL, retrieved evidence, and recent engineer feedback notes. The backend validates structured JSON before merging LLM suggestions into deterministic recommendations.

Engineer feedback improves future behavior without retraining. Accepted or corrected feedback can promote known root causes and confirmed actions, appear as learning notes in reports, and add prediction drivers for the relevant equipment.

## Tests

```bash
cd backend
source .venv/bin/activate
pytest
```

```bash
cd frontend
npm run test
npm run build
```

## Demo Flow

1. Start the FastAPI backend.
2. Start the Vite frontend.
3. Open the dashboard and review high-risk assets.
4. Select the hot strip mill main drive.
5. Ask why the drive is vibrating or run diagnosis.
6. Review sensor anomalies, cited evidence, root causes, immediate and planned actions, spares strategy, feedback controls, and Markdown report export.
7. Open the Ingestion view from the left navigation and import an SOP/manual/log or paste JSON records/documents.
8. Submit detailed feedback with actual root cause, action taken, and outcome; run diagnosis again to see learning notes included.

## Progress Tracking

Update `docs/progress.md` at the end of each implementation session with completed work, checks run, next steps, blockers, and decisions.

## Submission And Hardening

- Hackathon packaging guide: `docs/submission-guide.md`
- Production hardening notes: `docs/production-hardening.md`
