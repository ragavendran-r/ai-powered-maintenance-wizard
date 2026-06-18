import { useEffect, useMemo, useRef, useState } from 'react'
import { Bot, Briefcase, CalendarClock, FileText, Send, Sparkles, Truck } from 'lucide-react'
import type {
  AssetListItem,
  AuthUser,
  MaterialBlockerStatus,
  MaterialReadiness,
  PmPlan,
  PmPlanStatus,
  PmTemplate,
  ProcurementStatus,
  SupervisorAssistantResponse,
  TechnicianAssistantResponse,
  WorkOrder,
  WorkOrderPlanningStatus,
  WorkOrderSpareReservation,
} from '../services/api'
import type { AssistantTurn } from '../assistantContent'
import { AssistantMessageContent, FormattedAssistantContent, assistantProviderLabel, usePinnedStreamScroll } from '../assistantContent'
import {
  supervisorAssistantName,
  technicianAssistantName,
} from '../appModel'
import { effectiveWorkOrderStatus, workOrderStatusDetail } from '../workOrderStatus'
import {
  StatusBadge,
  StatusTimeline,
  TechnicianExecutionCard,
  WorkOrderTable,
} from '../sharedComponents'
import { formatDate } from '../appModel'

const TECHNICIAN_WAITING_MESSAGE_DELAY_MS = 7_000
type PlanningTab = 'preventive' | 'dispatch'

