# Demo Script

## Setup

1. For a live adapter-backed demo, start llama.cpp first:

   ```bash
   scripts/peft/start_llama_cpp_qwen_adapter.sh --check
   scripts/peft/start_llama_cpp_qwen_adapter.sh
   ```

   This starts llama.cpp's OpenAI-compatible `llama-server` on `http://127.0.0.1:8080/v1` with the configured Qwen2.5 GGUF base model and GGUF LoRA adapter. Neo, Trinity, Morpheus, Smith, recommendations, RAG reranking, and learning judge calls use this served adapter alias when `LLM_PROVIDER=openai`.

2. Start the local full stack:

   ```bash
   scripts/run-local-stack.sh start
   ```

   This starts NATS JetStream, Qdrant, the streaming-enabled FastAPI backend, the IoT simulator, the learning worker, and the Vite frontend.

   If you only need the app without the full stack, start the backend:

   ```bash
   cd backend
   source .venv/bin/activate
   uvicorn app.main:app --reload
   ```

3. Start the frontend manually only when you are not using the full stack script:

   ```bash
   cd frontend
   npm run dev
   ```

4. Open `http://localhost:5173`.
5. Sign in as `admin@plant.local` with `DemoPass123!`.

## Screen Recording Flow

1. Show the dashboard summary: average health, active alerts, critical alerts, and five assets tracked.
2. Point out role-aware navigation and the signed-in admin user.
3. Open Monitoring and show IoT simulator readings grouped by asset, two-column full-width sensor charts, x/y axis labels, threshold lines, anomaly markers, and stale telemetry indicators.
4. Wait for or point out the centered anomaly alert dialog; simulated anomalies and unseen-alert polling both run every 2 minutes by default.
5. Point out the priority asset list, including `Hot Rolling Hydraulic System` and `Melt Shop Overhead Crane`.
6. Select `Hot Strip Mill Main Drive Motor`.
7. Point out critical vibration and high bearing-temperature alerts.
8. Run diagnosis and explain the recommendation output: risk, urgency, immediate actions, spares strategy, learning notes, and evidence.
9. Open the Reliability tab for the selected asset and show Smith's streamed prediction narrative, model metadata, confidence interval, evidence, and degradation trend.
10. Select the hydraulic system or overhead crane and show its asset-specific alerts, anomalies, spares, and SOP/manual evidence.
11. Ask Neo: `Why is the hot strip mill main drive vibrating?`
12. Show cited SOP/manual/history evidence and the provider label from the llama-server adapter runtime when live LLM mode is enabled.
13. Open Work Execution as `technician@plant.local` or `supervisor@plant.local` to show Trinity role-specific assistance and material-blocker guidance.
14. Open Planning as `planner@plant.local` to show PM planning, scheduling, dispatch validation, and material readiness.
15. Open Reports as admin, refresh plant reports, refresh selected-asset reports, and export Markdown.
16. Open Ingestion and upload one file from `assets/ingestion_samples/`.
17. Open Learning and Tuning to show Qdrant RAG status, judged examples, datasets, jobs, artifacts, PEFT hooks, evaluations, deployments, and promotion gates.
18. Open Users as admin to show local RBAC administration.
19. Submit feedback using Accept, Correct, or Reject.
20. Briefly show `docs/architecture.md` and explain the llama-server adapter runtime, Qdrant RAG, NATS-backed ingestion/jobs, deterministic safety gates, and reviewer-controlled learning loop.
