# Demo Script

## Setup

1. Start the backend:

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

## Screen Recording Flow

1. Show the dashboard summary: average health, active alerts, critical alerts, and five assets tracked.
2. Point out the priority asset list, including `Hot Rolling Hydraulic System` and `Melt Shop Overhead Crane`.
3. Select `Hot Strip Mill Main Drive Motor`.
4. Point out critical vibration and high bearing-temperature alerts.
5. Run diagnosis.
6. Explain the recommendation output: risk, urgency, immediate actions, spares strategy, and evidence.
7. Select the hydraulic system or overhead crane and show its asset-specific alerts, anomalies, spares, and SOP/manual evidence.
8. Ask: `Why is the hot strip mill main drive vibrating?`
9. Show cited SOP/manual/history evidence.
10. Submit feedback using Accept, Correct, or Reject.
11. Briefly show `docs/architecture.md` and explain the provider-agnostic LLM adapter and planned vector retrieval path.