export function WorkOrdersRoute({
  approveWorkOrder,
  assignWorkOrder,
  assets,
  canApproveWorkOrders,
  canAssignWorkOrders,
  canSupervisorAssistant,
  canTechnicianAssistant,
  completeSelectedWorkOrder,
  dispatchWorkOrder,
  planWorkOrder,
  pmPlanLoading,
  pmPlanStreamText,
  pmPlans,
  pmTemplates,
  convertPmPlanToWorkOrder,
  draftPreventivePlan,
  runSupervisorAssistant,
  runTechnicianAssistant,
  selectedWorkOrder,
  setSelectedWorkOrderId,
  setSupervisorQuestion,
  setTechnicianObservation,
  startWorkOrder,
  supervisorChat,
  supervisorLoading,
  supervisorQuestion,
  supervisorStreaming,
  technicianAssistant,
  technicianChat,
  technicianLoading,
  technicianObservation,
  technicianStreaming,
  technicians,
  mode,
  workOrders,
}: {
  approveWorkOrder: (workOrderId: string) => void
  assignWorkOrder: (workOrderId: string, assignedTo: string) => void
  assets: AssetListItem[]
  canApproveWorkOrders: boolean
  canAssignWorkOrders: boolean
  canSupervisorAssistant: boolean
  canTechnicianAssistant: boolean
  completeSelectedWorkOrder: () => void
  dispatchWorkOrder: (workOrderId: string) => void
  planWorkOrder: (workOrderId: string, payload: WorkOrderPlanningUpdate) => void
  pmPlanLoading: boolean
  pmPlanStreamText: string
  pmPlans: PmPlan[]
  pmTemplates: PmTemplate[]
  convertPmPlanToWorkOrder: (planId: string) => void
  draftPreventivePlan: (equipmentId: string, templateId?: string) => void
  runSupervisorAssistant: (workOrderId?: string) => void
  runTechnicianAssistant: () => void
  selectedWorkOrder?: WorkOrder
  setSelectedWorkOrderId: (workOrderId: string) => void
  setSupervisorQuestion: (value: string) => void
  setTechnicianObservation: (value: string) => void
  startWorkOrder: (workOrderId: string) => void
  supervisorAssistant: SupervisorAssistantResponse | null
  supervisorChat: AssistantTurn[]
  supervisorLoading: boolean
  supervisorQuestion: string
  supervisorStreaming: boolean
  technicianAssistant: TechnicianAssistantResponse | null
  technicianChat: AssistantTurn[]
  technicianLoading: boolean
  technicianObservation: string
  technicianStreaming: boolean
  technicians: AuthUser[]
  mode: 'execution' | 'planning'
  workOrders: WorkOrder[]
}) {
  const selectedEffectiveStatus = selectedWorkOrder ? effectiveWorkOrderStatus(selectedWorkOrder) : undefined
  const selectedEffectiveStatusDetail = selectedEffectiveStatus ? workOrderStatusDetail(selectedEffectiveStatus) : undefined
  const [technicianWaitingLong, setTechnicianWaitingLong] = useState(false)
  const technicianTranscriptRef = useRef<HTMLDivElement | null>(null)
  const supervisorTranscriptRef = useRef<HTMLDivElement | null>(null)
  const isPlanningMode = mode === 'planning'
  const canUseAssistant = canTechnicianAssistant || canSupervisorAssistant
  const [planningTab, setPlanningTab] = useState<PlanningTab>('preventive')

  usePinnedStreamScroll(
    technicianTranscriptRef,
    `${technicianChat.length}:${technicianChat[technicianChat.length - 1]?.content.length ?? 0}:${technicianLoading}:${technicianStreaming}`,
  )
  usePinnedStreamScroll(
    supervisorTranscriptRef,
    `${supervisorChat.length}:${supervisorChat[supervisorChat.length - 1]?.content.length ?? 0}:${supervisorLoading}:${supervisorStreaming}`,
  )

  useEffect(() => {
    if (!technicianLoading || technicianStreaming) {
      setTechnicianWaitingLong(false)
      return
    }
    const timeoutId = window.setTimeout(() => setTechnicianWaitingLong(true), TECHNICIAN_WAITING_MESSAGE_DELAY_MS)
    return () => window.clearTimeout(timeoutId)
  }, [technicianLoading, technicianStreaming])

  return (
    <section className={`workOrderLayout${isPlanningMode ? ' planningMode' : ''}`}>
      <section className="workOrderCenterColumn" aria-label="Work order center pane">
        {isPlanningMode && canAssignWorkOrders && (
          <div className="planningTabsShell">
            <div className="planningTabRow" role="tablist" aria-label="Planning workflows">
              <button
                aria-controls="planning-tab-preventive"
                aria-selected={planningTab === 'preventive'}
                className={planningTab === 'preventive' ? 'selected' : ''}
                id="planning-tab-trigger-preventive"
                onClick={() => setPlanningTab('preventive')}
                role="tab"
                type="button"
              >
                Preventive plans
              </button>
              <button
                aria-controls="planning-tab-dispatch"
                aria-selected={planningTab === 'dispatch'}
                className={planningTab === 'dispatch' ? 'selected' : ''}
                id="planning-tab-trigger-dispatch"
                onClick={() => setPlanningTab('dispatch')}
                role="tab"
                type="button"
              >
                Schedule & dispatch
              </button>
            </div>
            <div
              aria-labelledby="planning-tab-trigger-preventive"
              hidden={planningTab !== 'preventive'}
              id="planning-tab-preventive"
              role="tabpanel"
            >
              <PreventiveMaintenancePanel
                assets={assets}
                convertPmPlanToWorkOrder={convertPmPlanToWorkOrder}
                draftPreventivePlan={draftPreventivePlan}
                isLoading={pmPlanLoading}
                streamText={pmPlanStreamText}
                plans={pmPlans}
                templates={pmTemplates}
              />
            </div>
            <div
              aria-labelledby="planning-tab-trigger-dispatch"
              hidden={planningTab !== 'dispatch'}
              id="planning-tab-dispatch"
              role="tabpanel"
            >
              <PlannerDispatchBoard
                onDispatch={dispatchWorkOrder}
                onOpen={setSelectedWorkOrderId}
                onPlan={planWorkOrder}
                selectedWorkOrderId={selectedWorkOrder?.id}
                technicians={technicians}
                workOrders={workOrders}
              />
            </div>
          </div>
        )}
        {!isPlanningMode && canUseAssistant && (
          <section className="detailPanel workOrderAssistantPanel">
            {selectedWorkOrder ? (
              <>
                {canTechnicianAssistant && (
                  <>
                    <TechnicianScheduleQueue
                      onOpen={setSelectedWorkOrderId}
                      selectedWorkOrderId={selectedWorkOrder.id}
                      workOrders={workOrders}
                    />
                    <TechnicianExecutionCard
                      assistant={technicianAssistant}
                      isLoading={technicianLoading}
                      onComplete={completeSelectedWorkOrder}
                      onStart={startWorkOrder}
                      workOrder={selectedWorkOrder}
                    />
                  </>
                )}
                <div className={canTechnicianAssistant && canSupervisorAssistant ? 'assistantSplit' : 'assistantSplit singleAssistant'}>
                  {canTechnicianAssistant && (
                    <section className="assistantBox technician" aria-busy={technicianLoading}>
                      <div className="sectionHeader">
                        <Bot size={18} />
                        <div>
                          <h2>{technicianAssistantName}</h2>
                          <small>Prioritized work list with short summary and next recommendation</small>
                        </div>
                      </div>
                      <div ref={technicianTranscriptRef} className="assistantTranscript" aria-label={`${technicianAssistantName} technician chat`}>
                        {technicianChat.map((turn) => (
                          <div className={`chatBubble ${turn.role}`} key={turn.id}>
                            <span>{turn.role === 'assistant' ? technicianAssistantName : 'You'}</span>
                            {turn.provider && <small>{assistantProviderLabel(turn)}</small>}
                            <AssistantMessageContent turn={turn} />
                          </div>
                        ))}
                        {technicianLoading && !technicianStreaming && (
                          <div className="chatBubble assistant" aria-live="polite">
                            <span>{technicianAssistantName}</span>
                            <p>
                              <span className="loadingSpinner" aria-hidden="true" />
                              {technicianWaitingLong
                                ? ' Waiting for the LLM response. Local models can take longer on first token.'
                                : ' Thinking...'}
                            </p>
                          </div>
                        )}
                      </div>
                      <form className="assistantComposer" onSubmit={(event) => {
                        event.preventDefault()
                        runTechnicianAssistant()
                      }}>
                        <textarea
                          aria-label="Technician observation"
                          value={technicianObservation}
                          disabled={technicianLoading}
                          onChange={(event) => setTechnicianObservation(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' && !event.shiftKey) {
                              event.preventDefault()
                              runTechnicianAssistant()
                            }
                          }}
                        />
                        <button className="textButton" type="submit" disabled={technicianLoading}>
                          {technicianLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Send size={16} />}
                          Send
                        </button>
                      </form>
                    </section>
                  )}
                  {canSupervisorAssistant && (
                    <section className="assistantBox supervisor" aria-busy={supervisorLoading}>
                      <div className="sectionHeader">
                        <Bot size={18} />
                        <div>
                          <h2>{supervisorAssistantName}</h2>
                          <small>Prioritized work list with short summary and next recommendation</small>
                        </div>
                      </div>
                      <div ref={supervisorTranscriptRef} className="assistantTranscript" aria-label={`${supervisorAssistantName} supervisor chat`}>
                        {supervisorChat.map((turn) => (
                          <div className={`chatBubble ${turn.role}`} key={turn.id}>
                            <span>{turn.role === 'assistant' ? supervisorAssistantName : 'You'}</span>
                            {turn.provider && <small>{assistantProviderLabel(turn)}</small>}
                            <AssistantMessageContent turn={turn} />
                          </div>
                        ))}
                        {supervisorLoading && !supervisorStreaming && (
                          <div className="chatBubble assistant" aria-live="polite">
                            <span>{supervisorAssistantName}</span>
                            <p><span className="loadingSpinner" aria-hidden="true" /> Thinking...</p>
                          </div>
                        )}
                      </div>
                      <form className="assistantComposer" onSubmit={(event) => {
                        event.preventDefault()
                        runSupervisorAssistant(selectedWorkOrder.id)
                      }}>
                        <textarea
                          aria-label="Supervisor question"
                          value={supervisorQuestion}
                          disabled={supervisorLoading}
                          onChange={(event) => setSupervisorQuestion(event.target.value)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter' && !event.shiftKey) {
                              event.preventDefault()
                              runSupervisorAssistant(selectedWorkOrder.id)
                            }
                          }}
                        />
                        <button className="textButton" type="submit" disabled={supervisorLoading}>
                          {supervisorLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Send size={16} />}
                          Send
                        </button>
                      </form>
                    </section>
                  )}
                </div>
              </>
            ) : (
              <p className="emptyState">Select a work order to use the assistant.</p>
            )}
          </section>
        )}
        <section className="detailPanel workOrderQueuePanel">
          <div className="sectionHeader">
            <Briefcase size={18} />
            <h2>{isPlanningMode ? 'Planning backlog' : 'Assigned and follow-up work'}</h2>
          </div>
          <WorkOrderTable
            workOrders={workOrders}
            onOpen={(id) => setSelectedWorkOrderId(id)}
            canAssign={isPlanningMode && canAssignWorkOrders}
            canApprove={canApproveWorkOrders}
            canStart={!isPlanningMode && canTechnicianAssistant}
            technicians={technicians}
            onAssign={assignWorkOrder}
            onApprove={approveWorkOrder}
            onStart={startWorkOrder}
          />
        </section>
      </section>
      {!isPlanningMode && (
        <section className="workOrderRightColumn" aria-label="Work order right pane">
          <section className="detailPanel workOrderDetail">
            {selectedWorkOrder ? (
              <>
                <div className="sectionHeader">
                  <FileText size={18} />
                  <h2>Work Order {selectedWorkOrder.id.replace('WO-', '')}</h2>
                </div>
                <StatusTimeline status={selectedEffectiveStatus ?? selectedWorkOrder.status} />
                <div className="workOrderSummary">
                  <div className="workOrderBadges">
                    <span className="statusPill connected priorityPill">Priority {selectedWorkOrder.priority}</span>
                    <StatusBadge status={selectedEffectiveStatus ?? selectedWorkOrder.status} />
                  </div>
                  <p className="statusDescription">{selectedEffectiveStatusDetail?.description}</p>
                  <p>{selectedWorkOrder.description}</p>
                  <dl>
                    <dt>Assigned to</dt>
                    <dd>{selectedWorkOrder.assigned_to}</dd>
                    <dt>Problem code</dt>
                    <dd>{technicianAssistant?.suggested_problem_code ?? selectedWorkOrder.problem_code}</dd>
                    <dt>Failure class</dt>
                    <dd>{technicianAssistant?.suggested_failure_class ?? selectedWorkOrder.failure_class}</dd>
                    <dt>Due date</dt>
                    <dd>{formatDate(selectedWorkOrder.due_date)}</dd>
                    <dt>Planning status</dt>
                    <dd>{planningStatusLabels[selectedWorkOrder.planning_status]}</dd>
                    <dt>Planned window</dt>
                    <dd>{formatPlanningWindow(selectedWorkOrder)}</dd>
                    <dt>Material readiness</dt>
                    <dd>{materialReadinessLabels[selectedWorkOrder.material_readiness]}</dd>
                    <dt>Material blocker</dt>
                    <dd>{materialBlockerStatusLabels[selectedWorkOrder.material_blocker_status]}</dd>
                    {selectedWorkOrder.material_blocker_note && (
                      <>
                        <dt>Blocker note</dt>
                        <dd>{selectedWorkOrder.material_blocker_note}</dd>
                      </>
                    )}
                    {selectedWorkOrder.spare_reservations.length > 0 && (
                      <>
                        <dt>Spare reservations</dt>
                        <dd>
                          <ul className="spareSummaryList">
                            {selectedWorkOrder.spare_reservations.map((reservation) => (
                              <li key={`${reservation.id ?? reservation.spare_id ?? reservation.spare_name}`}>
                                <strong>{reservation.spare_name}</strong>
                                <span>
                                  {reservation.reserved_qty}/{reservation.required_qty} reserved · {procurementStatusLabels[reservation.procurement_status]} · {materialBlockerStatusLabels[reservation.blocker_status]}
                                </span>
                                {reservation.substitute_name && <span>Substitute: {reservation.substitute_name}</span>}
                              </li>
                            ))}
                          </ul>
                        </dd>
                      </>
                    )}
                    {selectedWorkOrder.dispatch_notes && (
                      <>
                        <dt>Dispatch notes</dt>
                        <dd>{selectedWorkOrder.dispatch_notes}</dd>
                      </>
                    )}
                  </dl>
                </div>
              </>
            ) : (
              <p className="emptyState">Select a work order to review.</p>
            )}
          </section>
        </section>
      )}
    </section>
  )
}

