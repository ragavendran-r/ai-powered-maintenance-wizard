# ML Workspace

The ML Workspace is a standalone demo screen for comparing the current app's deterministic maintenance predictions with a read-only shadow ML scoring layer.

It does not replace or change the existing Reliability route, RCA workflow, alert generation, work orders, preventive-maintenance plans, or existing prediction endpoints.

## What It Compares

The screen compares two outputs for the selected asset:

- Current app baseline: the existing deterministic heuristic logic already used by the app.
- Shadow ML output: a local ML-style scoring layer used only inside the ML Workspace.

The baseline is not an LLM numeric prediction. Current app numeric outputs come from deterministic backend logic:

- anomaly baseline: rolling baseline, z-score, thresholds, and trend delta
- failure/RUL baseline: weighted heuristic scoring from alerts, anomalies, asset criticality, spares, maintenance history, feedback, and labels
- existing endpoint: `POST /api/predict`

LLMs remain useful elsewhere for explanation, diagnosis prose, RCA/PM drafts, assistant guidance, summarization, and learning review. They do not own the numeric comparison shown in the ML Workspace.

## What The Shadow ML Layer Does

The shadow ML layer is intentionally local and read-only. It uses existing SQLite plant records and does not require a production model server.

It computes:

- anomaly score, ML risk band, confidence, inspection category, and drift from the current heuristic risk band
- failure probability, RUL, 7/30/90-day failure horizons, confidence interval, evaluation metadata, and drift from the current heuristic prediction
- predictive-maintenance recommendations ranked from ML risk, RUL, anomaly severity, spare blockers, history, and feedback

The implementation is demo-grade model-style inference, not a production-trained model deployment.

## UI Layout

The page is organized as:

1. Asset selector and refresh control
2. Summary comparison:
   - Current app baseline
   - Shadow ML output
   - Difference between the two
3. Model provenance cards:
   - anomaly model
   - failure/RUL model
   - predictive-maintenance ranker
4. Anomaly comparison table:
   - signal
   - current heuristic baseline
   - shadow ML output
   - interpretation of the difference
5. Failure and RUL panel:
   - 7-day, 30-day, and 90-day failure horizons
   - confidence interval
   - evaluation summary
   - model drivers
6. Predictive-maintenance recommendations
7. Comparison notes explaining shadow-mode behavior

The anomaly section uses a table so each signal is compared row-by-row instead of stacking unrelated cards.

## API

The ML Workspace calls only this endpoint:

```text
GET /api/ml/compare/{equipment_id}
```

The endpoint is read-only and role-gated for:

- `admin`
- `maintenance_engineer`
- `reliability_engineer`

The endpoint returns:

- selected equipment identity
- model metadata
- anomaly comparisons
- failure/RUL comparison
- predictive-maintenance recommendations
- comparison notes

## Isolation Guarantees

The ML Workspace does not modify:

- `GET /api/equipment/{equipment_id}/anomalies`
- `POST /api/predict`
- `GET /api/assets/{equipment_id}/reliability/stream`
- RCA routes
- diagnosis routes
- PM plan routes
- work-order routes
- dashboard risk scoring
- alert generation

The output is shadow comparison only. It is not persisted as the source of truth and does not trigger operational actions.

## Demo Talking Points

- Current app baseline is deterministic and already trusted by existing workflows.
- Shadow ML shows what a model-driven decision layer could produce without disrupting live features.
- Drift highlights where ML and heuristic logic agree or disagree.
- RAG and PEFT can still support explanations and domain language, but ML should own numeric anomaly, failure, RUL, and PM-ranking scores in a future production design.
