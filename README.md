# AI-Powered Maintenance Wizard

Working prototype scaffold for an AI-powered maintenance decision-support system for steel manufacturing equipment.

The current slice includes:

- FastAPI backend with health, dashboard, equipment health, alert, chat, diagnosis, prediction, report, and feedback endpoints.
- React + TypeScript + Vite frontend for a maintenance dashboard, engineer chat, recommendation panel, and feedback controls.
- Sample steel-plant data for a hot strip mill drive, blast furnace blower, and caster cooling pump.
- SQLite-backed persistence seeded from sample data for equipment, alerts, spares, maintenance events, documents, and feedback.
- Local document chunk index with deterministic embeddings for offline retrieval-augmented answers.
- Time-series sensor readings with rolling-baseline anomaly detection and risk impact.
- Provider-agnostic LLM adapters for OpenAI and Ollama with structured JSON validation and deterministic fallback reasoning.
- Markdown maintenance report export.
- File upload ingestion for text/Markdown/CSV/log/JSON and PDF documents.
- Frontend ingestion panel for document uploads and JSON document/record imports.
- Engineer feedback capture with equipment-linked root cause, action, outcome, and notes reused in later recommendations and prediction drivers.
- Backend and frontend tests for core prototype behavior.

## Project Layout

```text
backend/              FastAPI application and tests
frontend/             React + Vite application
assets/sample_data/   Bundled steel-plant demo fixtures
backend/data/         Local SQLite database generated at runtime
docs/                 Implementation plan and progress tracking
```

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
curl -X POST http://localhost:8000/api/ingest/document-file \
  -F source_type=sop \
  -F equipment_id=RM-DRIVE-01 \
  -F title="Uploaded SOP" \
  -F file=@/path/to/manual-or-sop.pdf
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
7. Import an SOP/manual/log through the ingestion panel or paste JSON records/documents.
8. Submit detailed feedback with actual root cause, action taken, and outcome; run diagnosis again to see learning notes included.

## Progress Tracking

Update `docs/progress.md` at the end of each implementation session with completed work, checks run, next steps, blockers, and decisions.

## Submission And Hardening

- Hackathon packaging guide: `docs/submission-guide.md`
- Production hardening notes: `docs/production-hardening.md`
