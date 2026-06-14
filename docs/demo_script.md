# Demo Script

## Setup

1. Start the local full stack:

   ```bash
   scripts/run-local-stack.sh start
   ```

   This starts NATS JetStream, Qdrant, the streaming-enabled FastAPI backend, the learning worker, and the Vite frontend.

   If you only need the app without the full stack, start the backend:

   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --reload
   ```

2. Start the frontend:

   ```bash
   cd frontend
   npm run dev
   ```

3. Open `http://localhost:5173`.
4. Sign in as `admin@plant.local` with `DemoPass123!`.

## Screen Recording Flow

1. Show the dashboard summary: average health, active alerts, critical alerts, and five assets tracked.
2. Point out role-aware navigation and the signed-in admin user.
3. Point out the priority asset list, including `Hot Rolling Hydraulic System` and `Melt Shop Overhead Crane`.
4. Select `Hot Strip Mill Main Drive Motor`.
5. Point out critical vibration and high bearing-temperature alerts.
6. Run diagnosis and explain the recommendation output: risk, urgency, immediate actions, spares strategy, learning notes, and evidence.
7. Open the Reliability tab for the selected asset and show Smith's streamed prediction narrative, model metadata, confidence interval, evidence, and degradation trend.
8. Select the hydraulic system or overhead crane and show its asset-specific alerts, anomalies, spares, and SOP/manual evidence.
9. Ask Neo: `Why is the hot strip mill main drive vibrating?`
10. Show cited SOP/manual/history evidence and the provider label.
11. Open Work Execution as `technician@plant.local` or `supervisor@plant.local` to show role-specific Neo assistance and material-blocker guidance.
12. Open Planning as `planner@plant.local` to show PM planning, scheduling, dispatch validation, and material readiness.
13. Open Reports as admin, refresh plant reports, refresh selected-asset reports, and export Markdown.
14. Open Ingestion and upload one file from `assets/ingestion_samples/`.
15. Open Learning and Tuning to show Qdrant RAG status, judged examples, datasets, jobs, artifacts, PEFT hooks, evaluations, deployments, and promotion gates.
16. Open Users as admin to show local RBAC administration.
17. Submit feedback using Accept, Correct, or Reject.
18. Briefly show `docs/architecture.md` and explain the provider-agnostic LLM adapter, Qdrant RAG, NATS-backed ingestion/jobs, deterministic safety gates, and reviewer-controlled learning loop.
