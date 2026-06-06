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

1. Show the dashboard summary: average health, active alerts, critical alerts, and assets tracked.
2. Select `Hot Strip Mill Main Drive Motor`.
3. Point out critical vibration and high bearing-temperature alerts.
4. Run diagnosis.
5. Explain the recommendation output: risk, urgency, immediate actions, spares strategy, and evidence.
6. Ask: `Why is the hot strip mill main drive vibrating?`
7. Show cited SOP/manual/history evidence.
8. Submit feedback using Accept, Correct, or Reject.
9. Briefly show `docs/architecture.md` and explain the provider-agnostic LLM adapter and planned vector retrieval path.
