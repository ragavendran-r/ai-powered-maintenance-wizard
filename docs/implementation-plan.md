# Maintenance Wizard Implementation Plan (Historical)

This document is the original implementation plan and remains useful for understanding how the project was scoped. It is not the canonical current API or feature inventory. For current behavior, use `README.md`, `docs/architecture.md`, `docs/setup-and-running.md`, and `docs/completion-audit.md`.

## Summary

Build a working AI-powered maintenance decision-support prototype for industrial equipment in steel manufacturing environments.

The implemented system uses:

- Backend: Python FastAPI
- Frontend: React, TypeScript, and Vite
- Storage: SQLite for local/demo operational records, auth state, work orders, learning records, and lightweight startup migrations
- Retrieval: Qdrant-backed RAG for document chunks and approved learning examples, with deterministic SQLite/local-vector fallback
- Streaming and jobs: NATS JetStream for IoT ingestion and async learning jobs
- AI: provider-agnostic LLM adapter supporting OpenAI-compatible chat completions and Ollama-style local models
- Learning: LLM-as-a-Judge scoring, reviewer approval gates, JSONL snapshots, PEFT worker hooks, and model promotion controls
- Auth: local SQLite users, bcrypt password hashes, JWT bearer tokens, role guards, and role-aware React navigation
- Demo data: sample steel-plant equipment, sensor alerts, maintenance history, spares, SOPs, and manual excerpts

The implemented prototype now supports ingestion, retrieval-augmented maintenance chat, diagnosis, root-cause analysis, preventive-maintenance planning, work execution, anomaly and risk scoring, prioritized recommendations, engineer feedback, dashboard views, structured report generation, and reviewer-controlled continuous-learning workflows. Later iterations added local RBAC, NATS-backed IoT and learning jobs, Qdrant-backed RAG, RCA/PM workflows, Learning Review, PEFT handoff, artifact controls, and model promotion gates.

## Key Changes

- Create a predictable project structure:
  - `backend/` for FastAPI services, schemas, database access, tests, and sample loaders.
  - `frontend/` for the React dashboard, chat, equipment detail views, and report UI.
  - `assets/sample_data/` for steel-plant demo fixtures.
  - `docs/` for architecture, setup, data flow, demo script, assumptions, and progress tracking.
  - Root `.env.example`, `README.md`, and stack helper scripts.

- Original backend API targets:
  - `POST /api/auth/login`
  - `GET /api/auth/me`
  - `POST /api/ingest/documents`
  - `POST /api/ingest/document-file`
  - `POST /api/ingest/records`
  - `GET /api/streaming/status`
  - `GET /api/assets`
  - `GET /api/assets/{equipment_id}`
  - `GET /api/equipment`
  - `GET /api/equipment/{id}/health`
  - `GET /api/alerts`
  - `GET /api/work-orders`
  - `POST /api/work-orders`
  - `GET /api/pm-templates`
  - `GET /api/pm-plans`
  - `POST /api/pm-plans/morpheus-draft`
  - `POST /api/chat`
  - `POST /api/diagnose`
  - `POST /api/predict`
  - `GET /api/rca-cases`
  - `POST /api/recommendations/{id}/feedback`
  - `GET /api/reports/maintenance-insights`
  - `GET /api/reports/{equipment_id}`
  - `GET /api/learning/summary`
  - `GET /api/dashboard/summary`

- Implement core backend capabilities:
  - Ingest equipment manuals, SOPs, logs, alerts, failure reports, spare parts, and maintenance records into SQLite-backed repositories.
  - Normalize data into typed models for equipment, alerts, work orders, sensor summaries, spare parts, maintenance events, document chunks, recommendations, and feedback.
  - Chunk and embed knowledge documents into Qdrant-backed retrieval, retaining SQLite-local fallback for disconnected tests.
  - Retrieve relevant evidence for each maintenance question or alert.
  - Generate structured outputs containing diagnosis, probable root causes, risk level, urgency, evidence, immediate actions, long-term actions, spares impact, confidence, and report summary.
  - Detect abnormalities using threshold rules and simple statistical methods such as rolling z-score, EWMA, or IsolationForest where sample data supports it.
  - Estimate failure likelihood and basic remaining useful life using historical events, alert severity, condition indicators, and confidence bands.
  - Capture engineer feedback and include it in future retrieval and recommendation context.
  - Gate learning reuse through LLM-as-a-Judge scoring and explicit reviewer approval.

- Implement frontend capabilities:
  - Dashboard with equipment health, active alerts, risk levels, bottlenecks, spares constraints, and trend charts.
  - Equipment detail page with timeline, anomaly history, predicted risk/RUL, linked evidence, and recommended actions.
  - Role-aware Neo, Morpheus, and Smith assistant surfaces with streamed readable responses and cited context.
  - Recommendation panel with immediate actions, planned actions, spares strategy, and feedback controls.
  - Report view for abnormal alert reports, structured maintenance summaries, decision summaries, digital maintenance log entries, and Markdown export.
  - Learning Review view for examples, datasets, RAG status, PEFT jobs, artifacts, evaluations, deployments, and model promotions.

## Data And Reasoning Flow

1. User uploads or uses bundled sample data.
2. Backend parses structured inputs into SQLite and documents into chunked vector storage.
3. Dashboard summarizes equipment health, alerts, risks, bottlenecks, and spare constraints.
4. Engineer asks a natural language question or selects an alert.
5. Backend retrieves relevant manuals, SOPs, logs, and historical records.
6. Anomaly and risk services compute numeric signals.
7. LLM reasoner combines retrieved evidence, risk signals, and operational constraints.
8. System returns structured diagnosis, root causes, risk, RUL estimate, prioritized actions, and citations.
9. Engineer feedback is saved, judged, approved when appropriate, and reused in future recommendation, RAG, reporting, prediction, and tuning context.

## LLM And Retrieval Design

- Define a common `LLMClient` interface for chat completion and structured JSON output.
- Implement `OpenAIClient` and `OllamaClient` with structured JSON validation and deterministic fallback.
- Select provider through `.env` with `LLM_PROVIDER=openai` or `LLM_PROVIDER=ollama`.
- Use the same OpenAI-compatible path for LM Studio, vLLM, hosted gateways, and compatible local runtimes.
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

- This is a production-targeted local prototype, not a production deployment.
- Synthetic/sample steel manufacturing data will be used unless real plant data is provided.
- SQLite is sufficient for the local prototype; production should migrate to PostgreSQL or another managed database.
- Qdrant is the default production-like vector database; local vector storage remains only a fallback.
- Failure prediction and RUL are explainable heuristics unless richer historical time-series data is provided.
- Provider-agnostic LLM support means OpenAI and Ollama-compatible clients share one internal interface.
- Authentication and role-based access are implemented locally; enterprise SSO remains a production hardening item.
