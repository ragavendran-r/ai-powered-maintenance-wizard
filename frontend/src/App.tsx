import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Database,
  Download,
  FileJson,
  Gauge,
  MessageSquare,
  Send,
  ShieldAlert,
  Upload,
  Wrench,
} from 'lucide-react'
import { api, fallbackDashboard, type DashboardSummary, type Recommendation } from './services/api'

const riskRank = { low: 1, medium: 2, high: 3, critical: 4 }
type AppView = 'dashboard' | 'ingestion'

export function App() {
  const [dashboard, setDashboard] = useState<DashboardSummary>(fallbackDashboard)
  const [activeView, setActiveView] = useState<AppView>('dashboard')
  const [selectedEquipment, setSelectedEquipment] = useState('RM-DRIVE-01')
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [question, setQuestion] = useState('Why is the hot strip mill main drive vibrating?')
  const [answer, setAnswer] = useState('')
  const [apiState, setApiState] = useState<'connected' | 'fallback'>('fallback')
  const [ingestSourceType, setIngestSourceType] = useState('sop')
  const [ingestTitle, setIngestTitle] = useState('')
  const [ingestFile, setIngestFile] = useState<File | null>(null)
  const [jsonMode, setJsonMode] = useState<'documents' | 'records'>('documents')
  const [jsonPayload, setJsonPayload] = useState('')
  const [ingestionMessage, setIngestionMessage] = useState('')
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const [feedbackRootCause, setFeedbackRootCause] = useState('')
  const [feedbackActionTaken, setFeedbackActionTaken] = useState('')
  const [feedbackOutcome, setFeedbackOutcome] = useState('')
  const [feedbackNotes, setFeedbackNotes] = useState('')

  function loadDashboard() {
    return api
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
  }

  useEffect(() => {
    loadDashboard()
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
    api
      .feedback(recommendation.id, status, recommendation.equipment_id, {
        actualRootCause: feedbackRootCause.trim() || undefined,
        actionTaken: feedbackActionTaken.trim() || undefined,
        outcome: feedbackOutcome.trim() || undefined,
        notes: feedbackNotes.trim() || undefined,
      })
      .then(() => setFeedbackMessage(`${status} feedback stored`))
      .catch(() => setFeedbackMessage('Feedback could not be stored'))
  }

  async function ingestSelectedFile() {
    if (!ingestFile) {
      setIngestionMessage('Select a file before upload')
      return
    }
    try {
      const result = await api.ingestDocumentFile({
        file: ingestFile,
        sourceType: ingestSourceType,
        equipmentId: selectedEquipment,
        title: ingestTitle.trim() || undefined,
      })
      setIngestionMessage(`Stored ${result.documents} document${result.documents === 1 ? '' : 's'}`)
      setIngestTitle('')
      setIngestFile(null)
      await loadDashboard()
    } catch {
      setIngestionMessage('File ingestion failed')
    }
  }

  async function ingestJsonPayload() {
    try {
      const parsed = JSON.parse(jsonPayload)
      if (jsonMode === 'documents') {
        const documents = Array.isArray(parsed) ? parsed : parsed.documents
        if (!Array.isArray(documents)) throw new Error('documents payload must be an array')
        const result = await api.ingestDocuments(documents)
        setIngestionMessage(`Stored ${result.documents} document${result.documents === 1 ? '' : 's'}`)
      } else {
        const result = await api.ingestRecords(parsed)
        const total = Object.values(result.counts).reduce((sum, count) => sum + count, 0)
        setIngestionMessage(`Stored ${total} record${total === 1 ? '' : 's'}`)
      }
      setJsonPayload('')
      await loadDashboard()
    } catch {
      setIngestionMessage('JSON ingestion failed')
    }
  }

  const ingestionView = (
    <section className="detailPanel ingestionView">
      <div className="sectionHeader">
        <Upload size={18} />
        <h2>Ingestion</h2>
      </div>
      <div className="ingestionContext">
        <span>Target asset</span>
        <strong>{selectedHealth?.equipment.name}</strong>
        <small>{selectedEquipment}</small>
      </div>
      <div className="ingestionGrid">
        <label className="field">
          <span>Source</span>
          <select value={ingestSourceType} onChange={(event) => setIngestSourceType(event.target.value)}>
            <option value="manual">Manual</option>
            <option value="sop">SOP</option>
            <option value="log">Log</option>
            <option value="alert">Alert</option>
            <option value="spares">Spares</option>
            <option value="history">History</option>
          </select>
        </label>
        <label className="field">
          <span>Title</span>
          <input value={ingestTitle} onChange={(event) => setIngestTitle(event.target.value)} />
        </label>
        <label className="field fileField">
          <span>File</span>
          <input
            aria-label="Ingestion file"
            type="file"
            accept=".txt,.md,.markdown,.csv,.log,.json,.pdf,text/*,application/pdf"
            onChange={(event) => setIngestFile(event.target.files?.[0] ?? null)}
          />
        </label>
        <button onClick={ingestSelectedFile} title="Upload maintenance document">
          <Upload size={16} />
          Upload
        </button>
      </div>
      <div className="jsonIngest">
        <label className="field">
          <span>Payload</span>
          <select value={jsonMode} onChange={(event) => setJsonMode(event.target.value as 'documents' | 'records')}>
            <option value="documents">Documents</option>
            <option value="records">Records</option>
          </select>
        </label>
        <textarea
          aria-label="Ingestion JSON"
          value={jsonPayload}
          onChange={(event) => setJsonPayload(event.target.value)}
          placeholder={jsonMode === 'documents' ? '{"documents":[...]}' : '{"alerts":[...],"sensor_readings":[...]}'}
        />
        <button className="textButton" onClick={ingestJsonPayload}>
          <FileJson size={16} />
          Import JSON
        </button>
      </div>
      {ingestionMessage && <p className="inlineStatus">{ingestionMessage}</p>}
    </section>
  )

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

      <section className={`workArea ${activeView === 'ingestion' ? 'ingestionMode' : ''}`}>
        <aside className="leftNav" aria-label="Maintenance navigation">
          <nav className="primaryNav" aria-label="Primary navigation">
            <button className={`navButton ${activeView === 'dashboard' ? 'selected' : ''}`} onClick={() => setActiveView('dashboard')}>
              <ClipboardList size={17} />
              Dashboard
            </button>
            <button className={`navButton ${activeView === 'ingestion' ? 'selected' : ''}`} onClick={() => setActiveView('ingestion')}>
              <Upload size={17} />
              Ingestion
            </button>
          </nav>
          <div className="sectionHeader compactHeader">
            <Wrench size={18} />
            <h2>Priority Assets</h2>
          </div>
          {dashboard.highest_risk_equipment.map((item) => (
            <button
              className={`assetRow ${item.equipment.id === selectedEquipment ? 'selected' : ''}`}
              key={item.equipment.id}
              onClick={() => {
                setSelectedEquipment(item.equipment.id)
                setActiveView('dashboard')
              }}
            >
              <span>
                <strong>{item.equipment.name}</strong>
                <small>{item.equipment.area}</small>
              </span>
              <span className={`riskBadge ${item.risk_level}`}>{item.risk_level}</span>
            </button>
          ))}
        </aside>

        {activeView === 'dashboard' ? (
          <>
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
                  <div className="recommendationFacts">
                    <span>
                      <small>Urgency</small>
                      <strong>{recommendation.urgency}</strong>
                    </span>
                    <span>
                      <small>RUL</small>
                      <strong>{recommendation.remaining_useful_life_days ?? 'n/a'} days</strong>
                    </span>
                    <span>
                      <small>Confidence</small>
                      <strong>{Math.round(recommendation.confidence * 100)}%</strong>
                    </span>
                  </div>
                  <h3>Probable Root Causes</h3>
                  <ul>
                    {recommendation.probable_root_causes.map((cause) => (
                      <li key={cause}>{cause}</li>
                    ))}
                  </ul>
                  <h3>Immediate Actions</h3>
                  <ul>
                    {recommendation.immediate_actions.map((action) => (
                      <li key={action}>{action}</li>
                    ))}
                  </ul>
                  <h3>Planned Actions</h3>
                  <ul>
                    {recommendation.planned_actions.map((action) => (
                      <li key={action}>{action}</li>
                    ))}
                  </ul>
                  <h3>Spares Strategy</h3>
                  <ul>
                    {recommendation.spares_strategy.map((action) => (
                      <li key={action}>{action}</li>
                    ))}
                  </ul>
                  {(recommendation.learning_notes ?? []).length > 0 && (
                    <>
                      <h3>Learning Notes</h3>
                      {recommendation.learning_notes.map((note) => (
                        <p className="learningNote" key={note}>
                          {note}
                        </p>
                      ))}
                    </>
                  )}
                  <h3>Evidence</h3>
                  {recommendation.evidence.slice(0, 3).map((evidence) => (
                    <p className="evidence" key={evidence.source_id}>
                      <strong>{evidence.title}</strong>
                      {evidence.excerpt}
                    </p>
                  ))}
                  <div className="feedbackDetails">
                    <label className="field">
                      <span>Actual Root Cause</span>
                      <input value={feedbackRootCause} onChange={(event) => setFeedbackRootCause(event.target.value)} />
                    </label>
                    <label className="field">
                      <span>Action Taken</span>
                      <input value={feedbackActionTaken} onChange={(event) => setFeedbackActionTaken(event.target.value)} />
                    </label>
                    <label className="field">
                      <span>Outcome</span>
                      <input value={feedbackOutcome} onChange={(event) => setFeedbackOutcome(event.target.value)} />
                    </label>
                    <label className="field">
                      <span>Notes</span>
                      <input value={feedbackNotes} onChange={(event) => setFeedbackNotes(event.target.value)} />
                    </label>
                  </div>
                  <div className="feedbackRow">
                    <button onClick={() => sendFeedback('accepted')}>Accept</button>
                    <button onClick={() => sendFeedback('corrected')}>Correct</button>
                    <button onClick={() => sendFeedback('rejected')}>Reject</button>
                  </div>
                  {feedbackMessage && <p className="inlineStatus">{feedbackMessage}</p>}
                  <a className="downloadReport" href={api.reportMarkdownUrl(recommendation.equipment_id)} download>
                    <Download size={16} />
                    Export Report
                  </a>
                </>
              ) : (
                <p className="emptyState">Run diagnosis or ask a question to generate cited maintenance actions.</p>
              )}
            </aside>
          </>
        ) : (
          ingestionView
        )}
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
