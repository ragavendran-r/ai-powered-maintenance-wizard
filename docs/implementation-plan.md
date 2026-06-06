# Maintenance Wizard Implementation Plan

## Summary

Build a working AI-powered maintenance decision-support prototype for industrial equipment in steel manufacturing environments.

The system will use:

- Backend: Python FastAPI
- Frontend: React, TypeScript, and Vite
- Storage: SQLite for structured records and feedback
- Retrieval: local SQLite-backed chunk index for manuals, SOPs, logs, reports, and historical records
- AI: provider-agnostic LLM adapter supporting OpenAI-compatible chat completions and Ollama-style local models
- Demo data: sample steel-plant equipment, sensor alerts, maintenance history, spares, SOPs, and manual excerpts

The prototype will support ingestion, retrieval-augmented maintenance chat, diagnosis, root-cause analysis, anomaly and risk scoring, prioritized recommendations, engineer feedback, dashboard views, and structured report generation.

## Key Changes

- Create a predictable project structure:
  - `backend/` for FastAPI services, schemas, database access, tests, and sample loaders.
  - `frontend/` for the React dashboard, chat, equipment detail views, and report UI.
  - `assets/sample_data/` for steel-plant demo fixtures.
  - `docs/` for architecture, setup, data flow, demo script, assumptions, and progress tracking.
  - Root `.env.example`, `README.md`, and optional `docker-compose.yml`.

- Implement backend APIs:
  - `POST /api/ingest/documents`
  - `POST /api/ingest/records`
  - `GET /api/equipment`
  - `GET /api/equipment/{id}/health`
  - `GET /api/alerts`
  - `POST /api/chat`
  - `POST /api/diagnose`
  - `POST /api/predict`
  - `POST /api/recommendations/{id}/feedback`
  - `GET /api/reports/{equipment_id}`
  - `GET /api/dashboard/summary`

- Implement core backend capabilities:
- Ingest equipment manuals, SOPs, logs, alerts, failure reports, spare parts, and maintenance records into SQLite-backed repositories.
  - Normalize data into typed models for equipment, alerts, work orders, sensor summaries, spare parts, maintenance events, document chunks, recommendations, and feedback.
- Chunk and embed knowledge documents into a local SQLite-backed retrieval index.
  - Retrieve relevant evidence for each maintenance question or alert.
  - Generate structured outputs containing diagnosis, probable root causes, risk level, urgency, evidence, immediate actions, long-term actions, spares impact, confidence, and report summary.
  - Detect abnormalities using threshold rules and simple statistical methods such as rolling z-score, EWMA, or IsolationForest where sample data supports it.
  - Estimate failure likelihood and basic remaining useful life using historical events, alert severity, condition indicators, and confidence bands.
  - Capture engineer feedback and include it in future retrieval and recommendation context.

- Implement frontend capabilities:
  - Dashboard with equipment health, active alerts, risk levels, bottlenecks, spares constraints, and trend charts.
  - Equipment detail page with timeline, anomaly history, predicted risk/RUL, linked evidence, and recommended actions.
  - Maintenance chat page with multi-turn natural language interaction and cited answers.
  - Recommendation panel with immediate actions, planned actions, spares strategy, and feedback controls.
  - Report view for abnormal alert reports and structured maintenance summaries.

## Data And Reasoning Flow

1. User uploads or uses bundled sample data.
2. Backend parses structured inputs into SQLite and documents into chunked vector storage.
3. Dashboard summarizes equipment health, alerts, risks, bottlenecks, and spare constraints.
4. Engineer asks a natural language question or selects an alert.
5. Backend retrieves relevant manuals, SOPs, logs, and historical records.
6. Anomaly and risk services compute numeric signals.
7. LLM reasoner combines retrieved evidence, risk signals, and operational constraints.
8. System returns structured diagnosis, root causes, risk, RUL estimate, prioritized actions, and citations.
9. Engineer feedback is saved and reused in future recommendation context.

## LLM And Retrieval Design

- Define a common `LLMClient` interface for chat completion and structured JSON output.
- Implement `OpenAIClient` and `OllamaClient` with structured JSON validation and deterministic fallback.
- Select provider through `.env` with `LLM_PROVIDER=openai` or `LLM_PROVIDER=ollama`.
- Keep prompts provider-neutral and require structured JSON responses for diagnosis and recommendations.
- Include citations for recommendations wherever possible.
- When evidence is weak, return a lower confidence score and explicitly identify missing data.

## Test Plan

- Backend unit tests:
  - Record parsing and validation.
  - Document chunking and retrieval.
  - Risk classification boundaries: low, medium, high, critical.
  - Spare lead-time prioritization.
  - Feedback persistence.
  - LLM adapter mock responses and invalid JSON handling.

- Backend integration tests:
  - Ingest sample data, query diagnosis, and verify cited evidence exists.
  - Run alert-to-recommendation flow.
  - Generate a report for selected equipment.

- Frontend tests:
  - Dashboard renders sample equipment health.
  - Chat submits a query and displays cited recommendations.
  - Feedback controls call the backend.
  - Equipment detail view handles missing prediction confidence gracefully.

- Manual acceptance scenarios:
  - Diagnose a high-vibration rolling mill motor alert.
  - Explain likely root causes using SOP/manual evidence.
  - Prioritize action when spare bearing lead time is long.
  - Generate an abnormal alert report.
  - Submit engineer feedback and confirm it appears in future context.

## Assumptions

- This is a local hackathon prototype, not a production deployment.
- Synthetic/sample steel manufacturing data will be used unless real plant data is provided.
- SQLite is sufficient for the prototype; production can migrate to PostgreSQL.
- Local vector storage is sufficient for the prototype; production can migrate to Qdrant, Weaviate, or pgvector.
- Failure prediction and RUL are explainable heuristics unless richer historical time-series data is provided.
- Provider-agnostic LLM support means OpenAI and Ollama-compatible clients share one internal interface.
- Authentication and full role-based access are optional enhancements; role labels can be represented in sample data and UI without blocking the core prototype.