export type WorkOrderPlanningUpdate = Partial<Pick<
  WorkOrder,
  | 'assigned_to'
  | 'planning_status'
  | 'planned_start'
  | 'planned_end'
  | 'outage_window'
  | 'material_readiness'
  | 'material_blocker_status'
  | 'material_blocker_note'
  | 'spare_reservations'
  | 'dispatch_notes'
>>

const planningStatusLabels: Record<WorkOrderPlanningStatus, string> = {
  unscheduled: 'Unscheduled',
  planned: 'Planned',
  dispatched: 'Dispatched',
}

const materialReadinessLabels: Record<MaterialReadiness, string> = {
  unknown: 'Unknown',
  pending: 'Pending',
  ready: 'Ready',
  blocked: 'Blocked',
}

const materialReadinessOptions: MaterialReadiness[] = ['unknown', 'pending', 'ready', 'blocked']

const materialBlockerStatusLabels: Record<MaterialBlockerStatus, string> = {
  not_required: 'No blocker',
  reserved: 'Reserved',
  reorder_requested: 'Reorder requested',
  waiting_procurement: 'Waiting procurement',
  substitute_available: 'Substitute available',
  blocked: 'Blocked',
}

const materialBlockerStatusOptions: MaterialBlockerStatus[] = [
  'not_required',
  'reserved',
  'reorder_requested',
  'waiting_procurement',
  'substitute_available',
  'blocked',
]

