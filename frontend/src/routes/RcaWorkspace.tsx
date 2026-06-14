import {
  CheckCircle2,
  GitBranch,
  ListChecks,
  Network,
  SearchCheck,
  Sparkles,
} from 'lucide-react'
import type { RcaCase, WorkOrder } from '../services/api'
import { formatDate, metricValue } from '../appModel'
import { workOrderStatusLabel } from '../workOrderStatus'

export function RcaWorkspace({
  closeRcaCase,
  createRcaCase,
  draftRcaCase,
  rcaCases,
  rcaLoading,
  rcaMessage,
  selectedRcaCaseId,
  selectedWorkOrderId,
  setSelectedRcaCaseId,
  setSelectedWorkOrderId,
  workOrders,
}: {
  closeRcaCase: (caseId: string) => void
  createRcaCase: () => void
  draftRcaCase: (caseId?: string) => void
  rcaCases: RcaCase[]
  rcaLoading: boolean
  rcaMessage: string
  selectedRcaCaseId: string
  selectedWorkOrderId: string
  setSelectedRcaCaseId: (caseId: string) => void
  setSelectedWorkOrderId: (workOrderId: string) => void
  workOrders: WorkOrder[]
}) {
  const selectedCase = rcaCases.find((item) => item.id === selectedRcaCaseId) ?? rcaCases[0]
  const selectedWorkOrder = workOrders.find((item) => item.id === selectedWorkOrderId) ?? workOrders[0]
  const selectedCaseWorkOrder = selectedCase
    ? workOrders.find((item) => item.id === selectedCase.work_order_id)
    : selectedWorkOrder
  const fishboneEntries: [string, string[]][] = selectedCase ? Object.entries(selectedCase.fishbone) : []
  const visibleFishboneEntries: [string, string[]][] = fishboneEntries.length
    ? fishboneEntries
    : [['Pending', ['Run Morpheus draft to populate fishbone causes.']]]

  return (
    <section className="rcaWorkspace" aria-label="RCA workspace">
      <div className="sectionHeader">
        <SearchCheck size={18} />
        <h2>RCA Workspace</h2>
      </div>
      <div className="rcaToolbar">
        <label className="field compactField">
          <span>RCA case</span>
          <select value={selectedCase?.id ?? ''} onChange={(event) => setSelectedRcaCaseId(event.target.value)}>
            {rcaCases.length === 0 && <option value="">No RCA cases</option>}
            {rcaCases.map((item) => (
              <option value={item.id} key={item.id}>
                {item.id} · {item.title}
              </option>
            ))}
          </select>
        </label>
        <label className="field compactField">
          <span>Work order context</span>
          <select value={selectedWorkOrder?.id ?? ''} onChange={(event) => setSelectedWorkOrderId(event.target.value)}>
            {workOrders.map((item) => (
              <option value={item.id} key={item.id}>
                {item.id} · {item.title}
              </option>
            ))}
          </select>
        </label>
        <button className="outlineButton" onClick={createRcaCase} disabled={rcaLoading || !selectedWorkOrder}>
          <GitBranch size={16} />
          New RCA
        </button>
        <button className="textButton" onClick={() => draftRcaCase(selectedCase?.id)} disabled={rcaLoading || (!selectedCase && !selectedWorkOrder)}>
          {rcaLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
          Morpheus draft
        </button>
        <button className="outlineButton" onClick={() => selectedCase && closeRcaCase(selectedCase.id)} disabled={rcaLoading || !selectedCase || selectedCase.status === 'closed'}>
          <CheckCircle2 size={16} />
          Close and learn
        </button>
      </div>
      {rcaMessage && <p className="inlineStatus">{rcaMessage}</p>}
      {selectedCase ? (
        <div className="rcaCaseGrid">
          <article className="dataPanel rcaCaseSummary">
            <div className="rcaCaseTitle">
              <div>
                <strong>{selectedCase.title}</strong>
                <span>{selectedCase.id} · {selectedCase.equipment_id}{selectedCase.work_order_id ? ` · ${selectedCase.work_order_id}` : ''}</span>
              </div>
              <div className="rcaBadges">
                <span className={`statusPill ${selectedCase.status === 'closed' ? 'success' : 'warning'}`}>
                  {selectedCase.status.replace(/_/g, ' ')}
                </span>
                <span className={`riskPill ${selectedCase.severity}`}>{selectedCase.severity}</span>
              </div>
            </div>
            <p>{selectedCase.problem_statement}</p>
            <div className="rcaFacts">
              <span>
                <small>Probable cause</small>
                <strong>{selectedCase.probable_cause ?? 'Awaiting Morpheus draft'}</strong>
              </span>
              <span>
                <small>Confidence</small>
                <strong>{metricValue(selectedCase.confidence * 100)}%</strong>
              </span>
              <span>
                <small>Provider</small>
                <strong>{selectedCase.used_live_provider ? `Live ${selectedCase.provider}` : selectedCase.provider}</strong>
              </span>
              <span>
                <small>Updated</small>
                <strong>{formatDate(selectedCase.updated_at)}</strong>
              </span>
            </div>
            {selectedCaseWorkOrder && (
              <div className="rcaLinkedWorkOrder">
                <span>{selectedCaseWorkOrder.id}</span>
                <strong>{selectedCaseWorkOrder.title}</strong>
                <small>{workOrderStatusLabel(selectedCaseWorkOrder.status)} · Priority {selectedCaseWorkOrder.priority}</small>
              </div>
            )}
            {selectedCase.morpheus_summary && <p className="rcaSummary">{selectedCase.morpheus_summary}</p>}
          </article>
          <article className="dataPanel">
            <div className="miniHeader">
              <ListChecks size={16} />
              <h3>Symptoms and Missing Checks</h3>
            </div>
            <div className="twoColumnList">
              <div>
                <strong>Symptoms</strong>
                <ul>
                  {selectedCase.symptoms.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
              <div>
                <strong>Missing checks</strong>
                <ul>
                  {(selectedCase.missing_checks.length ? selectedCase.missing_checks : ['No missing checks recorded']).map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
          </article>
          <article className="dataPanel">
            <div className="miniHeader">
              <Sparkles size={16} />
              <h3>Hypotheses</h3>
            </div>
            <div className="hypothesisList">
              {selectedCase.hypotheses.map((item) => (
                <div className="hypothesisItem" key={item.id}>
                  <span>{item.id}</span>
                  <strong>{item.cause}</strong>
                  <small>{metricValue(item.confidence * 100)}% confidence · {item.status}</small>
                  {item.evidence.length > 0 && <p>{item.evidence.join(' · ')}</p>}
                </div>
              ))}
              {selectedCase.hypotheses.length === 0 && <p className="emptyState">Run Morpheus draft to generate evidence-backed hypotheses.</p>}
            </div>
          </article>
          <article className="dataPanel">
            <div className="miniHeader">
              <GitBranch size={16} />
              <h3>5-Why</h3>
            </div>
            <ol className="whyChain">
              {(selectedCase.why_chain.length ? selectedCase.why_chain : ['Morpheus has not drafted a why chain yet.']).map((item) => <li key={item}>{item}</li>)}
            </ol>
          </article>
          <article className="dataPanel">
            <div className="miniHeader">
              <Network size={16} />
              <h3>Fishbone</h3>
            </div>
            <div className="fishboneGrid">
              {visibleFishboneEntries.map(([category, items]) => (
                <div className="fishboneCategory" key={category}>
                  <strong>{category}</strong>
                  <span>{items.join(' · ')}</span>
                </div>
              ))}
            </div>
          </article>
          <article className="dataPanel">
            <div className="miniHeader">
              <CheckCircle2 size={16} />
              <h3>Corrective Actions</h3>
            </div>
            <div className="actionList">
              {(selectedCase.corrective_actions.length ? selectedCase.corrective_actions : []).map((item) => (
                <div className="actionItem" key={item.id}>
                  <span className={`statusPill ${item.status === 'complete' ? 'success' : 'neutral'}`}>{item.status.replace(/_/g, ' ')}</span>
                  <strong>{item.action}</strong>
                  <small>{item.owner}{item.due_date ? ` · ${formatDate(item.due_date)}` : ''}</small>
                  {item.verification && <p>{item.verification}</p>}
                </div>
              ))}
              {selectedCase.corrective_actions.length === 0 && <p className="emptyState">Corrective actions will appear after Morpheus draft or manual RCA update.</p>}
            </div>
          </article>
          <article className="dataPanel rcaEvidencePanel">
            <div className="miniHeader">
              <SearchCheck size={16} />
              <h3>Evidence Timeline</h3>
            </div>
            <div className="timelineList">
              {selectedCase.evidence_timeline.map((item) => (
                <div className="timelineItem" key={item.id}>
                  <span>{formatDate(item.timestamp)}</span>
                  <strong>{item.title}</strong>
                  <p>{item.summary}</p>
                  <small>{item.source_type} · {item.source_id} · {item.relevance}</small>
                </div>
              ))}
            </div>
          </article>
        </div>
      ) : (
        <p className="emptyState">Create an RCA case from a work order to begin structured root-cause review.</p>
      )}
    </section>
  )
}
