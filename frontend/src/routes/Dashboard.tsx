import type { RefObject } from 'react'
import { BarChart3, Search, Send, Sparkles } from 'lucide-react'
import type { DashboardSummary, NeoTable, WorkOrder } from '../services/api'
import type { AssistantTurn } from '../assistantContent'
import {
  AssistantMessageContent,
  assistantProviderLabel,
} from '../assistantContent'
import {
  BarChart,
  KpiCard,
  MiniBars,
  NeoResultTable,
  WorkOrderTable,
} from '../sharedComponents'

export type DashboardMetrics = {
  assetsAtRisk: number
  overdueEmergency: number
  pmOverdue: number
  equipmentPerformance: number
  followUps: number
}

export function DashboardRoute({
  approveWorkOrder,
  canApproveWorkOrders,
  canTechnicianAssistant,
  dashboard,
  dashboardMetrics,
  neoLoading,
  neoMessages,
  neoQuestion,
  neoStreaming,
  neoTable,
  neoTranscriptRef,
  openWorkOrder,
  sendNeoQuestion,
  setNeoQuestion,
  startWorkOrder,
  workOrders,
}: {
  approveWorkOrder: (workOrderId: string) => void
  canApproveWorkOrders: boolean
  canTechnicianAssistant: boolean
  dashboard: DashboardSummary
  dashboardMetrics: DashboardMetrics
  neoLoading: boolean
  neoMessages: AssistantTurn[]
  neoQuestion: string
  neoStreaming: boolean
  neoTable: NeoTable | null
  neoTranscriptRef: RefObject<HTMLDivElement | null>
  openWorkOrder: (workOrderId: string) => void
  sendNeoQuestion: () => void
  setNeoQuestion: (value: string) => void
  startWorkOrder: (workOrderId: string) => void
  workOrders: WorkOrder[]
}) {
  return (
    <section className="dashboardWithNeo">
      <div className="dashboardKpiBand" aria-label="Dashboard KPI summary">
        <KpiCard
          className="kpiRisk"
          title="Assets at risk"
          value={`${dashboardMetrics.assetsAtRisk}`}
          unit="assets"
          detail="Key contributors: sensor trends, incomplete maintenance, and health score."
          ai="AI explained: asset risk uses current health, alert severity, work status, and anomaly context."
        />
        <KpiCard className="kpiEmergency" title="Overdue emergency work" value={`${dashboardMetrics.overdueEmergency}`} unit="work orders" detail="Priority 1 open work requiring supervisor attention." />
        <KpiCard className="kpiPm" title="PM Work orders overdue" value={`${dashboardMetrics.pmOverdue}`} unit="work orders" detail="Preventive maintenance items waiting on material or approval." />
        <KpiCard className="kpiPerformance" title="Equipment performance" value={`${dashboardMetrics.equipmentPerformance}`} unit="%" detail="Average health across tracked steel-plant assets." />
      </div>
      <div className="dashboardMainGrid">
        <div className="dashboardCenterColumn">
          <section className="neoPanel" aria-label="Neo dashboard assistant" aria-busy={neoLoading}>
            <div className="neoHeader">
              <span className="neoAvatar">N</span>
              <div>
                <h2>Neo</h2>
                <small>Dashboard AI assistant</small>
              </div>
            </div>
            <div className="neoTranscript" ref={neoTranscriptRef} aria-label="Neo chat transcript">
              {neoMessages.map((turn) => (
                <div className={`chatBubble ${turn.role}`} key={turn.id}>
                  <span>{turn.role === 'assistant' ? 'Neo' : 'You'}</span>
                  {assistantProviderLabel(turn) && <small>{assistantProviderLabel(turn)}</small>}
                  <AssistantMessageContent turn={turn} />
                </div>
              ))}
              {neoLoading && !neoStreaming && (
                <div className="chatBubble assistant neoThinking" aria-live="polite">
                  <span>Neo</span>
                  <p><span className="loadingSpinner" aria-hidden="true" /> Thinking...</p>
                </div>
              )}
            </div>
            <div className="neoPromptChips" aria-label="Neo prompt shortcuts">
              <button type="button" disabled={neoLoading} onClick={() => setNeoQuestion('Show assets at risk')}>Assets</button>
              <button type="button" disabled={neoLoading} onClick={() => setNeoQuestion('Show work orders needing follow-up')}>Work orders</button>
              <button type="button" disabled={neoLoading} onClick={() => setNeoQuestion('Show users and roles')}>User table</button>
            </div>
            <form className="neoComposer" onSubmit={(event) => {
              event.preventDefault()
              sendNeoQuestion()
            }}>
              <textarea
                aria-label="Ask Neo"
                value={neoQuestion}
                disabled={neoLoading}
                onChange={(event) => setNeoQuestion(event.target.value)}
              />
              <button className="textButton" type="submit" disabled={neoLoading}>
                {neoLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Send size={16} />}
                Send
              </button>
            </form>
          </section>
          <section className="detailPanel neoResultPanel">
            <div className="sectionHeader">
              <Sparkles size={18} />
              <h2>{neoTable?.title ?? 'Neo Results'}</h2>
            </div>
            {neoTable ? <NeoResultTable table={neoTable} /> : <p className="emptyState">Ask Neo to show assets, work orders, or users. Results appear here.</p>}
          </section>
          <section className="detailPanel queuePanel">
            <div className="sectionHeader">
              <Search size={18} />
              <h2>Work queues</h2>
            </div>
            <WorkOrderTable
              compact
              workOrders={workOrders}
              canApprove={canApproveWorkOrders}
              canStart={canTechnicianAssistant}
              onApprove={approveWorkOrder}
              onStart={startWorkOrder}
              onOpen={openWorkOrder}
            />
          </section>
        </div>
        <div className="dashboardRightColumn">
          <section className="detailPanel chartPanel dashboardEfficiency">
            <div className="sectionHeader">
              <BarChart3 size={18} />
              <h2>Equipment efficiency</h2>
            </div>
            <BarChart assets={dashboard.highest_risk_equipment} />
          </section>
          <section className="detailPanel slaPanel">
            <h2>SLA compliance by incident priority</h2>
            <MiniBars values={[92, 78, 64, 88]} labels={['P1', 'P2', 'P3', 'P4']} />
          </section>
        </div>
      </div>
    </section>
  )
}
