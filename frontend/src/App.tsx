import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Database,
  Download,
  Gauge,
  MessageSquare,
  Send,
  ShieldAlert,
  Wrench,
} from 'lucide-react'
import { api, fallbackDashboard, type DashboardSummary, type Recommendation } from './services/api'

const riskRank = { low: 1, medium: 2, high: 3, critical: 4 }

export function App() {
  const [dashboard, setDashboard] = useState<DashboardSummary>(fallbackDashboard)
  const [selectedEquipment, setSelectedEquipment] = useState('RM-DRIVE-01')
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [question, setQuestion] = useState('Why is the hot strip mill main drive vibrating?')
  const [answer, setAnswer] = useState('')
  const [apiState, setApiState] = useState<'connected' | 'fallback'>('fallback')

  useEffect(() => {
    api
      .dashboard()
      .then((summary) => {
        setDashboard(summary)
        setApiState('connected')
        const topAsset = [...summary.highest_risk_equipment].sort(
          (a, b) => riskRank[b.risk_level] - riskRank[a.risk_level],
        )[0]
        if (topAsset) setSelectedEquipment(topAsset.equipment.id)
      })
      .catch(() => setApiState('fallback'))
  }, [])

  const selectedHealth = useMemo(
    () => dashboard.highest_risk_equipment.find((item) => item.equipment.id === selectedEquipment) ?? dashboard.highest_risk_equipment[0],
    [dashboard, selectedEquipment],
  )

  function runDiagnosis() {
    api
      .diagnose(selectedEquipment, selectedHealth?.active_alerts[0]?.id)
      .then((result) => {
        setRecommendation(result)
        setAnswer(result.report_summary)
        setApiState('connected')
      })
      .catch(() => {
        setApiState('fallback')
        setAnswer('Start the backend API to generate live diagnosis. The visible dashboard is using bundled fallback data.')
      })
  }

  function sendQuestion() {
    api
      .chat(selectedEquipment, question)
      .then((result) => {
        setRecommendation(result.recommendation)
        setAnswer(result.answer)
        setApiState('connected')
      })
      .catch(() => {
        setApiState('fallback')
        setAnswer('Backend is not reachable yet. The planned API will answer this with cited SOP, manual, alert, and maintenance history evidence.')
      })
  }

  function sendFeedback(status: 'accepted' | 'rejected' | 'corrected') {
    if (!recommendation) return
    api.feedback(recommendation.id, status).catch(() => undefined)
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <p className="eyebrow">Steel Plant Maintenance</p>
          <h1>Maintenance Wizard</h1>
        </div>
        <div className={`statusPill ${apiState}`}>
          <Database size={16} />
          {apiState === 'connected' ? 'API connected' : 'Sample view'}
        </div>
      </header>

      <section className="metricsGrid" aria-label="Plant health summary">
        <Metric icon={<Gauge />} label="Average Health" value={`${dashboard.average_health_score}%`} />
        <Metric icon={<AlertTriangle />} label="Active Alerts" value={dashboard.active_alert_count.toString()} />
        <Metric icon={<ShieldAlert />} label="Critical Alerts" value={dashboard.critical_alert_count.toString()} />
        <Metric icon={<Activity />} label="Assets Tracked" value={dashboard.equipment_count.toString()} />
      </section>

      <section className="workArea">
        <aside className="assetList" aria-label="Highest risk equipment">
          <div className="sectionHeader">
            <Wrench size={18} />
            <h2>Priority Assets</h2>
          </div>
          {dashboard.highest_risk_equipment.map((item) => (
            <button
              className={`assetRow ${item.equipment.id === selectedEquipment ? 'selected' : ''}`}
              key={item.equipment.id}
              onClick={() => setSelectedEquipment(item.equipment.id)}
            >
              <span>
                <strong>{item.equipment.name}</strong>
                <small>{item.equipment.area}</small>
              </span>
              <span className={`riskBadge ${item.risk_level}`}>{item.risk_level}</span>
            </button>
          ))}
        </aside>

        <section className="detailPanel">
          <div className="sectionHeader">
            <ClipboardList size={18} />
            <h2>{selectedHealth?.equipment.name}</h2>
          </div>
          <div className="assetFacts">
            <span>Process: {selectedHealth?.equipment.process}</span>
            <span>Health: {selectedHealth?.health_score}%</span>
            <span>Criticality: {selectedHealth?.equipment.criticality}/5</span>
          </div>

          <div className="split">
            <div>
              <h3>Active Alerts</h3>
              {selectedHealth?.active_alerts.map((alert) => (
                <div className="alertLine" key={alert.id}>
                  <span className={`riskDot ${alert.severity}`} />
                  <span>{alert.message}</span>
                  <strong>
                    {alert.value} {alert.unit}
                  </strong>
                </div>
              ))}
            </div>
            <div>
              <h3>Sensor Anomalies</h3>
              {selectedHealth?.anomalies.map((anomaly) => (
                <div className="anomalyLine" key={`${anomaly.signal}-${anomaly.timestamp}`}>
                  <span className={`riskDot ${anomaly.risk_level}`} />
                  <span>
                    <strong>{anomaly.signal.replace(/_/g, ' ')}</strong>
                    <small>
                      z {anomaly.z_score} · baseline {anomaly.baseline_mean} {anomaly.unit}
                    </small>
                  </span>
                  <strong>
                    {anomaly.value} {anomaly.unit}
                  </strong>
                </div>
              ))}
            </div>
            <div>
              <h3>Spares Constraints</h3>
              {selectedHealth?.top_spares_constraints.map((spare) => (
                <div className="spareLine" key={spare.id}>
                  <span>{spare.name}</span>
                  <strong>{spare.available_qty} stock</strong>
                  <small>{spare.lead_time_days}d lead</small>
                </div>
              ))}
            </div>
          </div>

          <div className="chatPanel">
            <div className="sectionHeader">
              <MessageSquare size={18} />
              <h2>Engineer Query</h2>
            </div>
            <div className="queryRow">
              <input value={question} onChange={(event) => setQuestion(event.target.value)} />
              <button onClick={sendQuestion} title="Ask maintenance wizard">
                <Send size={18} />
              </button>
              <button className="textButton" onClick={runDiagnosis}>
                Diagnose
              </button>
            </div>
            {answer && <p className="answer">{answer}</p>}
          </div>
        </section>

        <aside className="recommendationPanel">
          <div className="sectionHeader">
            <CheckCircle2 size={18} />
            <h2>Recommendation</h2>
          </div>
          {recommendation ? (
            <>
              <p className="diagnosis">{recommendation.diagnosis}</p>
              <span className={`riskBadge ${recommendation.risk_level}`}>{recommendation.risk_level}</span>
              <h3>Immediate Actions</h3>
              <ul>
                {recommendation.immediate_actions.map((action) => (
                  <li key={action}>{action}</li>
                ))}
              </ul>
              <h3>Evidence</h3>
              {recommendation.evidence.slice(0, 3).map((evidence) => (
                <p className="evidence" key={evidence.source_id}>
                  <strong>{evidence.title}</strong>
                  {evidence.excerpt}
                </p>
              ))}
              <div className="feedbackRow">
                <button onClick={() => sendFeedback('accepted')}>Accept</button>
                <button onClick={() => sendFeedback('corrected')}>Correct</button>
                <button onClick={() => sendFeedback('rejected')}>Reject</button>
              </div>
              <a className="downloadReport" href={api.reportMarkdownUrl(recommendation.equipment_id)} download>
                <Download size={16} />
                Export Report
              </a>
            </>
          ) : (
            <p className="emptyState">Run diagnosis or ask a question to generate cited maintenance actions.</p>
          )}
        </aside>
      </section>
    </main>
  )
}

function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      <span className="metricIcon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}
