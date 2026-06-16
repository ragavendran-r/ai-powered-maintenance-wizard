import {
  CheckCircle2,
  GitBranch,
  ListChecks,
  Network,
  SearchCheck,
  Sparkles,
} from 'lucide-react'
import { useEffect, useRef } from 'react'
import { FormattedAssistantContent } from '../assistantContent'
import type { RcaCase, WorkOrder } from '../services/api'
import { formatDate, metricValue } from '../appModel'
import { workOrderStatusLabel } from '../workOrderStatus'

export function RcaWorkspace({
  closeRcaCase,
  createRcaCase,
  draftRcaCase,
  rcaCases,
  rcaDraftCaseId,
  rcaDraftStreamText,
  rcaLoading,
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
  rcaDraftCaseId: string
  rcaDraftStreamText: string
  rcaLoading: boolean
  selectedRcaCaseId: string
  selectedWorkOrderId: string
  setSelectedRcaCaseId: (caseId: string) => void
  setSelectedWorkOrderId: (workOrderId: string) => void
  workOrders: WorkOrder[]
}) {
  const selectedCase = selectedRcaCaseId ? rcaCases.find((item) => item.id === selectedRcaCaseId) : undefined
  const selectedWorkOrder = workOrders.find((item) => item.id === selectedWorkOrderId) ?? workOrders[0]
  const existingCaseForSelectedWorkOrder = selectedWorkOrder
    ? rcaCases.find((item) => item.work_order_id === selectedWorkOrder.id)
    : undefined
  const selectedCaseWorkOrder = selectedCase
    ? workOrders.find((item) => item.id === selectedCase.work_order_id)
    : selectedWorkOrder
  const selectedWorkOrderCaseIsActive = Boolean(existingCaseForSelectedWorkOrder && selectedCase?.id === existingCaseForSelectedWorkOrder.id)
  const workOrderCaseActionLabel = selectedWorkOrderCaseIsActive
    ? 'RCA case selected'
    : existingCaseForSelectedWorkOrder
    ? 'Use existing RCA for work order'
    : 'Create RCA for work order'
  const fishboneEntries: [string, string[]][] = selectedCase ? Object.entries(selectedCase.fishbone) : []
  const visibleFishboneEntries: [string, string[]][] = fishboneEntries.length
    ? fishboneEntries
    : [['Pending', ['Run Morpheus draft to populate fishbone causes.']]]
  const liveFishboneText = selectedCase?.id === rcaDraftCaseId
    ? extractMarkdownSection(rcaDraftStreamText, 'Fishbone')
    : ''
  const morpheusFishboneText = liveFishboneText || selectedCase?.morpheus_fishbone_text || ''
  const streamEndRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!rcaDraftStreamText) return
    streamEndRef.current?.scrollIntoView({ block: 'end' })
  }, [rcaDraftStreamText])

  useEffect(() => {
    if (!selectedCase?.work_order_id || selectedWorkOrderId === selectedCase.work_order_id) return
    if (!workOrders.some((item) => item.id === selectedCase.work_order_id)) return
    setSelectedWorkOrderId(selectedCase.work_order_id)
  }, [selectedCase?.work_order_id, selectedWorkOrderId, setSelectedWorkOrderId, workOrders])

  function selectRcaCase(caseId: string) {
    setSelectedRcaCaseId(caseId)
    const nextCase = rcaCases.find((item) => item.id === caseId)
    if (nextCase?.work_order_id) {
      setSelectedWorkOrderId(nextCase.work_order_id)
    }
  }

  function selectWorkOrder(workOrderId: string) {
    setSelectedWorkOrderId(workOrderId)
    const linkedCase = rcaCases.find((item) => item.work_order_id === workOrderId)
    setSelectedRcaCaseId(linkedCase?.id ?? '')
  }

  function useOrCreateRcaForSelectedWorkOrder() {
    if (existingCaseForSelectedWorkOrder) {
      setSelectedRcaCaseId(existingCaseForSelectedWorkOrder.id)
      return
    }
    createRcaCase()
  }

  return (
    <section className="rcaWorkspace" aria-label="RCA workspace">
      <div className="sectionHeader">
        <SearchCheck size={18} />
        <h2>RCA Workspace</h2>
      </div>
      <div className="rcaToolbar" aria-label="RCA workflow controls">
        <section className="rcaControlGroup">
          <div className="miniHeader">
            <span className="stepBadge">1</span>
            <h3>Work order context</h3>
          </div>
          <label className="field compactField">
            <span>Work order</span>
            <select value={selectedWorkOrder?.id ?? ''} onChange={(event) => selectWorkOrder(event.target.value)}>
              {workOrders.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.id} · {item.title}
                </option>
              ))}
            </select>
          </label>
          <p className="rcaControlHint">RCA starts from the selected work order. Keep one active RCA per work order; capture multiple causes as hypotheses inside the case.</p>
        </section>
        <section className="rcaControlGroup">
          <div className="miniHeader">
            <span className="stepBadge">2</span>
            <h3>RCA case</h3>
          </div>
          <label className="field compactField">
            <span>Selected RCA case</span>
            <select value={selectedCase?.id ?? ''} onChange={(event) => selectRcaCase(event.target.value)}>
              <option value="">No selected RCA case</option>
              {rcaCases.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.id} · {item.title}
                </option>
              ))}
            </select>
          </label>
          <button
            className="outlineButton rcaWideButton"
            onClick={useOrCreateRcaForSelectedWorkOrder}
            disabled={rcaLoading || !selectedWorkOrder || selectedWorkOrderCaseIsActive}
          >
            <GitBranch size={16} />
            {workOrderCaseActionLabel}
          </button>
        </section>
        <section className="rcaControlGroup rcaActionGroup">
          <div className="miniHeader">
            <span className="stepBadge">3</span>
            <h3>Review actions</h3>
          </div>
          <button className="textButton rcaWideButton" onClick={() => selectedCase && draftRcaCase(selectedCase.id)} disabled={rcaLoading || !selectedCase}>
            {rcaLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
            Morpheus draft selected RCA
          </button>
          <button className="outlineButton rcaWideButton" onClick={() => selectedCase && closeRcaCase(selectedCase.id)} disabled={rcaLoading || !selectedCase || selectedCase.status === 'closed'}>
            <CheckCircle2 size={16} />
            Close selected RCA and learn
          </button>
        </section>
      </div>
      {(rcaLoading || rcaDraftStreamText) && (
        <article className="dataPanel rcaDraftStream" aria-label="Morpheus RCA draft stream">
          <div className="miniHeader">
            <Sparkles size={16} />
            <h3>Morpheus live draft</h3>
          </div>
          <div className="rcaDraftStreamViewport">
            {rcaDraftStreamText
              ? <FormattedAssistantContent content={rcaDraftStreamText} />
              : <p className="emptyState">Morpheus is opening the RCA draft stream...</p>}
            <div ref={streamEndRef} aria-hidden="true" />
          </div>
        </article>
      )}
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
              {morpheusFishboneText ? (
                <div className="fishboneCategory morpheusFishboneCategory">
                  <FormattedAssistantContent content={morpheusFishboneText} />
                </div>
              ) : (
                visibleFishboneEntries.map(([category, items]) => (
                  <div className="fishboneCategory" key={category}>
                    <strong>{category}</strong>
                    <span>{items.join(' · ')}</span>
                  </div>
                ))
              )}
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

function extractMarkdownSection(content: string, heading: string) {
  const marker = heading.toLowerCase()
  const lines = content.split(/\r?\n/)
  const collected: string[] = []
  let collecting = false
  for (const line of lines) {
    const stripped = line.trim()
    const normalized = stripped.replace(/^#+\s*/, '').replace(/:$/, '').trim().toLowerCase()
    if (normalized === marker) {
      collecting = true
      continue
    }
    if (collecting && stripped.startsWith('#')) {
      break
    }
    if (collecting) {
      collected.push(line)
    }
  }
  return collected.join('\n').trim()
}