const procurementStatusLabels: Record<ProcurementStatus, string> = {
  not_required: 'Not required',
  not_requested: 'Not requested',
  requested: 'Requested',
  ordered: 'Ordered',
  received: 'Received',
}

const procurementStatusOptions: ProcurementStatus[] = ['not_required', 'not_requested', 'requested', 'ordered', 'received']

const pmPlanStatusLabels: Record<PmPlanStatus, string> = {
  active: 'Active',
  converted: 'Converted',
  draft: 'Draft',
  paused: 'Paused',
}

function pmPlanStatusLabel(status: PmPlanStatus) {
  return pmPlanStatusLabels[status]
}

function pmPlanStatusBadgeClass(status: PmPlanStatus) {
  if (status === 'converted') return 'dispatched'
  if (status === 'active') return 'planned'
  if (status === 'paused') return 'unscheduled'
  return 'unscheduled'
}

function PreventiveMaintenancePanel({
  assets,
  convertPmPlanToWorkOrder,
  draftPreventivePlan,
  isLoading,
  plans,
  streamText,
  templates,
}: {
  assets: AssetListItem[]
  convertPmPlanToWorkOrder: (planId: string) => void
  draftPreventivePlan: (equipmentId: string, templateId?: string) => void
  isLoading: boolean
  plans: PmPlan[]
  streamText: string
  templates: PmTemplate[]
}) {
  const streamEndRef = useRef<HTMLDivElement | null>(null)
  const previousPlanIdsRef = useRef<string[]>(plans.map((plan) => plan.id))
  const assetOptions = useMemo(() => {
    const ids = new Set<string>()
    const options = [
      ...assets.map((asset) => {
        ids.add(asset.id)
        return { id: asset.id, label: `${asset.id} - ${asset.name}` }
      }),
      ...templates
        .filter((template) => template.equipment_id && !ids.has(template.equipment_id))
        .map((template) => ({ id: template.equipment_id as string, label: template.equipment_id as string })),
    ]
    return options.length ? options : [{ id: 'RM-DRIVE-01', label: 'RM-DRIVE-01' }]
  }, [assets, templates])
  const [selectedEquipmentId, setSelectedEquipmentId] = useState(assetOptions[0]?.id ?? 'RM-DRIVE-01')
  const applicableTemplates = templates.filter((template) => !template.equipment_id || template.equipment_id === selectedEquipmentId)
  const [selectedTemplateId, setSelectedTemplateId] = useState(applicableTemplates[0]?.id ?? '')
  const [activePlanId, setActivePlanId] = useState(plans[0]?.id ?? '')

  useEffect(() => {
    if (!assetOptions.some((asset) => asset.id === selectedEquipmentId)) {
      setSelectedEquipmentId(assetOptions[0]?.id ?? 'RM-DRIVE-01')
    }
  }, [assetOptions, selectedEquipmentId])

  useEffect(() => {
    const nextTemplates = templates.filter((template) => !template.equipment_id || template.equipment_id === selectedEquipmentId)
    if (!nextTemplates.some((template) => template.id === selectedTemplateId)) {
      setSelectedTemplateId(nextTemplates[0]?.id ?? '')
    }
  }, [selectedEquipmentId, selectedTemplateId, templates])

  const displayedPlans = plans
  const activePlan = displayedPlans.find((plan) => plan.id === activePlanId) ?? displayedPlans[0]

  useEffect(() => {
    const previousPlanIds = previousPlanIdsRef.current
    const nextPlanIds = displayedPlans.map((plan) => plan.id)
    const newlyAddedPlan = displayedPlans.find((plan) => !previousPlanIds.includes(plan.id))
    previousPlanIdsRef.current = nextPlanIds
    if (!displayedPlans.length) {
      setActivePlanId('')
      return
    }
    if (newlyAddedPlan) {
      setActivePlanId(newlyAddedPlan.id)
      return
    }
    if (!displayedPlans.some((plan) => plan.id === activePlanId)) {
      setActivePlanId(displayedPlans[0].id)
    }
  }, [activePlanId, displayedPlans])

  useEffect(() => {
    if (streamText) {
      streamEndRef.current?.scrollIntoView?.({ block: 'end' })
    }
  }, [streamText])

  return (
    <section className="detailPanel pmPlanningPanel" aria-label="Preventive maintenance planning">
      <div className="sectionHeader">
        <Sparkles size={18} />
        <div>
          <h2>Preventive Maintenance Plans</h2>
          <small>Morpheus drafts proactive PM; Smith turns it into technician-ready steps.</small>
        </div>
      </div>
      <div className="pmDraftControls">
        <label>
          Asset
          <select
            aria-label="Select asset for preventive maintenance plan"
            value={selectedEquipmentId}
            onChange={(event) => setSelectedEquipmentId(event.target.value)}
          >
            {assetOptions.map((asset) => (
              <option value={asset.id} key={asset.id}>{asset.label}</option>
            ))}
          </select>
        </label>
        <label>
          Template
          <select
            aria-label="Select preventive maintenance template"
            value={selectedTemplateId}
            onChange={(event) => setSelectedTemplateId(event.target.value)}
          >
            {applicableTemplates.length ? applicableTemplates.map((template) => (
              <option value={template.id} key={template.id}>{template.title}</option>
            )) : <option value="">No template</option>}
          </select>
        </label>
        <button
          className="textButton"
          type="button"
          disabled={isLoading}
          onClick={() => draftPreventivePlan(selectedEquipmentId, selectedTemplateId)}
        >
          {isLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
          Morpheus PM draft
        </button>
      </div>
      <div className="pmTemplateStrip" aria-label="PM templates">
        {applicableTemplates.map((template) => (
          <article className="pmTemplateCard" key={template.id}>
            <strong>{template.title}</strong>
            <small>{template.cadence_days} day cadence · {template.source}</small>
            <p>{template.description}</p>
          </article>
        ))}
      </div>
      {(isLoading || streamText) && (
        <article className="pmDraftStream" aria-label="Morpheus PM draft stream">
          <div className="miniHeader">
            <Sparkles size={16} />
            <h3>Morpheus PM live draft</h3>
          </div>
          <div className="pmDraftStreamViewport">
            {streamText
              ? <FormattedAssistantContent content={streamText} />
              : <p className="emptyState">Morpheus is opening the PM draft stream...</p>}
            <div ref={streamEndRef} aria-hidden="true" />
          </div>
        </article>
      )}
      {activePlan && (
        <article className={`pmPlanCard active ${activePlan.status}`} aria-label="Active preventive maintenance plan">
          <div className="plannerCardHeader">
            <div>
              <small>Active plan</small>
              <strong>{activePlan.title}</strong>
              <small>{activePlan.id} · {activePlan.equipment_id} · next due {formatDate(activePlan.next_due_date)}</small>
            </div>
            <span className={`planningBadge ${pmPlanStatusBadgeClass(activePlan.status)}`}>
              {pmPlanStatusLabel(activePlan.status)}
            </span>
          </div>
          <p>{activePlan.trigger.description}</p>
          <div className="pmPlanColumns">
            <PmList title="Monitoring thresholds" items={activePlan.thresholds} />
            <PmList title="Generated task list" items={activePlan.tasks.map((task) => task.task)} />
            <PmList title="Smith steps" items={activePlan.smith_steps} />
          </div>
          {activePlan.adjustment_notes.length > 0 && <PmList title="LLM adjustment notes" items={activePlan.adjustment_notes} />}
          {activePlan.spares_strategy.length > 0 && <PmList title="Spares strategy" items={activePlan.spares_strategy} />}
          <div className="plannerActions">
            <button
              className="outlineButton"
              type="button"
              disabled={isLoading || activePlan.status === 'converted'}
              onClick={() => convertPmPlanToWorkOrder(activePlan.id)}
            >
              Convert to planned work
            </button>
            {activePlan.converted_work_order_id && <span className="plannerHint">Created {activePlan.converted_work_order_id}</span>}
          </div>
        </article>
      )}
      <div className="pmPlanTablePanel" aria-label="Preventive maintenance plan table">
        <div className="miniHeader">
          <h3>All PM plans</h3>
          <small>{displayedPlans.length} plan{displayedPlans.length === 1 ? '' : 's'}</small>
        </div>
        <table className="pmPlanTable" aria-label="Preventive maintenance plans">
          <thead>
            <tr>
              <th scope="col">Plan</th>
              <th scope="col">Asset</th>
              <th scope="col">Next due</th>
              <th scope="col">Status</th>
              <th scope="col">Work order</th>
              <th scope="col">Action</th>
            </tr>
          </thead>
          <tbody>
            {displayedPlans.length ? (
              displayedPlans.map((plan) => (
                <tr className={plan.id === activePlan?.id ? 'selected' : ''} key={plan.id}>
                  <td>
                    <strong>{plan.id}</strong>
                    <small>{plan.title}</small>
                  </td>
                  <td>{plan.equipment_id}</td>
                  <td>{formatDate(plan.next_due_date)}</td>
                  <td>
                    <span className={`planningBadge ${pmPlanStatusBadgeClass(plan.status)}`}>
                      {pmPlanStatusLabel(plan.status)}
                    </span>
                  </td>
                  <td>{plan.converted_work_order_id ?? 'Not created'}</td>
                  <td>
                    <button
                      aria-pressed={plan.id === activePlan?.id}
                      className="outlineButton compactButton"
                      onClick={() => setActivePlanId(plan.id)}
                      type="button"
                    >
                      {plan.id === activePlan?.id ? 'Active' : 'Select'}
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="pmPlanEmptyCell" colSpan={6}>
                  No PM plans generated yet. Draft one from asset risk prediction and a PM template.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function PmList({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null
  return (
    <section className="pmPlanList">
      <h3>{title}</h3>
      <ul>
        {items.slice(0, 6).map((item, index) => (
          <li key={`${title}-${index}`}>{item}</li>
        ))}
      </ul>
    </section>
  )
}

function PlannerDispatchBoard({
  onDispatch,
  onOpen,
  onPlan,
  selectedWorkOrderId,
  technicians,
  workOrders,
}: {
  onDispatch: (workOrderId: string) => void
  onOpen: (workOrderId: string) => void
  onPlan: (workOrderId: string, payload: WorkOrderPlanningUpdate) => void
  selectedWorkOrderId?: string
  technicians: AuthUser[]
  workOrders: WorkOrder[]
}) {
  const openWorkOrders = useMemo(
    () => workOrders.filter((order) => !['COMP', 'CLOSE'].includes(order.status)),
    [workOrders],
  )
  const openWorkOrderIds = openWorkOrders.map((order) => order.id).join('|')
  const [selectedPlannerOrderId, setSelectedPlannerOrderId] = useState(selectedWorkOrderId ?? openWorkOrders[0]?.id ?? '')
  const selectedPlannerOrder = openWorkOrders.find((order) => order.id === selectedPlannerOrderId) ?? openWorkOrders[0]

  useEffect(() => {
    if (selectedWorkOrderId && openWorkOrders.some((order) => order.id === selectedWorkOrderId)) {
      setSelectedPlannerOrderId(selectedWorkOrderId)
      return
    }
    if (!openWorkOrders.some((order) => order.id === selectedPlannerOrderId)) {
      setSelectedPlannerOrderId(openWorkOrders[0]?.id ?? '')
    }
  }, [openWorkOrderIds, openWorkOrders, selectedPlannerOrderId, selectedWorkOrderId])

  function selectPlannerOrder(workOrderId: string) {
    setSelectedPlannerOrderId(workOrderId)
    onOpen(workOrderId)
  }

  return (
    <section className="detailPanel plannerDispatchBoard" aria-label="Maintenance planning and dispatch board">
      <div className="sectionHeader">
        <CalendarClock size={18} />
        <div>
          <h2>Planning, Scheduling & Dispatch</h2>
          <small>{openWorkOrders.length} open work order{openWorkOrders.length === 1 ? '' : 's'} ready for planner review</small>
        </div>
      </div>
      {openWorkOrders.length > 0 ? (
        <>
          <label className="plannerWorkOrderPicker">
            Work order
            <select
              aria-label="Select work order for planning"
              value={selectedPlannerOrder?.id ?? ''}
              onChange={(event) => selectPlannerOrder(event.target.value)}
            >
              {openWorkOrders.map((order) => (
                <option value={order.id} key={order.id}>
                  {order.id} - {order.title}
                </option>
              ))}
            </select>
          </label>
          <PlannerDispatchCard
            key={selectedPlannerOrder.id}
            onDispatch={onDispatch}
            onOpen={onOpen}
            onPlan={onPlan}
            order={selectedPlannerOrder}
            technicians={technicians}
          />
        </>
      ) : (
        <p className="plannerHint">No open work orders are ready for planner review.</p>
      )}
    </section>
  )
}

function PlannerDispatchCard({
  onDispatch,
  onOpen,
  onPlan,
  order,
  technicians,
}: {
  onDispatch: (workOrderId: string) => void
  onOpen: (workOrderId: string) => void
  onPlan: (workOrderId: string, payload: WorkOrderPlanningUpdate) => void
  order: WorkOrder
  technicians: AuthUser[]
}) {
  const [assignedTo, setAssignedTo] = useState(order.assigned_to)
  const [plannedStart, setPlannedStart] = useState(toDateTimeLocal(order.planned_start))
  const [plannedEnd, setPlannedEnd] = useState(toDateTimeLocal(order.planned_end))
  const [materialReadiness, setMaterialReadiness] = useState<MaterialReadiness>(order.material_readiness)
  const [materialBlockerStatus, setMaterialBlockerStatus] = useState<MaterialBlockerStatus>(order.material_blocker_status)
  const [materialBlockerNote, setMaterialBlockerNote] = useState(order.material_blocker_note ?? '')
  const [spareReservations, setSpareReservations] = useState<WorkOrderSpareReservation[]>(order.spare_reservations)
  const [outageWindow, setOutageWindow] = useState(order.outage_window ?? '')
  const [dispatchNotes, setDispatchNotes] = useState(order.dispatch_notes ?? '')

  useEffect(() => {
    setAssignedTo(order.assigned_to)
    setPlannedStart(toDateTimeLocal(order.planned_start))
    setPlannedEnd(toDateTimeLocal(order.planned_end))
    setMaterialReadiness(order.material_readiness)
    setMaterialBlockerStatus(order.material_blocker_status)
    setMaterialBlockerNote(order.material_blocker_note ?? '')
    setSpareReservations(order.spare_reservations)
    setOutageWindow(order.outage_window ?? '')
    setDispatchNotes(order.dispatch_notes ?? '')
  }, [
    order.id,
    order.assigned_to,
    order.planned_start,
    order.planned_end,
    order.material_readiness,
    order.material_blocker_status,
    order.material_blocker_note,
    order.spare_reservations,
    order.outage_window,
    order.dispatch_notes,
  ])

  const technicianOptions = technicians.some((technician) => technician.display_name === assignedTo)
    ? technicians
    : [
        {
          id: `current-${order.id}`,
          email: '',
          display_name: assignedTo,
          role: 'maintenance_technician' as const,
          is_active: true,
        },
        ...technicians,
      ]
  const dispatchBlockedReason = dispatchBlockReason(order, plannedStart, materialReadiness, materialBlockerStatus, spareReservations)

  function savePlan() {
    onPlan(order.id, {
      assigned_to: assignedTo,
      planning_status: plannedStart ? 'planned' : 'unscheduled',
      planned_start: plannedStart || null,
      planned_end: plannedEnd || null,
      material_readiness: materialReadiness,
      material_blocker_status: materialBlockerStatus,
      material_blocker_note: materialBlockerNote.trim() || null,
      spare_reservations: spareReservations.map(normalizeSpareReservation),
      outage_window: outageWindow.trim() || null,
      dispatch_notes: dispatchNotes.trim() || null,
    })
  }

  function updateSpareReservation(index: number, updates: Partial<WorkOrderSpareReservation>) {
    setSpareReservations((items) => items.map((item, itemIndex) => (
      itemIndex === index ? { ...item, ...updates } : item
    )))
  }

  function addSpareReservation() {
    setSpareReservations((items) => [
      ...items,
      {
        spare_name: '',
        required_qty: 1,
        reserved_qty: 0,
        available_qty: 0,
        reorder_requested: false,
        procurement_status: 'not_requested',
        procurement_lead_time_days: 0,
        expected_available_date: null,
        substitute_spare_id: null,
        substitute_name: null,
        blocker_status: 'not_required',
        blocker_note: null,
      },
    ])
  }

  return (
    <article className={`plannerCard ${order.planning_status}`} aria-label={`${order.id} planner card`}>
      <div className="plannerCardHeader">
        <button className="workOrderCellButton workOrderIdButton" type="button" onClick={() => onOpen(order.id)}>
          {order.id}
        </button>
        <div>
          <strong>{order.title}</strong>
          <small>{order.equipment_id} · Priority {order.priority}</small>
        </div>
        <span className={`planningBadge ${order.planning_status}`}>{planningStatusLabels[order.planning_status]}</span>
      </div>
      <div className="plannerFieldGrid">
        <label>
          Technician
          <select value={assignedTo} onChange={(event) => setAssignedTo(event.target.value)}>
            {technicianOptions.map((technician) => (
              <option value={technician.display_name} key={`${order.id}-${technician.id}`}>
                {technician.display_name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Start
          <span className="plannerDateControl">
            <input
              aria-label={`Planned start ${order.id}`}
              className={`plannerDateInput ${plannedStart ? 'hasValue' : 'empty'}`}
              type="datetime-local"
              value={plannedStart}
              onClick={(event) => (event.currentTarget as HTMLInputElement & { showPicker?: () => void }).showPicker?.()}
              onChange={(event) => setPlannedStart(event.target.value)}
            />
            {!plannedStart && <span className="plannerDatePlaceholder" aria-hidden="true">Pick start</span>}
          </span>
        </label>
        <label>
          End
          <span className="plannerDateControl">
            <input
              aria-label={`Planned end ${order.id}`}
              className={`plannerDateInput ${plannedEnd ? 'hasValue' : 'empty'}`}
              type="datetime-local"
              value={plannedEnd}
              onClick={(event) => (event.currentTarget as HTMLInputElement & { showPicker?: () => void }).showPicker?.()}
              onChange={(event) => setPlannedEnd(event.target.value)}
            />
            {!plannedEnd && <span className="plannerDatePlaceholder" aria-hidden="true">Pick end</span>}
          </span>
        </label>
        <label>
          Materials
          <select
            aria-label={`Material readiness ${order.id}`}
            value={materialReadiness}
            onChange={(event) => setMaterialReadiness(event.target.value as MaterialReadiness)}
          >
            {materialReadinessOptions.map((option) => (
              <option value={option} key={option}>{materialReadinessLabels[option]}</option>
            ))}
          </select>
        </label>
        <label>
          Material blocker
          <select
            aria-label={`Material blocker ${order.id}`}
            value={materialBlockerStatus}
            onChange={(event) => setMaterialBlockerStatus(event.target.value as MaterialBlockerStatus)}
          >
            {materialBlockerStatusOptions.map((option) => (
              <option value={option} key={option}>{materialBlockerStatusLabels[option]}</option>
            ))}
          </select>
        </label>
      </div>
      <section className="plannerSparesPanel" aria-label={`Spare availability ${order.id}`}>
        <div className="plannerSparesHeader">
          <div>
            <h3>Spare availability & procurement</h3>
            <small>Reservations and reorder state are saved deterministically for this work order.</small>
          </div>
          <button className="outlineButton compactButton" type="button" onClick={addSpareReservation}>
            Add spare
          </button>
        </div>
        {spareReservations.length > 0 ? (
          <div className="plannerSparesList">
            {spareReservations.map((reservation, index) => (
              <div className="plannerSpareRow" key={`${reservation.id ?? 'new'}-${index}`}>
                <label className="plannerSpareName">
                  Spare
                  <input
                    aria-label={`Spare name ${order.id} ${index + 1}`}
                    value={reservation.spare_name}
                    onChange={(event) => updateSpareReservation(index, { spare_name: event.target.value })}
                  />
                </label>
                <label>
                  Required
                  <input
                    aria-label={`Required quantity ${order.id} ${index + 1}`}
                    min="0"
                    type="number"
                    value={reservation.required_qty}
                    onChange={(event) => updateSpareReservation(index, { required_qty: numberFromInput(event.target.value) })}
                  />
                </label>
                <label>
                  Reserved
                  <input
                    aria-label={`Reserved quantity ${order.id} ${index + 1}`}
                    min="0"
                    type="number"
                    value={reservation.reserved_qty}
                    onChange={(event) => updateSpareReservation(index, { reserved_qty: numberFromInput(event.target.value) })}
                  />
                </label>
                <label>
                  Available
                  <input
                    aria-label={`Available quantity ${order.id} ${index + 1}`}
                    min="0"
                    type="number"
                    value={reservation.available_qty}
                    onChange={(event) => updateSpareReservation(index, { available_qty: numberFromInput(event.target.value) })}
                  />
                </label>
                <label>
                  Procurement
                  <select
                    aria-label={`Procurement status ${order.id} ${index + 1}`}
                    value={reservation.procurement_status}
                    onChange={(event) => updateSpareReservation(index, { procurement_status: event.target.value as ProcurementStatus })}
                  >
                    {procurementStatusOptions.map((option) => (
                      <option value={option} key={option}>{procurementStatusLabels[option]}</option>
                    ))}
                  </select>
                </label>
                <label>
                  Lead time
                  <input
                    aria-label={`Procurement lead time ${order.id} ${index + 1}`}
                    min="0"
                    type="number"
                    value={reservation.procurement_lead_time_days}
                    onChange={(event) => updateSpareReservation(index, { procurement_lead_time_days: numberFromInput(event.target.value) })}
                  />
                </label>
                <label>
                  Expected
                  <input
                    aria-label={`Expected availability ${order.id} ${index + 1}`}
                    type="date"
                    value={reservation.expected_available_date ?? ''}
                    onChange={(event) => updateSpareReservation(index, { expected_available_date: event.target.value || null })}
                  />
                </label>
                <label>
                  Row blocker
                  <select
                    aria-label={`Spare blocker ${order.id} ${index + 1}`}
                    value={reservation.blocker_status}
                    onChange={(event) => updateSpareReservation(index, { blocker_status: event.target.value as MaterialBlockerStatus })}
                  >
                    {materialBlockerStatusOptions.map((option) => (
                      <option value={option} key={option}>{materialBlockerStatusLabels[option]}</option>
                    ))}
                  </select>
                </label>
                <label className="plannerSpareReorder">
                  <input
                    aria-label={`Reorder requested ${order.id} ${index + 1}`}
                    checked={reservation.reorder_requested}
                    type="checkbox"
                    onChange={(event) => updateSpareReservation(index, { reorder_requested: event.target.checked })}
                  />
                  Reorder
                </label>
                <label className="plannerSpareSubstitute">
                  Substitute
                  <input
                    aria-label={`Substitute ${order.id} ${index + 1}`}
                    value={reservation.substitute_name ?? ''}
                    onChange={(event) => updateSpareReservation(index, { substitute_name: event.target.value || null })}
                  />
                </label>
                <label className="plannerSpareNote">
                  Blocker note
                  <input
                    aria-label={`Spare blocker note ${order.id} ${index + 1}`}
                    value={reservation.blocker_note ?? ''}
                    onChange={(event) => updateSpareReservation(index, { blocker_note: event.target.value || null })}
                  />
                </label>
              </div>
            ))}
          </div>
        ) : (
          <p className="plannerHint">No spare reservations are attached to this work order.</p>
        )}
      </section>
      <label className="plannerWideField">
        Material blocker note
        <input value={materialBlockerNote} onChange={(event) => setMaterialBlockerNote(event.target.value)} />
      </label>
      <label className="plannerWideField">
        Outage window
        <input value={outageWindow} onChange={(event) => setOutageWindow(event.target.value)} />
      </label>
      <label className="plannerWideField">
        Dispatch notes
        <textarea value={dispatchNotes} onChange={(event) => setDispatchNotes(event.target.value)} />
      </label>
      <div className="plannerActions">
        <button className="outlineButton" type="button" onClick={savePlan}>
          Save plan
        </button>
        <button
          className="textButton"
          type="button"
          disabled={Boolean(dispatchBlockedReason)}
          onClick={() => onDispatch(order.id)}
        >
          <Truck size={16} />
          Dispatch
        </button>
      </div>
      {dispatchBlockedReason && <p className="plannerHint">{dispatchBlockedReason}</p>}
    </article>
  )
}

function TechnicianScheduleQueue({
  onOpen,
  selectedWorkOrderId,
  workOrders,
}: {
  onOpen: (workOrderId: string) => void
  selectedWorkOrderId: string
  workOrders: WorkOrder[]
}) {
  const assignedWorkOrders = workOrders
    .filter((order) => !['COMP', 'CLOSE'].includes(order.status))
    .sort((left, right) => planningSortValue(left) - planningSortValue(right))

  return (
    <section className="technicianScheduleQueue" aria-label="Technician assigned schedule">
      <div className="sectionHeader">
        <CalendarClock size={18} />
        <div>
          <h2>Assigned Schedule</h2>
          <small>{assignedWorkOrders.length} open assigned job{assignedWorkOrders.length === 1 ? '' : 's'}</small>
        </div>
      </div>
      <div className="technicianScheduleList">
        {assignedWorkOrders.map((order) => (
          <button
            className={`technicianScheduleItem ${order.id === selectedWorkOrderId ? 'selected' : ''}`}
            key={order.id}
            type="button"
            onClick={() => onOpen(order.id)}
          >
            <span>{order.id}</span>
            <strong>{order.title}</strong>
            <small>{planningStatusLabels[order.planning_status]} · {formatPlanningWindow(order)}</small>
          </button>
        ))}
      </div>
    </section>
  )
}

function dispatchBlockReason(
  order: WorkOrder,
  plannedStart: string,
  materialReadiness: MaterialReadiness,
  materialBlockerStatus: MaterialBlockerStatus,
  spareReservations: WorkOrderSpareReservation[],
) {
  if (order.planning_status === 'dispatched') return 'Already dispatched to the assigned technician.'
  if (order.status === 'WAPPR') return 'Approval is required before dispatch.'
  if (!plannedStart) return 'Set a planned start before dispatch.'
  if (materialReadiness === 'blocked') return 'Resolve blocked materials before dispatch.'
  if (['blocked', 'waiting_procurement', 'reorder_requested'].includes(materialBlockerStatus)) {
    return 'Resolve the material blocker before dispatch.'
  }
  if (spareReservations.some((reservation) => ['blocked', 'waiting_procurement', 'reorder_requested'].includes(reservation.blocker_status))) {
    return 'Resolve the material blocker before dispatch.'
  }
  return ''
}

function normalizeSpareReservation(reservation: WorkOrderSpareReservation): WorkOrderSpareReservation {
  return {
    ...reservation,
    spare_name: reservation.spare_name.trim(),
    required_qty: Math.max(0, reservation.required_qty),
    reserved_qty: Math.max(0, reservation.reserved_qty),
    available_qty: Math.max(0, reservation.available_qty),
    substitute_name: reservation.substitute_name?.trim() || null,
    blocker_note: reservation.blocker_note?.trim() || null,
  }
}

function numberFromInput(value: string) {
  const parsed = Number.parseInt(value, 10)
  return Number.isFinite(parsed) ? Math.max(0, parsed) : 0
}

function toDateTimeLocal(value?: string | null) {
  return value ? value.slice(0, 16) : ''
}

function formatPlanningWindow(order: WorkOrder) {
  if (!order.planned_start) return 'Not scheduled'
  if (!order.planned_end) return formatDate(order.planned_start)
  return `${formatDate(order.planned_start)} to ${formatDate(order.planned_end)}`
}

function planningSortValue(order: WorkOrder) {
  if (order.planned_start) {
    const parsed = new Date(order.planned_start).getTime()
    if (Number.isFinite(parsed)) return parsed
  }
  return new Date(order.due_date).getTime()
}
