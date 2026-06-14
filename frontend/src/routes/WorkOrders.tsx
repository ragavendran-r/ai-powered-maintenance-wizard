import { Bot, Briefcase, FileText, Send } from 'lucide-react'
import type {
  AuthUser,
  SupervisorAssistantResponse,
  TechnicianAssistantResponse,
  WorkOrder,
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
        <section className="detailPanel workOrderAssistantPanel">
          {selectedWorkOrder ? (
            <>
              {canTechnicianAssistant && (
                <TechnicianExecutionCard
                  assistant={technicianAssistant}
                  isLoading={technicianLoading}
                  onComplete={completeSelectedWorkOrder}
                  onStart={startWorkOrder}
                  workOrder={selectedWorkOrder}
                />
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
                <span className="statusPill connected">Priority {selectedWorkOrder.priority}</span>
                <StatusBadge status={selectedWorkOrder.status} />
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
