import { useEffect, useMemo, useState } from 'react'
import { Activity, BrainCircuit, RefreshCw, Wrench } from 'lucide-react'

import {
  api,
  type AssetListItem,
  type MlComparisonResponse,
  type PredictionModelVersion,
} from '../services/api'

function pct(value: number) {
  return `${Math.round(value * 100)}%`
}

function signedPct(value: number) {
  const rounded = Math.round(value * 100)
  return `${rounded >= 0 ? '+' : ''}${rounded}%`
}

function signedDays(value: number) {
  return `${value >= 0 ? '+' : ''}${value} days`
}

function ModelBadge({ model }: { model: PredictionModelVersion }) {
  return (
    <div className="mlModelBadge">
      <strong>{model.name} {model.version}</strong>
      <span>{model.status} · {model.algorithm}</span>
    </div>
  )
}

export function MlWorkspaceRoute({
  assets,
  selectedEquipment,
  setSelectedEquipment,
}: {
  assets: AssetListItem[]
  selectedEquipment: string
  setSelectedEquipment: (equipmentId: string) => void
}) {
  const [comparison, setComparison] = useState<MlComparisonResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [refreshCount, setRefreshCount] = useState(0)
  const selectedAsset = useMemo(
    () => assets.find((asset) => asset.id === selectedEquipment),
    [assets, selectedEquipment],
  )

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setMessage('')
    api.mlComparison(selectedEquipment)
      .then((result) => {
        if (!cancelled) setComparison(result)
      })
      .catch(() => {
        if (!cancelled) {
          setMessage('ML comparison could not be loaded.')
          setComparison(null)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [refreshCount, selectedEquipment])

  const failure = comparison?.failure_prediction
  const modelEvaluation = failure?.model_evaluation

  return (
    <section className="mlWorkspace" aria-label="ML Workspace">
      <div className="sectionHeader">
        <BrainCircuit size={24} />
        <div>
          <p className="eyebrow">Shadow ML Comparison</p>
          <h2>ML Workspace</h2>
          <small>Baseline is the current app heuristic output, not an LLM numeric prediction. LLMs remain explanation and guidance tools elsewhere.</small>
        </div>
      </div>

      <div className="mlWorkspaceToolbar">
        <label className="field compactField">
          <span>Asset</span>
          <select value={selectedEquipment} onChange={(event) => setSelectedEquipment(event.target.value)} disabled={loading}>
            {assets.map((asset) => (
              <option key={asset.id} value={asset.id}>
                {asset.id} - {asset.name}
              </option>
            ))}
          </select>
        </label>
        <button className="outlineButton" type="button" onClick={() => setRefreshCount((value) => value + 1)} disabled={loading}>
          {loading ? <span className="loadingSpinner" aria-hidden="true" /> : <RefreshCw size={16} />}
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {message && <p className="inlineStatus errorText">{message}</p>}
      {loading && !comparison && (
        <section className="mlLoadingPanel" aria-live="polite" aria-busy="true">
          <span className="loadingSpinner" aria-hidden="true" />
          <strong>Loading ML predictions</strong>
          <small>{selectedAsset?.name ?? selectedEquipment}</small>
        </section>
      )}

      {comparison && failure && (
        <>
          <div className="mlSummaryGrid" aria-label="ML comparison summary">
            <article className="dataPanel mlSummaryCard">
              <span className="chip">Current app baseline</span>
              <div>
                <span className={`riskBadge ${failure.heuristic_prediction.risk_level}`}>{failure.heuristic_prediction.risk_level}</span>
                <strong>{pct(failure.heuristic_prediction.failure_probability)} failure probability</strong>
                <small>{failure.heuristic_prediction.remaining_useful_life_days} days RUL from existing deterministic `/api/predict` heuristic, not LLM output</small>
              </div>
            </article>
            <article className="dataPanel mlSummaryCard">
              <span className="chip">Shadow ML output</span>
              <div>
                <span className={`riskBadge ${failure.ml_risk_level}`}>{failure.ml_risk_level}</span>
                <strong>{pct(failure.ml_failure_probability)} failure probability</strong>
                <small>{failure.ml_remaining_useful_life_days} days RUL from local ML-style scoring</small>
              </div>
            </article>
            <article className="dataPanel mlSummaryCard">
              <span className="chip">Difference</span>
              <div>
                <strong>{signedPct(failure.probability_drift)} probability drift</strong>
                <small>{signedDays(failure.rul_drift_days)} RUL drift between baseline and ML shadow output</small>
              </div>
            </article>
          </div>

          <div className="mlModelGrid" aria-label="ML model provenance">
            <ModelBadge model={comparison.anomaly_model} />
            <ModelBadge model={comparison.failure_model} />
            <ModelBadge model={comparison.maintenance_model} />
          </div>

          <section className="mlWorkspaceStack">
            <article className="dataPanel mlWidePanel">
              <div className="sectionHeader compactHeader">
                <Activity size={18} />
                <h3>Anomaly comparison</h3>
              </div>
              {comparison.anomalies.length ? (
                <div className="mlComparisonTableWrap">
                  <table className="mlComparisonTable" aria-label="Anomaly heuristic and ML comparison">
                    <thead>
                      <tr>
                        <th>Signal</th>
                        <th>Current heuristic baseline</th>
                        <th>Shadow ML output</th>
                        <th>How to read the comparison</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.anomalies.map((item) => (
                        <tr key={`${item.heuristic.signal}-${item.heuristic.timestamp}`}>
                          <td>
                            <strong>{item.heuristic.signal.replace(/_/g, ' ')}</strong>
                            <small>{item.heuristic.value}{item.heuristic.unit} · z-score {item.heuristic.z_score}</small>
                          </td>
                          <td>
                            <span className={`riskBadge ${item.heuristic.risk_level}`}>{item.heuristic.risk_level}</span>
                            <small>Existing rolling baseline, z-score, threshold, and trend rule.</small>
                          </td>
                          <td>
                            <span className={`riskBadge ${item.ml_risk_level}`}>{item.ml_risk_level}</span>
                            <small>Score {pct(item.ml_score)} · confidence {pct(item.ml_confidence)}</small>
                            <small>{item.inspection_category}</small>
                          </td>
                          <td>
                            <p>{item.decision}</p>
                            <small>{signedPct(item.drift_delta)} risk-score drift from heuristic severity band.</small>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="emptyState">No current heuristic anomalies to compare for this asset.</p>
              )}
            </article>

            <article className="dataPanel mlWidePanel mlFailurePanel">
              <div className="sectionHeader compactHeader">
                <BrainCircuit size={18} />
                <h3>Failure and RUL</h3>
              </div>
              <div className="mlHorizonGrid">
                {failure.horizons.map((horizon) => (
                  <div key={horizon.label}>
                    <span>{horizon.label}</span>
                    <strong>{pct(horizon.probability)}</strong>
                  </div>
                ))}
              </div>
              <p className="predictionAuditNote">
                Confidence interval {pct(failure.confidence_interval.lower_probability)}-{pct(failure.confidence_interval.upper_probability)}
                {' '}probability, {failure.confidence_interval.lower_rul_days}-{failure.confidence_interval.upper_rul_days} days RUL.
              </p>
              {modelEvaluation && (
                <p className="predictionAuditNote">
                  Evaluation: {pct(modelEvaluation.precision)} precision / {pct(modelEvaluation.recall)} recall;
                  {' '}RUL MAE {modelEvaluation.mean_absolute_rul_error_days} days.
                </p>
              )}
              <ul className="predictionEvidenceList">
                {failure.drivers.map((driver) => <li key={driver}>{driver}</li>)}
              </ul>
            </article>

            <article className="dataPanel mlWidePanel">
              <div className="sectionHeader compactHeader">
                <Wrench size={18} />
                <h3>Predictive maintenance recommendations</h3>
              </div>
              <div className="mlMaintenanceList">
                {comparison.maintenance_recommendations.map((item) => (
                  <div key={item.id} className="mlMaintenanceItem">
                    <div>
                      <strong>{item.title}</strong>
                      <small>{item.trigger_type.replace(/_/g, ' ')} · due in {item.recommended_due_days} day(s)</small>
                    </div>
                    <span>{pct(item.risk_reduction_score)} risk reduction</span>
                    <p>{item.rationale}</p>
                    <ul>
                      {item.evidence.map((evidence) => <li key={evidence}>{evidence}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            </article>

            <article className="dataPanel mlWidePanel">
              <h3>Comparison notes</h3>
              <ul className="predictionEvidenceList">
                {comparison.comparison_notes.map((note) => <li key={note}>{note}</li>)}
              </ul>
            </article>
          </section>
        </>
      )}
    </section>
  )
}
