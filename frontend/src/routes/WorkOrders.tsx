import { useEffect, useMemo, useState } from 'react'
import { Bot, Briefcase, CalendarClock, FileText, Send, Truck } from 'lucide-react'
import type {
  AuthUser,
  MaterialReadiness,
  SupervisorAssistantResponse,
  TechnicianAssistantResponse,
  WorkOrder,
  WorkOrderPlanningStatus,
} from '../services/api'
import type { AssistantTurn } from '../assistantContent'
import { AssistantMessageContent } from '../assistantContent'
import {
  supervisorAssistantName,
  technicianAssistantName,
} from '../appModel'
import { workOrderStatusDetail } from '../workOrderStatus'
import {
  StatusBadge,
  StatusTimeline,
  TechnicianExecutionCard,
  WorkOrderTable,
} from '../sharedComponents'
import { formatDate } from '../appModel'

export function WorkOrdersRoute({
  approveWorkOrder,
  assignWorkOrder,
  canApproveWorkOrders,
  canAssignWorkOrders,
  canSupervisorAssistant,
  canTechnicianAssistant,
  completeSelectedWorkOrder,
  dispatchWorkOrder,
  planWorkOrder,
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
  workOrderMessage,
  workOrders,
}: {
  approveWorkOrder: (workOrderId: string) => void
  assignWorkOrder: (workOrderId: string, assignedTo: string) => void
  canApproveWorkOrders: boolean
  canAssignWorkOrders: boolean
  canSupervisorAssistant: boolean
  canTechnicianAssistant: boolean
  completeSelectedWorkOrder: () => void
  dispatchWorkOrder: (workOrderId: string) => void
  planWorkOrder: (workOrderId: string, payload: WorkOrderPlanningUpdate) => void
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
  workOrderMessage: string
  workOrders: WorkOrder[]
}) {
  return (
    <section className="workOrderLayout">
      <section className="workOrderCenterColumn" aria-label="Work order center pane">
        {canAssignWorkOrders && (
          <PlannerDispatchBoard
            onDispatch={dispatchWorkOrder}
            onOpen={setSelectedWorkOrderId}
            onPlan={planWorkOrder}
            selectedWorkOrderId={selectedWorkOrder?.id}
            technicians={technicians}
            workOrders={workOrders}
          />
        )}
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
                        <small>Technician AI assistant with shared LLM configuration</small>
                      </div>
                    </div>
                    <div className="assistantTranscript" aria-label={`${technicianAssistantName} technician chat`}>
                      {technicianChat.map((turn) => (
                        <div className={`chatBubble ${turn.role}`} key={turn.id}>
                          <span>{turn.role === 'assistant' ? technicianAssistantName : 'You'}</span>
                          {turn.provider && <small>{turn.usedLiveProvider ? 'Live LLM' : 'LLM fallback'} · {turn.provider}</small>}
                          <AssistantMessageContent turn={turn} />
                        </div>
                      ))}
                      {technicianLoading && !technicianStreaming && (
                        <div className="chatBubble assistant" aria-live="polite">
                          <span>{technicianAssistantName}</span>
                          <p><span className="loadingSpinner" aria-hidden="true" /> Thinking...</p>
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
                        <small>Supervisor AI assistant with shared LLM configuration</small>
                      </div>
                    </div>
                    <div className="assistantTranscript" aria-label={`${supervisorAssistantName} supervisor chat`}>
                      {supervisorChat.map((turn) => (
                        <div className={`chatBubble ${turn.role}`} key={turn.id}>
                          <span>{turn.role === 'assistant' ? supervisorAssistantName : 'You'}</span>
                          {turn.provider && <small>{turn.usedLiveProvider ? 'Live LLM' : 'LLM fallback'} · {turn.provider}</small>}
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
                      />
                      <button className="textButton" type="submit" disabled={supervisorLoading}>
                        {supervisorLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Send size={16} />}
                        Send
                      </button>
                    </form>
                  </section>
                )}
                {!canTechnicianAssistant && !canSupervisorAssistant && (
                  <section className="assistantBox">
                    <p className="emptyState">Neo is available to technician and supervisor accounts.</p>
                  </section>
                )}
              </div>
            </>
          ) : (
            <p className="emptyState">Select a work order to use the assistant.</p>
          )}
        </section>
        <section className="detailPanel workOrderQueuePanel">
          <div className="sectionHeader">
            <Briefcase size={18} />
            <h2>WOs with follow up actions</h2>
          </div>
          <WorkOrderTable
            workOrders={workOrders}
            onOpen={(id) => setSelectedWorkOrderId(id)}
            canAssign={canAssignWorkOrders}
            canApprove={canApproveWorkOrders}
            canStart={canTechnicianAssistant}
            technicians={technicians}
            onAssign={assignWorkOrder}
            onApprove={approveWorkOrder}
            onStart={startWorkOrder}
          />
          {workOrderMessage && <p className="inlineStatus">{workOrderMessage}</p>}
        </section>
      </section>
      <section className="workOrderRightColumn" aria-label="Work order right pane">
        <section className="detailPanel workOrderDetail">
          {selectedWorkOrder ? (
            <>
              <div className="sectionHeader">
                <FileText size={18} />
                <h2>Work Order {selectedWorkOrder.id.replace('WO-', '')}</h2>
              </div>
              <StatusTimeline status={selectedWorkOrder.status} />
              <div className="workOrderSummary">
                <div className="workOrderBadges">
                  <span className="statusPill connected priorityPill">Priority {selectedWorkOrder.priority}</span>
                  <StatusBadge status={selectedWorkOrder.status} />
                </div>
                <p className="statusDescription">{workOrderStatusDetail(selectedWorkOrder.status).description}</p>
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
  const [outageWindow, setOutageWindow] = useState(order.outage_window ?? '')
  const [dispatchNotes, setDispatchNotes] = useState(order.dispatch_notes ?? '')

  useEffect(() => {
    setAssignedTo(order.assigned_to)
    setPlannedStart(toDateTimeLocal(order.planned_start))
    setPlannedEnd(toDateTimeLocal(order.planned_end))
    setMaterialReadiness(order.material_readiness)
    setOutageWindow(order.outage_window ?? '')
    setDispatchNotes(order.dispatch_notes ?? '')
  }, [
    order.id,
    order.assigned_to,
    order.planned_start,
    order.planned_end,
    order.material_readiness,
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
  const dispatchBlockedReason = dispatchBlockReason(order, plannedStart, materialReadiness)

  function savePlan() {
    onPlan(order.id, {
      assigned_to: assignedTo,
      planning_status: plannedStart ? 'planned' : 'unscheduled',
      planned_start: plannedStart || null,
      planned_end: plannedEnd || null,
      material_readiness: materialReadiness,
      outage_window: outageWindow.trim() || null,
      dispatch_notes: dispatchNotes.trim() || null,
    })
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
      </div>
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

function dispatchBlockReason(order: WorkOrder, plannedStart: string, materialReadiness: MaterialReadiness) {
  if (order.planning_status === 'dispatched') return 'Already dispatched to the assigned technician.'
  if (order.status === 'WAPPR') return 'Approval is required before dispatch.'
  if (!plannedStart) return 'Set a planned start before dispatch.'
  if (materialReadiness === 'blocked') return 'Resolve blocked materials before dispatch.'
  return ''
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
