import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Activity,
  AlertTriangle,
  Bot,
  Briefcase,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  FileText,
  Gauge,
  Info,
  LogOut,
  ShieldAlert,
  Sparkles,
  Users,
  Wrench,
  X,
  XCircle,
} from 'lucide-react'
import {
  api,
  fallbackDashboard,
  type AssetDetail,
  type AssetDetailSection,
  type AssetListItem,
  type AuthSession,
  type AuthUser,
  type DashboardSummary,
  type LearningDatasetSnapshot,
  type LearningExample,
  type LearningArtifactCleanupResult,
  type LearningEmbeddingProfile,
  type LearningRagMigrationPlan,
  type LearningModelDeployment,
  type AbnormalAlertReport,
  type DigitalMaintenanceLogEntry,
  type LearningModelVersion,
  type LearningSummary,
  type MaintenanceDecisionSummary,
  type MaintenanceInsightReportSummary,
  type NeoAction,
  type NeoChatResponse,
  type NeoTable,
  type PaginatedResponse,
  type PmPlan,
  type PmTemplate,
  type PredictionResponse,
  type RcaCase,
  type Recommendation,
  type SupervisorAssistantResponse,
  type TechnicianAssistantResponse,
  type StreamingStatus,
  type StructuredMaintenanceReport,
  type UserRole,
  type WorkOrder,
  type WorkOrderCreateRequest,
} from './services/api'
import { getUserPermissions } from './permissions'
import {
  applicationTitle,
  assetSectionsByTab,
  diagnosisAssistantName,
  fallbackWorkOrders,
  fallbackWorkOrdersForUser,
  mergeAssetDetail,
  metricValue,
  roleLabels,
  riskRank,
  supervisorAssistantName,
  technicianAssistantName,
  type AppView,
  type AssetTab,
} from './appModel'
import {
  canAccessAppView,
  homeViewForRole,
  navigationForRole,
  navigationItemForView,
  roleUiProfiles,
  type NavigationIcon,
} from './navigation'
import {
  assistantTurnId,
  scrollStreamToBottom,
  usePinnedStreamScroll,
  type AssistantTurn,
} from './assistantContent'
import { hasWorkOrderMaterialBlocker, workOrderStartBlockReason, workOrderStatusLabel } from './workOrderStatus'
import { Metric } from './sharedComponents'
import { AuthLoadingRoute, ApiOnlyRoute, LoginRoute } from './routes/Auth'
import { DashboardRoute } from './routes/Dashboard'
import { AssetsRoute } from './routes/Assets'
import { AssetDetailRoute } from './routes/AssetDetail'
import { WorkOrdersRoute, type WorkOrderPlanningUpdate } from './routes/WorkOrders'
import { IngestionRoute } from './routes/Ingestion'
import { LearningReviewRoute } from './routes/LearningReview'
import { RcaWorkspace } from './routes/RcaWorkspace'
import { UsersRoute } from './routes/Users'
import { ReportsRoute } from './routes/Reports'

const WORK_EXECUTION_NEO_STREAM_TIMEOUT_MS = 60_000
const TOAST_TIMEOUT_MS = 4_500
const PLANNING_TABLE_PAGE_SIZE = 5

type MaintenanceInsightSectionKey = 'summary' | 'structuredReports' | 'abnormalAlerts' | 'decisionSummaries' | 'logEntries'

type MaintenanceInsightLoading = Record<MaintenanceInsightSectionKey, boolean>

type ToastVariant = 'success' | 'error' | 'info'

type ToastNotification = {
  id: string
  message: string
  variant: ToastVariant
}

type AdminTab = 'ingestion' | 'users' | 'learning'
type LearningLoadingAction =
  | 'activateEmbeddingProfile'
  | 'createSnapshot'
  | 'deployAdapter'
  | 'previewArtifactCleanup'
  | 'previewRagMigration'
  | 'promoteAdapter'
  | 'queuePeftTuning'
  | 'refreshExamples'
  | 'registerAdapter'
  | 'reindexRag'
  | 'rollbackAdapter'
  | 'runEvaluation'
  | 'runRagMigration'

export type LearningLoadingState = Partial<Record<LearningLoadingAction, boolean>>

function toDatetimeLocalValue(value: string) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const localDate = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return localDate.toISOString().slice(0, 16)
}

function fromDatetimeLocalValue(value: string) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toISOString()
}

const emptyMaintenanceInsightLoading: MaintenanceInsightLoading = {
  summary: false,
  structuredReports: false,
  abnormalAlerts: false,
  decisionSummaries: false,
  logEntries: false,
}

function toastVariantForMessage(message: string): ToastVariant {
  const lower = message.toLowerCase()
  if (
    lower.includes('could not') ||
    lower.includes('failed') ||
    lower.includes('rejected') ||
    lower.includes('invalid') ||
    lower.includes('permission') ||
    lower.includes('resolve ') ||
    lower.includes('select ') ||
    lower.includes('ended before') ||
    lower.includes('unavailable')
  ) {
    return 'error'
  }
  if (
    lower.includes('streaming') ||
    lower.includes('judging') ||
    lower.includes('previewed') ||
    lower.includes('queued') ||
    lower.includes('requested')
  ) {
    return 'info'
  }
  return 'success'
}

function ToastStack({
  dismissToast,
  toasts,
}: {
  dismissToast: (toastId: string) => void
  toasts: ToastNotification[]
}) {
  if (!toasts.length) return null
  return (
    <div className="toastStack" aria-label="Application notifications">
      {toasts.map((toast) => {
        const Icon = toast.variant === 'success' ? CheckCircle2 : toast.variant === 'error' ? XCircle : Info
        return (
          <article
            aria-live={toast.variant === 'error' ? 'assertive' : 'polite'}
            className={`toastMessage ${toast.variant}`}
            key={toast.id}
            role={toast.variant === 'error' ? 'alert' : 'status'}
          >
            <Icon size={18} />
            <p>{toast.message}</p>
            <button type="button" onClick={() => dismissToast(toast.id)} aria-label="Dismiss notification">
              <X size={15} />
            </button>
          </article>
        )
      })}
    </div>
  )
}

function WorkOrderReviewDialog({
  assets,
  draft,
  onCancel,
  onChange,
  onSubmit,
  submitting,
  technicians,
}: {
  assets: AssetListItem[]
  draft: WorkOrderCreateRequest
  onCancel: () => void
  onChange: (updates: Partial<WorkOrderCreateRequest>) => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  submitting: boolean
  technicians: AuthUser[]
}) {
  return (
    <div className="modalOverlay" role="presentation">
      <form className="modalPanel workOrderReviewDialog" role="dialog" aria-modal="true" aria-labelledby="work-order-review-title" onSubmit={onSubmit}>
        <div className="sectionHeader compactHeader">
          <Briefcase size={18} />
          <h2 id="work-order-review-title">Review Work Order</h2>
        </div>
        <p className="modalContext">
          Verify the prefilled details before submitting.
          <small>{draft.equipment_id} · Priority {draft.priority} · {draft.work_type}</small>
        </p>
        <div className="workOrderReviewGrid">
          <label className="field">
            <span>Equipment</span>
            <select value={draft.equipment_id} onChange={(event) => onChange({ equipment_id: event.target.value })} required>
              {!assets.some((asset) => asset.id === draft.equipment_id) && (
                <option value={draft.equipment_id}>{draft.equipment_id}</option>
              )}
              {assets.map((asset) => (
                <option key={asset.id} value={asset.id}>
                  {asset.id} - {asset.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Priority</span>
            <input
              min="1"
              max="5"
              type="number"
              value={draft.priority}
              onChange={(event) => onChange({ priority: Number(event.target.value) || 1 })}
              required
            />
          </label>
          <label className="field workOrderWideField">
            <span>Work order title</span>
            <input value={draft.title} onChange={(event) => onChange({ title: event.target.value })} required />
          </label>
          <label className="field">
            <span>Work type</span>
            <input value={draft.work_type} onChange={(event) => onChange({ work_type: event.target.value })} required />
          </label>
          <label className="field">
            <span>Failure class</span>
            <input value={draft.failure_class} onChange={(event) => onChange({ failure_class: event.target.value })} required />
          </label>
          <label className="field">
            <span>Problem code</span>
            <input value={draft.problem_code} onChange={(event) => onChange({ problem_code: event.target.value })} required />
          </label>
          <label className="field">
            <span>Due date</span>
            <input
              type="datetime-local"
              value={toDatetimeLocalValue(draft.due_date)}
              onChange={(event) => onChange({ due_date: fromDatetimeLocalValue(event.target.value) })}
              required
            />
          </label>
          <label className="field">
            <span>Assigned to</span>
            <select value={draft.assigned_to} onChange={(event) => onChange({ assigned_to: event.target.value })}>
              <option value="">Unassigned</option>
              {draft.assigned_to && !technicians.some((technician) => technician.display_name === draft.assigned_to) && (
                <option value={draft.assigned_to}>{draft.assigned_to}</option>
              )}
              {technicians.map((technician) => (
                <option key={technician.id} value={technician.display_name}>
                  {technician.display_name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Supervisor</span>
            <input value={draft.supervisor} onChange={(event) => onChange({ supervisor: event.target.value })} required />
          </label>
          <label className="field workOrderWideField">
            <span>Classification</span>
            <input value={draft.classification} onChange={(event) => onChange({ classification: event.target.value })} required />
          </label>
          <label className="field workOrderWideField">
            <span>Description</span>
            <textarea value={draft.description} onChange={(event) => onChange({ description: event.target.value })} required />
          </label>
          <label className="field workOrderWideField">
            <span>Recommended action</span>
            <textarea value={draft.recommended_action} onChange={(event) => onChange({ recommended_action: event.target.value })} required />
          </label>
          <label className="field workOrderWideField">
            <span>AI summary</span>
            <textarea value={draft.ai_summary ?? ''} onChange={(event) => onChange({ ai_summary: event.target.value })} />
          </label>
          <label className="checkboxField workOrderWideField">
            <input
              checked={Boolean(draft.follow_up_required)}
              type="checkbox"
              onChange={(event) => onChange({ follow_up_required: event.target.checked })}
            />
            <span>Follow-up required</span>
          </label>
        </div>
        <div className="modalActions">
          <button className="outlineButton" type="button" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
          <button className="iconTextButton" type="submit" disabled={submitting}>
            {submitting ? <span className="loadingSpinner" aria-hidden="true" /> : <Briefcase size={16} />}
            {submitting ? 'Creating...' : 'Confirm and submit'}
          </button>
        </div>
      </form>
    </div>
  )
}

function markdownBullets(items: string[]) {
  return items.length > 0 ? items.map((item) => `- ${item}`) : ['- None recorded.']
}

function buildMaintenanceInsightsMarkdown({
  abnormalAlertReports,
  decisionSummaries,
  logEntries,
  structuredReports,
  summary,
}: {
  abnormalAlertReports: AbnormalAlertReport[]
  decisionSummaries: MaintenanceDecisionSummary[]
  logEntries: DigitalMaintenanceLogEntry[]
  structuredReports: StructuredMaintenanceReport[]
  summary: MaintenanceInsightReportSummary | null
}) {
  const generatedAt = summary?.generated_at ?? new Date().toISOString()
  const lines = [
    '# Structured Maintenance Insights',
    '',
    `Generated: ${generatedAt}`,
    `Assets reviewed: ${summary?.assets_reviewed ?? structuredReports.length}`,
    '',
    '## Maintenance Reports',
  ]

  for (const report of structuredReports) {
    lines.push(
      '',
      `### ${report.equipment_name} (${report.equipment_id})`,
      `- Risk: ${report.risk_level}`,
      `- Health: ${report.health_score}%`,
      `- Failure probability: ${Math.round(report.failure_probability * 100)}%`,
      `- Estimated RUL: ${report.remaining_useful_life_days} days`,
      `- Summary: ${report.report_summary}`,
      '',
      'Probable causes:',
      ...markdownBullets(report.probable_causes),
      'Immediate actions:',
      ...markdownBullets(report.immediate_actions),
      'Planned actions:',
      ...markdownBullets(report.planned_actions),
      'Evidence:',
      ...markdownBullets(report.evidence),
    )
  }

  lines.push('', '## Abnormal Alert Reports')
  for (const report of abnormalAlertReports) {
    lines.push(
      '',
      `### ${report.alert_id}: ${report.equipment_name}`,
      `- Signal: ${report.signal}`,
      `- Severity: ${report.severity}`,
      `- Value: ${report.value}${report.unit}; threshold ${report.threshold}${report.unit}`,
      `- Threshold delta: ${report.threshold_delta}${report.unit}`,
      `- Decision: ${report.decision}`,
      'Recommended actions:',
      ...markdownBullets(report.recommended_actions),
    )
  }

  lines.push('', '## Decision Summaries')
  for (const decisionSummary of decisionSummaries) {
    lines.push(
      '',
      `### ${decisionSummary.title}`,
      `Audience: ${decisionSummary.audience}`,
      '',
      decisionSummary.summary,
      '',
      'Decisions:',
      ...markdownBullets(decisionSummary.decisions),
      'Risks:',
      ...markdownBullets(decisionSummary.risks),
      'Next actions:',
      ...markdownBullets(decisionSummary.next_actions),
    )
  }

  lines.push('', '## Equipment Digital Maintenance Log Entries')
  for (const entry of logEntries) {
    lines.push(
      '',
      `### ${entry.equipment_name} (${entry.equipment_id})`,
      `- Entry type: ${entry.entry_type}`,
      `- Timestamp: ${entry.timestamp}`,
      '',
      entry.content,
      '',
      'Source IDs:',
      ...markdownBullets(entry.source_ids),
    )
  }

  return `${lines.join('\n')}\n`
}

function isAbortError(error: unknown) {
  return Boolean(error && typeof error === 'object' && 'name' in error && error.name === 'AbortError')
}

function navigationIcon(icon: NavigationIcon) {
  switch (icon) {
    case 'assets':
      return <Activity size={17} />
    case 'execution':
      return <Briefcase size={17} />
    case 'planning':
      return <CalendarClock size={17} />
    case 'reports':
      return <FileText size={17} />
    case 'reliability':
      return <Gauge size={17} />
    case 'learning':
      return <Sparkles size={17} />
    case 'admin':
      return <Users size={17} />
    case 'command':
    default:
      return <ClipboardList size={17} />
  }
}

function technicianInitialContextPrompt(workOrder: WorkOrder, userName?: string) {
  const statusLabel = workOrderStatusLabel(workOrder.status)
  const materialBlockReason = workOrderStartBlockReason(workOrder)
  const nameInstruction = userName ? `Address ${userName} by name, not by role.` : 'Address the signed-in technician by name, not by role.'
  if (materialBlockReason) {
    return [
      nameInstruction,
      'Open Work Execution with a prioritized technician action list.',
      `Top assigned item: ${workOrder.id} ${workOrder.title}.`,
      `Current status is ${statusLabel}, and field execution is blocked by material availability.`,
      `Material blocker: ${materialBlockReason}.`,
      'Return a named lead sentence and a concise Markdown recommendation section, up to 10 lines. Use P1/P2 priority-labeled blocks, not ordered Markdown lists. Each P1/P2 item must include the work order ID, why it matters, and the next permissible technician action. Do not start field execution while blocked.',
    ].join(' ')
  }
  return [
    nameInstruction,
    'Open Work Execution with a prioritized technician action list.',
    `Top assigned item: ${workOrder.id} ${workOrder.title}.`,
    `Current status is ${statusLabel}.`,
    'Use the work order, material plan, asset evidence, and approved learning notes to rank what the technician should focus on first.',
    'Return a named lead sentence and a concise Markdown recommendation section, up to 10 lines. Use P1/P2 priority-labeled blocks, not ordered Markdown lists. Each P1/P2 item must include the work order ID, why it matters, and the next technician action.',
  ].join(' ')
}

function supervisorQueueNameForPrompt(prompt: string) {
  const lowered = prompt.toLowerCase()
  if (['approval', 'approve', 'waiting approval', 'waiting for approval', 'pending approval', 'wappr'].some((term) => lowered.includes(term))) {
    return 'waiting_approval'
  }
  if (['material', 'blocked', 'procurement', 'spare'].some((term) => lowered.includes(term))) {
    return 'material_blockers'
  }
  if (['follow-up', 'follow up', 'followup'].some((term) => lowered.includes(term))) {
    return 'follow_up'
  }
  return 'all_work'
}

function supervisorApprovalWorkOrderId(prompt: string) {
  if (/\b(?:do not|don't|dont|not)\s+approve\b/i.test(prompt)) return null
  const match = prompt.match(/\bapprove\b[\s\S]{0,48}\b(WO-\d+)\b/i)
  return match?.[1]?.toUpperCase() ?? null
}

function supervisorInitialContextPrompt(workOrder: WorkOrder | undefined, workOrders: WorkOrder[], userName?: string) {
  const approvals = workOrders.filter((item) => item.status === 'WAPPR')
  const followUps = workOrders.filter((item) => item.follow_up_required)
  const materialBlocked = workOrders.filter((item) => (
    ['blocked', 'waiting_procurement', 'reorder_requested'].includes(item.material_blocker_status)
    && !['COMP', 'CLOSE'].includes(item.status)
  ))
  const selected = workOrder
    ? `Selected work order: ${workOrder.id} ${workOrder.title}, status ${workOrderStatusLabel(workOrder.status)}.`
    : 'No selected work order.'
  return [
    userName ? `Address ${userName} by name, not by role.` : 'Address the signed-in supervisor by name, not by role.',
    'Open supervisor Work Execution with a prioritized action list.',
    selected,
    `Queue context: ${approvals.length} waiting approval, ${followUps.length} follow-up, ${materialBlocked.length} material-blocked.`,
    'Rank waiting approval, material blockers, follow-ups, and urgent open work. Return a named lead sentence and a concise Markdown recommendation section, up to 10 lines. Use P1/P2/P3 priority-labeled blocks, not ordered Markdown lists. Each P1/P2/P3 item must include a work order ID, why it needs focus, and the next supervisor decision.',
  ].join(' ')
}

function supervisorContextKey(workOrder: WorkOrder | undefined, workOrders: WorkOrder[], userId?: string) {
  const approvals = workOrders.filter((item) => item.status === 'WAPPR').map((item) => item.id).join('|')
  const followUps = workOrders.filter((item) => item.follow_up_required).map((item) => item.id).join('|')
  const materialBlocked = workOrders
    .filter((item) => ['blocked', 'waiting_procurement', 'reorder_requested'].includes(item.material_blocker_status))
    .map((item) => item.id)
    .join('|')
  return [userId ?? 'anonymous', workOrder?.id ?? 'none', approvals, followUps, materialBlocked].join('::')
}

function assistantFinalMarkdown(response: Record<string, unknown>) {
  const markdown = response.markdown
  return typeof markdown === 'string' && markdown.trim() ? markdown : ''
}

function technicianTimeoutFallbackResponse(workOrder: WorkOrder, _prompt: string, timeoutMs: number): TechnicianAssistantResponse {
  const nextPrompt = `Sorry, ${technicianAssistantName} could not get a live LLM response within ${Math.round(timeoutMs / 1000)} seconds. Please retry after confirming the LLM service is responding.`
  return {
    work_order_id: workOrder.id,
    next_prompt: nextPrompt,
    live_directions: [],
    recommendations: [],
    safety_reminders: [],
    suggested_problem_code: workOrder.problem_code,
    suggested_failure_class: workOrder.failure_class,
    completion_summary: `${workOrder.id} Trinity query timed out before a live LLM answer was received.`,
    evidence: [],
    used_live_provider: false,
    provider: 'timeout_fallback',
  }
}

function supervisorTimeoutFallbackResponse(
  _prompt: string,
  workOrders: WorkOrder[],
  _selectedWorkOrder: WorkOrder | undefined,
  timeoutMs: number,
): SupervisorAssistantResponse {
  return {
    summary: `Sorry, ${supervisorAssistantName} could not get a live LLM response within ${Math.round(timeoutMs / 1000)} seconds. Please retry after confirming the LLM service is responding.`,
    follow_up_actions: [],
    risks: [],
    draft_work_order: null,
    referenced_work_orders: workOrders.map((item) => item.id),
    used_live_provider: false,
    provider: 'timeout_fallback',
  }
}

function technicianContextKey(workOrder: WorkOrder, userId?: string) {
  const spareState = workOrder.spare_reservations
    .map((spare) => [
      spare.spare_id,
      spare.reserved_qty,
      spare.available_qty,
      spare.blocker_status,
      spare.expected_available_date,
      spare.substitute_name,
    ].join(':'))
    .join('|')
  return [
    userId ?? 'anonymous',
    workOrder.id,
    workOrder.material_readiness,
    workOrder.material_blocker_status,
    workOrder.material_blocker_note,
    spareState,
  ].join('::')
}

export function App() {
  const [session, setSession] = useState<AuthSession | null>(() => api.restoreSession())
  const [authReady, setAuthReady] = useState(false)
  const [loginEmail, setLoginEmail] = useState('admin@plant.local')
  const [loginPassword, setLoginPassword] = useState('DemoPass123!')
  const [authMessage, setAuthMessage] = useState('')
  const [dashboard, setDashboard] = useState<DashboardSummary>(fallbackDashboard)
  const [assets, setAssets] = useState<AssetListItem[]>([])
  const [assetDetail, setAssetDetail] = useState<AssetDetail | null>(null)
  const [assetDetailLoading, setAssetDetailLoading] = useState(false)
  const [assetLoadedSections, setAssetLoadedSections] = useState<AssetDetailSection[]>([])
  const [assetSectionLoading, setAssetSectionLoading] = useState<Partial<Record<AssetDetailSection, boolean>>>({})
  const [assetReliabilityPrediction, setAssetReliabilityPrediction] = useState<PredictionResponse | null>(null)
  const [assetReliabilityText, setAssetReliabilityText] = useState('')
  const [assetReliabilityLoading, setAssetReliabilityLoading] = useState(false)
  const [assetReliabilityProvider, setAssetReliabilityProvider] = useState('')
  const [assetReliabilityUsedLive, setAssetReliabilityUsedLive] = useState(false)
  const [assetReliabilityMessage, setAssetReliabilityMessage] = useState('')
  const [assetReliabilityStreamAsset, setAssetReliabilityStreamAsset] = useState('')
  const [assetMessage, setAssetMessage] = useState('')
  const [activeView, setActiveView] = useState<AppView>('commandCenter')
  const [activeAdminTab, setActiveAdminTab] = useState<AdminTab>('ingestion')
  const [selectedEquipment, setSelectedEquipment] = useState('RM-DRIVE-01')
  const [assetTab, setAssetTab] = useState<AssetTab>('summary')
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [diagnosisLoading, setDiagnosisLoading] = useState(false)
  const [diagnosisStreaming, setDiagnosisStreaming] = useState(false)
  const [diagnosisStreamText, setDiagnosisStreamText] = useState('')
  const [diagnosisProvider, setDiagnosisProvider] = useState('')
  const [diagnosisUsedLive, setDiagnosisUsedLive] = useState(false)
  const [diagnosisMessage, setDiagnosisMessage] = useState('')
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>(fallbackWorkOrders)
  const [planningBacklogPage, setPlanningBacklogPage] = useState<PaginatedResponse<WorkOrder>>({
    items: fallbackWorkOrders.filter((item) => !['COMP', 'CLOSE'].includes(item.status)).slice(0, PLANNING_TABLE_PAGE_SIZE),
    total: fallbackWorkOrders.filter((item) => !['COMP', 'CLOSE'].includes(item.status)).length,
    limit: PLANNING_TABLE_PAGE_SIZE,
    offset: 0,
  })
  const [selectedWorkOrderId, setSelectedWorkOrderId] = useState('WO-8304')
  const [workOrderMessage, setWorkOrderMessage] = useState('')
  const [workOrderDraft, setWorkOrderDraft] = useState<WorkOrderCreateRequest | null>(null)
  const [workOrderSubmitting, setWorkOrderSubmitting] = useState(false)
  const [pmTemplates, setPmTemplates] = useState<PmTemplate[]>([])
  const [pmPlans, setPmPlans] = useState<PmPlan[]>([])
  const [pmPlanTablePage, setPmPlanTablePage] = useState<PaginatedResponse<PmPlan>>({
    items: [],
    total: 0,
    limit: PLANNING_TABLE_PAGE_SIZE,
    offset: 0,
  })
  const [pmPlanLoading, setPmPlanLoading] = useState(false)
  const [pmPlanMessage, setPmPlanMessage] = useState('')
  const [pmPlanStreamText, setPmPlanStreamText] = useState('')
  const [technicianObservation, setTechnicianObservation] = useState('There are hotspots and looseness around the checked connections.')
  const [technicianAssistant, setTechnicianAssistant] = useState<TechnicianAssistantResponse | null>(null)
  const [technicianLoading, setTechnicianLoading] = useState(false)
  const [technicianStreaming, setTechnicianStreaming] = useState(false)
  const [technicianChat, setTechnicianChat] = useState<AssistantTurn[]>([])
  const [technicianSessionId, setTechnicianSessionId] = useState<string | null>(null)
  const [supervisorQuestion, setSupervisorQuestion] = useState('Summarize follow-up actions for completed work orders.')
  const [supervisorAssistant, setSupervisorAssistant] = useState<SupervisorAssistantResponse | null>(null)
  const [supervisorLoading, setSupervisorLoading] = useState(false)
  const [supervisorStreaming, setSupervisorStreaming] = useState(false)
  const [supervisorChat, setSupervisorChat] = useState<AssistantTurn[]>([
  ])
  const [supervisorSessionId, setSupervisorSessionId] = useState<string | null>(null)
  const [neoQuestion, setNeoQuestion] = useState('Show work orders needing follow-up')
  const [neoTable, setNeoTable] = useState<NeoTable | null>(null)
  const [neoLoading, setNeoLoading] = useState(false)
  const [neoStreaming, setNeoStreaming] = useState(false)
  const [neoMessages, setNeoMessages] = useState<AssistantTurn[]>([
  ])
  const [neoSessionId, setNeoSessionId] = useState<string | null>(null)
  const [apiState, setApiState] = useState<'connected' | 'fallback'>('fallback')
  const [ingestSourceType, setIngestSourceType] = useState('sop')
  const [ingestTitle, setIngestTitle] = useState('')
  const [ingestFile, setIngestFile] = useState<File | null>(null)
  const [jsonMode, setJsonMode] = useState<'documents' | 'records'>('documents')
  const [jsonPayload, setJsonPayload] = useState('')
  const [ingestionMessage, setIngestionMessage] = useState('')
  const [fileIngestionLoading, setFileIngestionLoading] = useState(false)
  const [jsonIngestionLoading, setJsonIngestionLoading] = useState(false)
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus | null>(null)
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const [feedbackRootCause, setFeedbackRootCause] = useState('')
  const [feedbackActionTaken, setFeedbackActionTaken] = useState('')
  const [feedbackOutcome, setFeedbackOutcome] = useState('')
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [reportMessage, setReportMessage] = useState('')
  const [maintenanceInsightSummary, setMaintenanceInsightSummary] = useState<MaintenanceInsightReportSummary | null>(null)
  const [structuredReports, setStructuredReports] = useState<StructuredMaintenanceReport[]>([])
  const [abnormalAlertReports, setAbnormalAlertReports] = useState<AbnormalAlertReport[]>([])
  const [decisionSummaries, setDecisionSummaries] = useState<MaintenanceDecisionSummary[]>([])
  const [maintenanceLogEntries, setMaintenanceLogEntries] = useState<DigitalMaintenanceLogEntry[]>([])
  const [maintenanceInsightsLoading, setMaintenanceInsightsLoading] = useState<MaintenanceInsightLoading>(emptyMaintenanceInsightLoading)
  const [maintenanceInsightsMessage, setMaintenanceInsightsMessage] = useState('')
  const [maintenanceInsightsExporting, setMaintenanceInsightsExporting] = useState(false)
  const [users, setUsers] = useState<AuthUser[]>([])
  const [technicians, setTechnicians] = useState<AuthUser[]>([])
  const [userMessage, setUserMessage] = useState('')
  const [learningSummary, setLearningSummary] = useState<LearningSummary | null>(null)
  const [learningExamples, setLearningExamples] = useState<LearningExample[]>([])
  const [learningDatasets, setLearningDatasets] = useState<LearningDatasetSnapshot[]>([])
  const [learningDeployments, setLearningDeployments] = useState<LearningModelDeployment[]>([])
  const [learningEmbeddingProfiles, setLearningEmbeddingProfiles] = useState<LearningEmbeddingProfile[]>([])
  const [rcaCases, setRcaCases] = useState<RcaCase[]>([])
  const [selectedRcaCaseId, setSelectedRcaCaseId] = useState('')
  const [rcaLoading, setRcaLoading] = useState(false)
  const [rcaMessage, setRcaMessage] = useState('')
  const [rcaDraftStreamText, setRcaDraftStreamText] = useState('')
  const [rcaDraftCaseId, setRcaDraftCaseId] = useState('')
  const [selectedLearningDatasetId, setSelectedLearningDatasetId] = useState('')
  const [selectedLearningModelId, setSelectedLearningModelId] = useState('')
  const [selectedLearningPromptId, setSelectedLearningPromptId] = useState('')
  const [selectedEmbeddingProfileId, setSelectedEmbeddingProfileId] = useState('')
  const [ragMigrationPreview, setRagMigrationPreview] = useState<LearningRagMigrationPlan | null>(null)
  const [ragTargetCollection, setRagTargetCollection] = useState('')
  const [artifactCleanupResult, setArtifactCleanupResult] = useState<LearningArtifactCleanupResult | null>(null)
  const [learningMessage, setLearningMessage] = useState('')
  const [learningLoading, setLearningLoading] = useState<LearningLoadingState>({})
  const [learningJudgingExampleId, setLearningJudgingExampleId] = useState<string | null>(null)
  const [learningDatasetName, setLearningDatasetName] = useState('maintenance-wizard-learning-snapshot')
  const [learningDatasetDescription, setLearningDatasetDescription] = useState('Approved examples for local LLM adapter tuning and evaluation.')
  const [adapterProvider, setAdapterProvider] = useState('openai')
  const [adapterModelName, setAdapterModelName] = useState('qwen2.5-7b-instruct-lora-candidate')
  const [adapterBaseModel, setAdapterBaseModel] = useState('qwen2.5-7b-instruct')
  const [adapterPath, setAdapterPath] = useState('')
  const [adapterNotes, setAdapterNotes] = useState('Offline PEFT adapter candidate trained from approved judge-qualified examples.')
  const [deploymentRuntimeProvider, setDeploymentRuntimeProvider] = useState('llama_cpp')
  const [deploymentBaseUrl, setDeploymentBaseUrl] = useState('http://127.0.0.1:8080/v1')
  const [peftAdapterName, setPeftAdapterName] = useState('maintenance-wizard-qwen-lora')
  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserName, setNewUserName] = useState('')
  const [newUserRole, setNewUserRole] = useState<UserRole>('operator')
  const [newUserPassword, setNewUserPassword] = useState('')
  const [resetUser, setResetUser] = useState<AuthUser | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const [toasts, setToasts] = useState<ToastNotification[]>([])
  const neoTranscriptRef = useRef<HTMLDivElement | null>(null)
  const morpheusProgressRef = useRef<HTMLDivElement | null>(null)
  const reliabilityStreamRef = useRef<HTMLDivElement | null>(null)
  const technicianInitialContextRef = useRef('')
  const supervisorInitialContextRef = useRef('')
  const previousToastMessagesRef = useRef<Record<string, string>>({})

  const currentUser = session?.user
  const {
    canAdminUsers,
    canApproveWorkOrders,
    canAssignWorkOrders,
    canCreateWorkOrders,
    canDecisionSupport: canDecision,
    canFeedback,
    canIngestion: canIngest,
    canLearningReview: canReviewLearning,
    canStreaming,
    canSupervisorAssistant,
    canTechnicianAssistant,
  } = useMemo(() => getUserPermissions(currentUser), [currentUser])
  const roleProfile = currentUser ? roleUiProfiles[currentUser.role] : null
  const navigationItems = useMemo(
    () => currentUser ? navigationForRole(currentUser.role) : [],
    [currentUser?.role],
  )
  const activeNavigationItem = navigationItemForView(activeView)

  const setLearningActionLoading = useCallback((action: LearningLoadingAction, isLoading: boolean) => {
    setLearningLoading((current) => ({ ...current, [action]: isLoading }))
  }, [])

  const dismissToast = useCallback((toastId: string) => {
    setToasts((current) => current.filter((toast) => toast.id !== toastId))
  }, [])

  const showToast = useCallback((message: string) => {
    const trimmedMessage = message.trim()
    if (!trimmedMessage) return
    const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`
    setToasts((current) => [
      { id, message: trimmedMessage, variant: toastVariantForMessage(trimmedMessage) },
      ...current.slice(0, 3),
    ])
    window.setTimeout(() => dismissToast(id), TOAST_TIMEOUT_MS)
  }, [dismissToast])

  useEffect(() => {
    const nextMessages: Record<string, string> = {
      feedbackMessage,
      ingestionMessage,
      learningMessage,
      maintenanceInsightsMessage,
      pmPlanMessage,
      rcaMessage,
      reportMessage,
      userMessage,
      workOrderMessage,
    }
    Object.entries(nextMessages).forEach(([key, message]) => {
      if (message && previousToastMessagesRef.current[key] !== message) {
        showToast(message)
      }
      previousToastMessagesRef.current[key] = message
    })
  }, [
    feedbackMessage,
    ingestionMessage,
    learningMessage,
    maintenanceInsightsMessage,
    pmPlanMessage,
    rcaMessage,
    reportMessage,
    showToast,
    userMessage,
    workOrderMessage,
  ])

  function clearSession(message = '') {
    api.setSession(null)
    setSession(null)
    setActiveView('commandCenter')
    setWorkOrders(fallbackWorkOrders)
    setPmTemplates([])
    setPmPlans([])
    setPmPlanLoading(false)
    setPmPlanMessage('')
    setPmPlanStreamText('')
    setAssets([])
    setAssetDetail(null)
    setAssetLoadedSections([])
    setAssetSectionLoading({})
    setAssetReliabilityPrediction(null)
    setAssetReliabilityText('')
    setAssetReliabilityLoading(false)
    setAssetReliabilityProvider('')
    setAssetReliabilityUsedLive(false)
    setAssetReliabilityMessage('')
    setAssetReliabilityStreamAsset('')
    setAssetMessage('')
    setRecommendation(null)
    setDiagnosisLoading(false)
    setDiagnosisStreaming(false)
    setDiagnosisStreamText('')
    setDiagnosisProvider('')
    setDiagnosisUsedLive(false)
    setDiagnosisMessage('')
    setMaintenanceInsightSummary(null)
    setStructuredReports([])
    setAbnormalAlertReports([])
    setDecisionSummaries([])
    setMaintenanceLogEntries([])
    setMaintenanceInsightsLoading({ ...emptyMaintenanceInsightLoading })
    setMaintenanceInsightsMessage('')
    setTechnicianAssistant(null)
    setTechnicianChat([])
    setTechnicianSessionId(null)
    setTechnicianLoading(false)
    setTechnicianStreaming(false)
    setSupervisorAssistant(null)
    setSupervisorChat([])
    setSupervisorSessionId(null)
    setSupervisorLoading(false)
    setSupervisorStreaming(false)
    setNeoSessionId(null)
    technicianInitialContextRef.current = ''
    supervisorInitialContextRef.current = ''
    setNeoTable(null)
    setLearningSummary(null)
    setLearningExamples([])
    setLearningDatasets([])
    setLearningDeployments([])
    setLearningEmbeddingProfiles([])
    setRcaCases([])
    setSelectedRcaCaseId('')
    setRcaLoading(false)
    setRcaMessage('')
    setSelectedEmbeddingProfileId('')
    setRagMigrationPreview(null)
    setRagTargetCollection('')
    setArtifactCleanupResult(null)
    setLearningMessage('')
    setLearningLoading({})
    setAdapterProvider('openai')
    setAdapterModelName('qwen2.5-7b-instruct-lora-candidate')
    setAdapterBaseModel('qwen2.5-7b-instruct')
    setAdapterPath('')
    setAdapterNotes('Offline PEFT adapter candidate trained from approved judge-qualified examples.')
    setDeploymentRuntimeProvider('llama_cpp')
    setDeploymentBaseUrl('http://127.0.0.1:8080/v1')
    setPeftAdapterName('maintenance-wizard-qwen-lora')
    setNeoMessages([
      {
        id: 'neo-welcome',
        role: 'assistant',
        content: 'I’m Neo. I’m checking your role-aware attention queue.',
      },
    ])
    setAuthMessage(message)
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setAuthMessage('')
    try {
      const result = await api.login(loginEmail.trim(), loginPassword)
      const nextSession = { accessToken: result.access_token, user: result.user }
      api.setSession(nextSession)
      setSession(nextSession)
      setWorkOrders(fallbackWorkOrdersForUser(result.user))
      setLoginPassword('')
      setActiveView(homeViewForRole(result.user.role))
    } catch {
      setAuthMessage('Invalid email or password')
    }
  }

  async function handleLogout() {
    void api.logout().catch(() => undefined)
    clearSession('')
  }

  function loadDashboard() {
    return api
      .dashboard()
      .then((summary) => {
        setDashboard(summary)
        setApiState('connected')
        const topAsset = [...summary.highest_risk_equipment].sort(
          (a, b) => riskRank[b.risk_level] - riskRank[a.risk_level],
        )[0]
        if (topAsset) {
          setSelectedEquipment((current) =>
            summary.highest_risk_equipment.some((item) => item.equipment.id === current)
              ? current
              : topAsset.equipment.id,
          )
        }
      })
      .catch(() => setApiState('fallback'))
  }

  function loadAssets() {
    return api
      .assets()
      .then((items) => {
        setAssets(items)
        setApiState('connected')
      })
      .catch(() => {
        setAssets([])
        setApiState('fallback')
      })
  }

  function loadAssetDetail(equipmentId: string, sections: AssetDetailSection[] = ['summary']) {
    const isSummaryLoad = sections.includes('summary')
    if (isSummaryLoad) {
      setAssetDetailLoading(true)
    } else {
      setAssetSectionLoading((current) => ({
        ...current,
        ...Object.fromEntries(sections.map((section) => [section, true])),
      }))
    }
    setAssetMessage('')
    return api
      .assetDetail(equipmentId, sections)
      .then((detail) => {
        setAssetDetail((current) => mergeAssetDetail(current, detail, sections))
        setAssetLoadedSections((current) => [...new Set([...current, ...sections])])
        setApiState('connected')
      })
      .catch(() => {
        if (isSummaryLoad) {
          setAssetDetail(null)
        } else {
          setAssetLoadedSections((current) => [...new Set([...current, ...sections])])
        }
        setApiState('fallback')
        setAssetMessage('Asset detail data could not be loaded from the API.')
      })
      .finally(() => {
        if (isSummaryLoad) {
          setAssetDetailLoading(false)
        } else {
          setAssetSectionLoading((current) => ({
            ...current,
            ...Object.fromEntries(sections.map((section) => [section, false])),
          }))
        }
      })
  }

  function loadUsers() {
    return api
      .users()
      .then((items) => setUsers(items))
      .catch(() => setUserMessage('Users could not be loaded'))
  }

  function loadLearning(options: { silent?: boolean } = {}) {
    if (!options.silent) {
      setLearningLoading({})
      setLearningMessage('')
    }
    return Promise.all([
      api.learningSummary(),
      api.learningExamplesPage({ limit: 10, offset: 0 }),
      api.learningDatasets(),
      api.learningModelDeployments().catch((): LearningModelDeployment[] => []),
      api.learningEmbeddingProfiles().catch((): LearningEmbeddingProfile[] => []),
    ])
      .then(([summary, examplesPage, datasets, deployments, embeddingProfiles]) => {
        setLearningSummary(summary)
        setLearningExamples(examplesPage.items)
        setLearningDatasets(datasets)
        setLearningDeployments(deployments)
        setLearningEmbeddingProfiles(embeddingProfiles)
        const activeProfile = embeddingProfiles.find((profile) => profile.status === 'active') ?? embeddingProfiles[0]
        if (activeProfile && !selectedEmbeddingProfileId) {
          setSelectedEmbeddingProfileId(activeProfile.id)
        }
        if (!ragTargetCollection && summary.vector_store?.collection) {
          setRagTargetCollection(summary.vector_store.collection)
        }
        const latestDataset = datasets[0] ?? summary.recent_snapshots[0]
        if (latestDataset && !selectedLearningDatasetId) {
          setSelectedLearningDatasetId(latestDataset.id)
        }
        const activeModel = summary.model_versions.find((model) => model.status === 'active') ?? summary.model_versions[0]
        if (activeModel && !selectedLearningModelId) {
          setSelectedLearningModelId(activeModel.id)
        }
        const neoPrompt = summary.prompt_versions.find((item) => item.assistant === 'neo') ?? summary.prompt_versions[0]
        if (neoPrompt && !selectedLearningPromptId) {
          setSelectedLearningPromptId(neoPrompt.id)
        }
        setApiState('connected')
      })
      .catch(() => {
        if (!options.silent) {
          setLearningMessage('Learning data could not be loaded')
        }
        setApiState('fallback')
      })
      .finally(() => {
        if (!options.silent) {
          setLearningLoading({})
        }
      })
  }

  function loadRcaCases() {
    setRcaLoading(true)
    setRcaMessage('')
    return api
      .rcaCases()
      .then((items) => {
        setRcaCases(items)
        if (items.length && !items.some((item) => item.id === selectedRcaCaseId)) {
          setSelectedRcaCaseId(items[0].id)
        }
        setApiState('connected')
      })
      .catch(() => {
        setRcaMessage('RCA cases could not be loaded')
        setApiState('fallback')
      })
      .finally(() => setRcaLoading(false))
  }

  function loadMaintenanceInsights(equipmentId?: string) {
    setMaintenanceInsightsMessage('')
    setMaintenanceInsightSummary(null)
    setStructuredReports([])
    setAbnormalAlertReports([])
    setDecisionSummaries([])
    setMaintenanceLogEntries([])
    setMaintenanceInsightsLoading({
      summary: true,
      structuredReports: true,
      abnormalAlerts: true,
      decisionSummaries: true,
      logEntries: true,
    })

    function loadSection<T>(
      section: MaintenanceInsightSectionKey,
      request: () => Promise<T>,
      update: (value: T) => void,
    ) {
      return request()
        .then((value) => {
          update(value)
          setApiState('connected')
          return true
        })
        .catch(() => {
          setMaintenanceInsightsMessage('One or more structured report sections could not be loaded')
          setApiState('fallback')
          return false
        })
        .finally(() => {
          setMaintenanceInsightsLoading((current) => ({ ...current, [section]: false }))
        })
    }

    const priorityRequests = [
      loadSection('summary', () => api.maintenanceInsightReportSummary(equipmentId), setMaintenanceInsightSummary),
      loadSection('abnormalAlerts', () => api.abnormalAlertReports(equipmentId), setAbnormalAlertReports),
    ]
    const priorityResultsPromise = Promise.all(priorityRequests)

    const detailSequence = priorityResultsPromise
      .then(() => loadSection('structuredReports', () => api.structuredMaintenanceReports(equipmentId), setStructuredReports))
      .then((structuredResult) =>
        loadSection('decisionSummaries', () => api.maintenanceDecisionSummaries(equipmentId), setDecisionSummaries).then(
          (decisionResult) => [structuredResult, decisionResult],
        ),
      )
      .then((previousResults) =>
        loadSection('logEntries', () => api.digitalMaintenanceLogEntries(equipmentId), setMaintenanceLogEntries).then(
          (logResult) => [...previousResults, logResult],
        ),
      )

    return Promise.all([priorityResultsPromise, detailSequence]).then(([priorityResults, detailResults]) => {
      const results = [...priorityResults, ...detailResults]
      if (results.every(Boolean)) {
        setApiState('connected')
      }
      return results
    })
  }

  async function refreshLearningExamples() {
    setLearningActionLoading('refreshExamples', true)
    setLearningMessage('')
    try {
      const examples = await api.refreshLearningExamples()
      const [summary, examplesPage] = await Promise.all([
        api.learningSummary(),
        api.learningExamplesPage({ limit: 10, offset: 0 }),
      ])
      setLearningExamples(examplesPage.items)
      setLearningSummary(summary)
      setLearningMessage(
        examples.length > 0
          ? `Refreshed ${examples.length} learning example${examples.length === 1 ? '' : 's'}`
          : 'Refresh completed, but no learning examples were found. Add accepted feedback, usable maintenance labels, completed work orders, closed RCA cases, ingested documents, or approved assistant interactions, then refresh again.',
      )
      setApiState('connected')
    } catch {
      setLearningMessage('Learning examples could not be refreshed')
      setApiState('fallback')
    } finally {
      setLearningActionLoading('refreshExamples', false)
    }
  }

  async function toggleLearningApproval(example: LearningExample) {
    try {
      const updated = await api.updateLearningExample(example.id, !example.approved)
      setLearningExamples((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`${updated.source_type} example ${updated.approved ? 'approved' : 'removed from approved set'}`)
    } catch {
      setLearningMessage('Learning approval could not be changed')
    }
  }

  async function judgeLearningExample(example: LearningExample) {
    setLearningJudgingExampleId(example.id)
    setLearningMessage(`Judging ${example.source_type.replace(/_/g, ' ')} example. Live LLM checks can take up to 15 seconds before falling back.`)
    try {
      const updated = await api.judgeLearningExample(example.id)
      setLearningExamples((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Judge scored ${updated.source_type} at ${Math.round(updated.judge_score * 100)}%`)
    } catch {
      setLearningMessage('Learning judge could not score the example')
    } finally {
      setLearningJudgingExampleId(null)
    }
  }

  async function createLearningSnapshot() {
    setLearningActionLoading('createSnapshot', true)
    setLearningMessage('')
    try {
      const snapshot = await api.createLearningDataset({
        name: learningDatasetName.trim() || 'maintenance-wizard-learning-snapshot',
        description: learningDatasetDescription.trim() || undefined,
        approved_only: true,
        min_judge_score: 0.65,
      })
      setLearningDatasets((items) => [snapshot, ...items])
      setSelectedLearningDatasetId(snapshot.id)
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Created dataset snapshot with ${snapshot.example_count} approved example${snapshot.example_count === 1 ? '' : 's'}`)
    } catch {
      setLearningMessage('Learning dataset snapshot could not be created')
    } finally {
      setLearningActionLoading('createSnapshot', false)
    }
  }

  async function downloadLearningSnapshot(snapshot: LearningDatasetSnapshot) {
    try {
      const content = await api.learningDatasetJsonl(snapshot.id)
      const url = URL.createObjectURL(new Blob([content], { type: 'application/jsonl' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `${snapshot.id}.jsonl`
      link.click()
      URL.revokeObjectURL(url)
      setLearningMessage(`Downloaded ${snapshot.name}`)
    } catch {
      setLearningMessage('Learning dataset download failed')
    }
  }

  async function registerLearningAdapter() {
    if (!adapterModelName.trim() || !adapterPath.trim()) {
      setLearningMessage('Enter a model name and adapter path before registering a local adapter candidate')
      return
    }
    setLearningActionLoading('registerAdapter', true)
    setLearningMessage('')
    try {
      const model = await api.registerLearningModelVersion({
        provider: adapterProvider.trim() || 'openai',
        model_name: adapterModelName.trim(),
        base_model: adapterBaseModel.trim() || undefined,
        adapter_path: adapterPath.trim() || undefined,
        status: 'candidate',
        notes: adapterNotes.trim() || undefined,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Registered adapter candidate ${model.model_name}`)
    } catch {
      setLearningMessage('Adapter candidate could not be registered')
    } finally {
      setLearningActionLoading('registerAdapter', false)
    }
  }

  async function runLearningEvaluation() {
    const dataset = learningDatasets.find((item) => item.id === selectedLearningDatasetId)
      ?? learningSummary?.recent_snapshots.find((item) => item.id === selectedLearningDatasetId)
      ?? learningDatasets[0]
      ?? learningSummary?.recent_snapshots[0]
    const model = learningSummary?.model_versions.find((item) => item.id === selectedLearningModelId)
      ?? learningSummary?.model_versions.find((item) => item.status === 'active')
      ?? learningSummary?.model_versions[0]
    const prompt = learningSummary?.prompt_versions.find((item) => item.id === selectedLearningPromptId)
      ?? learningSummary?.prompt_versions.find((item) => item.assistant === 'neo')
      ?? learningSummary?.prompt_versions[0]
    if (!dataset || !model || !prompt) {
      setLearningMessage('Create a dataset snapshot and keep model/prompt versions available before evaluation')
      return
    }
    setLearningActionLoading('runEvaluation', true)
    setLearningMessage('')
    try {
      const run = await api.runLearningEvaluation({
        dataset_id: dataset.id,
        model_version_id: model.id,
        prompt_version_id: prompt.id,
        min_quality_score: 0.7,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Evaluation ${run.passed ? 'passed' : 'needs review'} with quality ${metricValue(run.metrics.quality_score)}`)
    } catch {
      setLearningMessage('Learning evaluation could not be run')
    } finally {
      setLearningActionLoading('runEvaluation', false)
    }
  }

  async function queuePeftTuningJob() {
    const dataset = learningDatasets.find((item) => item.id === selectedLearningDatasetId)
      ?? learningSummary?.recent_snapshots.find((item) => item.id === selectedLearningDatasetId)
      ?? learningDatasets[0]
      ?? learningSummary?.recent_snapshots[0]
    const model = learningSummary?.model_versions.find((item) => item.id === selectedLearningModelId)
      ?? learningSummary?.model_versions.find((item) => item.status === 'active')
      ?? learningSummary?.model_versions[0]
    const prompt = learningSummary?.prompt_versions.find((item) => item.id === selectedLearningPromptId)
      ?? learningSummary?.prompt_versions.find((item) => item.assistant === 'neo')
      ?? learningSummary?.prompt_versions[0]
    if (!dataset || !model || !prompt) {
      setLearningMessage('Create a dataset snapshot and keep model/prompt versions available before queuing PEFT tuning')
      return
    }
    setLearningActionLoading('queuePeftTuning', true)
    setLearningMessage('')
    try {
      const job = await api.queueLearningPeftJob({
        dataset_id: dataset.id,
        model_version_id: model.id,
        prompt_version_id: prompt.id,
        adapter_name: peftAdapterName.trim() || 'maintenance-wizard-qwen-lora',
        base_model: adapterBaseModel.trim() || undefined,
        training_config: {
          method: 'lora',
          max_examples: dataset.example_count,
          source: 'learning-review',
        },
        notes: 'Production async PEFT tuning request from Learning Review.',
      })
      const summary = await api.learningSummary()
      setLearningSummary({
        ...summary,
        recent_jobs: [job, ...summary.recent_jobs.filter((item) => item.id !== job.id)],
      })
      const trainerConfigured = Boolean(learningSummary?.peft_trainer?.configured)
      setLearningMessage(
        trainerConfigured
          ? `Queued PEFT training job ${job.id} with status ${job.status}`
          : `Prepared PEFT artifact job ${job.id} with status ${job.status}; configure the PEFT trainer to train an adapter`,
      )
    } catch {
      setLearningMessage('PEFT tuning job could not be queued')
    } finally {
      setLearningActionLoading('queuePeftTuning', false)
    }
  }

  async function reindexLearningRag() {
    setLearningActionLoading('reindexRag', true)
    setLearningMessage('')
    try {
      const job = await api.reindexLearningRag({
        target_collection: ragTargetCollection.trim() || undefined,
        recreate_collection: false,
        notes: `Current-profile reindex requested from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      const chunkCount = Number(job.output_refs?.chunk_count ?? 0)
      const learningIndexResult = (job.output_refs?.learning_index_result ?? null) as Record<string, unknown> | null
      const rawLearningIndexed = Number(learningIndexResult?.indexed ?? 0)
      const learningIndexed = Number.isFinite(rawLearningIndexed) ? rawLearningIndexed : 0
      const learningEligible = Number(learningIndexResult?.eligible ?? learningIndexed)
      const learningDetail = learningIndexResult
        ? [
            ` and synced ${learningIndexed} approved learning example${learningIndexed === 1 ? '' : 's'}`,
            learningIndexResult.state ? ` (${String(learningIndexResult.state)})` : '',
            Number.isFinite(learningEligible) && learningEligible !== learningIndexed ? ` from ${learningEligible} eligible` : '',
          ].join('')
        : ''
      setLearningMessage(`Reindexed ${chunkCount} RAG chunk${chunkCount === 1 ? '' : 's'}${learningDetail} with status ${job.status}`)
    } catch {
      setLearningMessage('RAG vector reindex could not be completed')
    } finally {
      setLearningActionLoading('reindexRag', false)
    }
  }

  async function activateSelectedEmbeddingProfile() {
    if (!selectedEmbeddingProfileId) return
    setLearningActionLoading('activateEmbeddingProfile', true)
    setLearningMessage('')
    setRagMigrationPreview(null)
    try {
      const job = await api.activateLearningEmbeddingProfile(selectedEmbeddingProfileId)
      const [summary, profiles] = await Promise.all([api.learningSummary(), api.learningEmbeddingProfiles()])
      setLearningSummary(summary)
      setLearningEmbeddingProfiles(profiles)
      setLearningMessage(`Activated embedding profile with audit job ${job.id}. Preview migration before relying on RAG results.`)
    } catch {
      setLearningMessage('Embedding profile activation could not be completed')
    } finally {
      setLearningActionLoading('activateEmbeddingProfile', false)
    }
  }

  async function previewLearningRagMigration() {
    setLearningActionLoading('previewRagMigration', true)
    setLearningMessage('')
    try {
      const preview = await api.previewLearningRagMigration({
        profile_id: selectedEmbeddingProfileId || undefined,
        target_collection: ragTargetCollection.trim() || undefined,
        recreate_collection: true,
        activate_profile: true,
      })
      setRagMigrationPreview(preview)
      setRagTargetCollection(preview.target_collection)
      setLearningMessage(`Previewed RAG migration to ${preview.target_collection}`)
    } catch {
      setLearningMessage('RAG migration preview could not be completed')
    } finally {
      setLearningActionLoading('previewRagMigration', false)
    }
  }

  async function runLearningRagMigration() {
    setLearningActionLoading('runRagMigration', true)
    setLearningMessage('')
    try {
      const job = await api.migrateLearningRag({
        profile_id: selectedEmbeddingProfileId || undefined,
        target_collection: ragTargetCollection.trim() || ragMigrationPreview?.target_collection,
        recreate_collection: true,
        activate_profile: true,
        notes: `RAG migration requested from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const [summary, profiles] = await Promise.all([api.learningSummary(), api.learningEmbeddingProfiles()])
      setLearningSummary(summary)
      setLearningEmbeddingProfiles(profiles)
      setRagMigrationPreview(null)
      const chunkCount = Number(job.output_refs?.result && (job.output_refs.result as { chunk_count?: number }).chunk_count)
      setLearningMessage(`Migrated RAG vectors with ${Number.isFinite(chunkCount) ? chunkCount : 0} chunk(s); job ${job.status}`)
    } catch {
      setLearningMessage('RAG migration could not be completed')
    } finally {
      setLearningActionLoading('runRagMigration', false)
    }
  }

  function loadTechnicians() {
    return api
      .technicians()
      .then((items) => setTechnicians(items))
      .catch(() => setTechnicians([]))
  }

  function loadWorkOrders() {
    return api
      .workOrders()
      .then((items) => {
        if (!Array.isArray(items)) {
          setWorkOrders(fallbackWorkOrdersForUser(currentUser))
          return
        }
        setWorkOrders(items)
        if (items.length && !items.some((item) => item.id === selectedWorkOrderId)) {
          setSelectedWorkOrderId(items[0].id)
        }
      })
      .catch(() => setWorkOrders(fallbackWorkOrdersForUser(currentUser)))
  }

  function planningBacklogFallbackPage(offset: number, source = workOrders): PaginatedResponse<WorkOrder> {
    const openWorkOrders = source.filter((item) => !['COMP', 'CLOSE'].includes(item.status))
    return {
      items: openWorkOrders.slice(offset, offset + PLANNING_TABLE_PAGE_SIZE),
      total: openWorkOrders.length,
      limit: PLANNING_TABLE_PAGE_SIZE,
      offset,
    }
  }

  function pmPlanFallbackPage(offset: number, source = pmPlans): PaginatedResponse<PmPlan> {
    return {
      items: source.slice(offset, offset + PLANNING_TABLE_PAGE_SIZE),
      total: source.length,
      limit: PLANNING_TABLE_PAGE_SIZE,
      offset,
    }
  }

  function loadPlanningBacklogPage(offset = planningBacklogPage.offset) {
    return api
      .workOrderPlanningBoardPage({ limit: PLANNING_TABLE_PAGE_SIZE, offset })
      .then((page) => setPlanningBacklogPage(page))
      .catch(() => setPlanningBacklogPage(planningBacklogFallbackPage(offset)))
  }

  function loadPmPlanTablePage(offset = pmPlanTablePage.offset) {
    return api
      .pmPlansPage({ limit: PLANNING_TABLE_PAGE_SIZE, offset })
      .then((page) => setPmPlanTablePage(page))
      .catch(() => setPmPlanTablePage(pmPlanFallbackPage(offset)))
  }

  function loadPmPlanning() {
    setPmPlanLoading(true)
    setPmPlanMessage('')
    return Promise.all([
      api.pmTemplates().catch((): PmTemplate[] => []),
      api.pmPlans().catch((): PmPlan[] => []),
      api.pmPlansPage({ limit: PLANNING_TABLE_PAGE_SIZE, offset: 0 }).catch((): PaginatedResponse<PmPlan> | null => null),
      api.workOrderPlanningBoardPage({ limit: PLANNING_TABLE_PAGE_SIZE, offset: 0 }).catch((): PaginatedResponse<WorkOrder> | null => null),
    ])
      .then(([templates, plans, planPage, backlogPage]) => {
        setPmTemplates(templates)
        setPmPlans(plans)
        setPmPlanTablePage(planPage ?? pmPlanFallbackPage(0, plans))
        setPlanningBacklogPage(backlogPage ?? planningBacklogFallbackPage(0))
        setApiState('connected')
      })
      .catch(() => {
        setPmPlanMessage('Preventive maintenance plans could not be loaded')
        setApiState('fallback')
      })
      .finally(() => setPmPlanLoading(false))
  }

  function loadNeoWelcome() {
    setNeoMessages([])
    setNeoTable(null)
    setNeoLoading(true)
    setNeoStreaming(false)
    let messageId: string | null = null
    let streamedContent = ''
    let finalMarkdown = ''
    let streamProvider = 'openai'
    let streamUsedLiveProvider = true
    let streamRuntimeFallback = false
    let streamRuntimeFallbackReason: string | null = null
    const ensureMessage = () => {
      if (messageId) return messageId
      messageId = 'neo-welcome'
      setNeoStreaming(true)
      setNeoMessages([
        {
          id: messageId,
          role: 'assistant',
          content: '',
          provider: streamProvider,
          usedLiveProvider: streamUsedLiveProvider,
          runtimeFallback: streamRuntimeFallback,
          runtimeFallbackReason: streamRuntimeFallbackReason,
        },
      ])
      return messageId
    }
    const updateMessage = (updates: Partial<AssistantTurn>) => {
      if (!messageId) return
      setNeoMessages((turns) => turns.map((turn) => (turn.id === messageId ? { ...turn, ...updates } : turn)))
    }
    return api
      .neoWelcomeStream((event) => {
        if (event.type === 'session') {
          setNeoSessionId(event.session_id)
          return
        }
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          streamRuntimeFallback = Boolean(event.runtime_fallback)
          streamRuntimeFallbackReason = event.runtime_fallback_reason ?? null
          updateMessage({
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'token') {
          ensureMessage()
          streamedContent += event.content
          updateMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'error') {
          ensureMessage()
          updateMessage({
            content: event.message,
            provider: streamProvider || 'pydantic_ai',
            usedLiveProvider: false,
            runtimeFallback: true,
            runtimeFallbackReason: event.message,
          })
          setNeoLoading(false)
          setNeoStreaming(false)
          return
        }
        if (event.type === 'final') {
          finalMarkdown = assistantFinalMarkdown(event.response)
          if (finalMarkdown) {
            ensureMessage()
            updateMessage({ content: finalMarkdown })
          }
          return
        }
        if (event.type === 'done') {
          setNeoTable(event.response.table ?? null)
          if (event.response.action) void refreshAfterNeoAction(event.response.action)
          if (messageId) {
            updateMessage({
              content: finalMarkdown || streamedContent || event.response.answer,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
              runtimeFallback: streamRuntimeFallback,
              runtimeFallbackReason: streamRuntimeFallbackReason,
            })
          } else {
            setNeoMessages([
              {
                id: 'neo-welcome',
                role: 'assistant',
                content: finalMarkdown || event.response.answer,
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
                runtimeFallback: streamRuntimeFallback,
                runtimeFallbackReason: streamRuntimeFallbackReason,
              },
            ])
          }
        }
      }, neoSessionId)
      .then(() => {
        setApiState('connected')
      })
      .catch(() => {
        setNeoMessages([
          {
            id: 'neo-welcome-fallback',
            role: 'assistant',
            content: 'Sorry, Neo could not get a live LLM response right now. Please retry after confirming the LLM service is responding.',
            provider: 'fallback',
            usedLiveProvider: false,
            runtimeFallback: true,
          },
        ])
        setApiState('fallback')
      })
      .finally(() => {
        setNeoLoading(false)
        setNeoStreaming(false)
      })
  }

  useEffect(() => {
    api.onUnauthorized(() => clearSession('Session expired. Sign in again.'))
    const restored = api.restoreSession()
    if (!restored) {
      setAuthReady(true)
      return () => api.onUnauthorized(null)
    }
    api
      .me()
      .then((user) => {
        const nextSession = { accessToken: restored.accessToken, user }
        api.setSession(nextSession)
        setSession(nextSession)
        setWorkOrders(fallbackWorkOrdersForUser(user))
        setActiveView((current) => canAccessAppView(user.role, current) ? current : homeViewForRole(user.role))
      })
      .catch(() => clearSession('Session expired. Sign in again.'))
      .finally(() => setAuthReady(true))
    return () => api.onUnauthorized(null)
  }, [])

  useEffect(() => {
    if (!authReady || !session || session.user.role === 'iot_service') return
    loadDashboard()
    loadAssets()
    loadWorkOrders()
    loadNeoWelcome()
    if (canStreaming) loadStreamingStatus()
    if (canAssignWorkOrders) loadTechnicians()
  }, [authReady, session?.user.id])

  useEffect(() => {
    if (!currentUser) return
    if (!canAccessAppView(currentUser.role, activeView)) {
      setActiveView(homeViewForRole(currentUser.role))
      return
    }
    if (activeView === 'admin' && activeAdminTab === 'ingestion' && canStreaming) loadStreamingStatus()
  }, [activeAdminTab, activeView, canStreaming, currentUser?.role])

  useEffect(() => {
    if (activeView === 'admin' && activeAdminTab === 'users' && canAdminUsers) loadUsers()
  }, [activeAdminTab, activeView, canAdminUsers])

  useEffect(() => {
    if (activeView === 'planning' && canAssignWorkOrders) {
      void loadPmPlanning()
    }
  }, [activeView, canAssignWorkOrders])

  useEffect(() => {
    if (activeView === 'reliability') {
      void loadRcaCases()
    }
  }, [activeView])

  useEffect(() => {
    if (activeView === 'reports') {
      void loadMaintenanceInsights()
    }
  }, [activeView])

  useEffect(() => {
    if (
      (activeView === 'learningReview' || (activeView === 'admin' && activeAdminTab === 'learning')) &&
      canReviewLearning
    ) {
      void loadLearning()
    }
  }, [activeAdminTab, activeView, canReviewLearning])

  useEffect(() => {
    if (!authReady || !session || activeView !== 'asset') return
    loadAssetDetail(selectedEquipment, ['summary'])
  }, [authReady, session?.user.id, activeView, selectedEquipment])

  useEffect(() => {
    if (!authReady || !session || activeView !== 'asset' || !assetDetail) return
    const unloadedSections = assetSectionsByTab[assetTab].filter(
      (section) => !assetLoadedSections.includes(section) && !assetSectionLoading[section],
    )
    if (unloadedSections.length === 0) return
    loadAssetDetail(selectedEquipment, unloadedSections)
  }, [
    activeView,
    assetTab,
    assetDetail?.profile.equipment_id,
    assetLoadedSections.join('|'),
    assetSectionLoading,
    authReady,
    selectedEquipment,
    session?.user.id,
  ])

  useEffect(() => {
    if (!authReady || !session || activeView !== 'asset' || assetTab !== 'reliability' || !assetDetail) return
    if (assetReliabilityStreamAsset === selectedEquipment) return
    let cancelled = false
    let streamedText = ''
    setAssetReliabilityPrediction(null)
    setAssetReliabilityText('')
    setAssetReliabilityProvider('')
    setAssetReliabilityUsedLive(false)
    setAssetReliabilityMessage('')
    setAssetReliabilityLoading(true)
    setAssetReliabilityStreamAsset(selectedEquipment)

    api
      .assetReliabilityPredictionStream(selectedEquipment, (event) => {
        if (cancelled) return
        if (event.type === 'meta') {
          setAssetReliabilityProvider(event.provider)
          setAssetReliabilityUsedLive(event.used_live_provider)
        }
        if (event.type === 'token') {
          streamedText += event.content
          setAssetReliabilityText(streamedText)
          scrollStreamToBottom(reliabilityStreamRef)
        }
        if (event.type === 'done') {
          setAssetReliabilityProvider(event.provider)
          setAssetReliabilityUsedLive(event.used_live_provider)
          setAssetReliabilityPrediction(event.prediction)
          setAssetReliabilityText(event.answer || streamedText)
          setAssetReliabilityLoading(false)
          scrollStreamToBottom(reliabilityStreamRef)
        }
        if (event.type === 'error') {
          setAssetReliabilityProvider(event.provider)
          setAssetReliabilityUsedLive(false)
          setAssetReliabilityMessage(event.message)
          setAssetReliabilityLoading(false)
          scrollStreamToBottom(reliabilityStreamRef)
        }
      })
      .catch(() => {
        if (cancelled) return
        setAssetReliabilityMessage('Live LLM reliability prediction could not be streamed.')
        setAssetReliabilityLoading(false)
        scrollStreamToBottom(reliabilityStreamRef)
      })

    return () => {
      cancelled = true
    }
  }, [
    activeView,
    assetTab,
    assetDetail?.profile.equipment_id,
    authReady,
    selectedEquipment,
    session?.user.id,
  ])

  usePinnedStreamScroll(
    neoTranscriptRef,
    `${neoMessages.length}:${neoMessages[neoMessages.length - 1]?.content.length ?? 0}:${neoLoading}:${neoStreaming}`,
  )
  usePinnedStreamScroll(
    morpheusProgressRef,
    `${diagnosisStreamText.length}:${diagnosisLoading}:${diagnosisStreaming}:${diagnosisMessage.length}:${recommendation?.id ?? ''}`,
  )
  usePinnedStreamScroll(
    reliabilityStreamRef,
    `${assetReliabilityText.length}:${assetReliabilityLoading}:${assetReliabilityMessage.length}:${assetReliabilityPrediction?.equipment_id ?? ''}`,
  )

  const selectedHealth = useMemo(
    () => dashboard.highest_risk_equipment.find((item) => item.equipment.id === selectedEquipment) ?? dashboard.highest_risk_equipment[0],
    [dashboard, selectedEquipment],
  )
  const selectedWorkOrder = useMemo(
    () => workOrders.find((item) => item.id === selectedWorkOrderId) ?? workOrders[0],
    [selectedWorkOrderId, workOrders],
  )
  const selectedTechnicianContextKey = useMemo(
    () => selectedWorkOrder ? technicianContextKey(selectedWorkOrder, currentUser?.id) : '',
    [currentUser?.id, selectedWorkOrder],
  )
  const selectedSupervisorContextKey = useMemo(
    () => supervisorContextKey(selectedWorkOrder, workOrders, currentUser?.id),
    [currentUser?.id, selectedWorkOrder, workOrders],
  )
  const assetWorkOrders = useMemo(
    () => assetDetail?.work_orders ?? workOrders.filter((item) => item.equipment_id === selectedEquipment),
    [assetDetail, selectedEquipment, workOrders],
  )
  const dashboardMetrics = useMemo(() => {
    const openOrders = workOrders.filter((item) => !['COMP', 'CLOSE'].includes(item.status))
    return {
      assetsAtRisk: dashboard.highest_risk_equipment.filter((item) => item.health_score < 50).length,
      overdueEmergency: openOrders.filter((item) => item.priority === 1).length,
      pmOverdue: openOrders.filter((item) => item.work_type === 'PM').length,
      equipmentPerformance: dashboard.average_health_score,
      followUps: workOrders.filter((item) => item.follow_up_required).length,
    }
  }, [dashboard, workOrders])

  useEffect(() => {
    if (!authReady || !session || activeView !== 'workExecution' || !canTechnicianAssistant || !selectedWorkOrder) return
    if (!selectedTechnicianContextKey || technicianInitialContextRef.current === selectedTechnicianContextKey) return
    technicianInitialContextRef.current = selectedTechnicianContextKey
    void loadTechnicianInitialContext(selectedWorkOrder, selectedTechnicianContextKey)
  }, [
    activeView,
    authReady,
    canTechnicianAssistant,
    selectedTechnicianContextKey,
    selectedWorkOrder,
    session,
  ])

  useEffect(() => {
    if (!authReady || !session || activeView !== 'workExecution' || !canSupervisorAssistant) return
    if (!selectedSupervisorContextKey || supervisorInitialContextRef.current === selectedSupervisorContextKey) return
    supervisorInitialContextRef.current = selectedSupervisorContextKey
    void loadSupervisorInitialContext(selectedWorkOrder, selectedSupervisorContextKey)
  }, [
    activeView,
    authReady,
    canSupervisorAssistant,
    selectedSupervisorContextKey,
    selectedWorkOrder?.id,
    session,
    workOrders,
  ])

  function openAsset(equipmentId: string) {
    setSelectedEquipment(equipmentId)
    setAssetTab('summary')
    setAssetDetail(null)
    setAssetLoadedSections([])
    setAssetSectionLoading({})
    setAssetReliabilityPrediction(null)
    setAssetReliabilityText('')
    setAssetReliabilityLoading(false)
    setAssetReliabilityProvider('')
    setAssetReliabilityUsedLive(false)
    setAssetReliabilityMessage('')
    setAssetReliabilityStreamAsset('')
    setRecommendation(null)
    setDiagnosisLoading(false)
    setDiagnosisStreaming(false)
    setDiagnosisStreamText('')
    setDiagnosisProvider('')
    setDiagnosisUsedLive(false)
    setDiagnosisMessage('')
    setActiveView('asset')
  }

  async function runDiagnosis() {
    if (diagnosisLoading) return
    const alertId = selectedHealth?.active_alerts[0]?.id
    let streamedText = ''
    let streamCompleted = false
    setDiagnosisLoading(true)
    setDiagnosisStreaming(false)
    setDiagnosisStreamText('')
    setDiagnosisProvider('openai')
    setDiagnosisUsedLive(true)
    setDiagnosisMessage('')
    try {
      await api.diagnoseStream(selectedEquipment, alertId, (event) => {
        if (event.type === 'meta') {
          setDiagnosisProvider(event.provider)
          setDiagnosisUsedLive(event.used_live_provider)
          setDiagnosisStreaming(true)
        }
        if (event.type === 'token') {
          streamedText += event.content
          setDiagnosisStreamText(streamedText)
          setDiagnosisStreaming(true)
          scrollStreamToBottom(morpheusProgressRef)
        }
        if (event.type === 'done') {
          streamCompleted = true
          setRecommendation(event.recommendation)
          setDiagnosisProvider(event.recommendation.provider)
          setDiagnosisUsedLive(event.recommendation.used_live_provider)
          setDiagnosisStreaming(false)
          setDiagnosisLoading(false)
          setApiState('connected')
          scrollStreamToBottom(morpheusProgressRef)
        }
        if (event.type === 'error') {
          streamCompleted = true
          setDiagnosisMessage(event.message)
          setDiagnosisStreaming(false)
          setDiagnosisLoading(false)
          setApiState('fallback')
          scrollStreamToBottom(morpheusProgressRef)
        }
      })
      if (!streamCompleted) {
        setDiagnosisStreaming(false)
        setDiagnosisLoading(false)
        setDiagnosisMessage(`${diagnosisAssistantName} diagnosis stream ended before the recommendation was ready.`)
        scrollStreamToBottom(morpheusProgressRef)
      }
    } catch {
      try {
        const result = await api.diagnose(selectedEquipment, alertId)
        setRecommendation(result)
        setDiagnosisProvider(result.provider)
        setDiagnosisUsedLive(result.used_live_provider)
        setApiState('connected')
      } catch {
        setApiState('fallback')
        setDiagnosisMessage(`${diagnosisAssistantName} could not retrieve a diagnosis.`)
        scrollStreamToBottom(morpheusProgressRef)
      } finally {
        setDiagnosisStreaming(false)
        setDiagnosisLoading(false)
      }
    }
  }

  async function sendNeoQuestion() {
    if (neoLoading) return
    const prompt = neoQuestion.trim() || 'Show assets'
    const history = neoMessages.map((turn) => ({ role: turn.role, content: turn.content }))
    setNeoMessages((turns) => [
      ...turns,
      { id: assistantTurnId('neo-user'), role: 'user', content: prompt },
    ])
    scrollStreamToBottom(neoTranscriptRef)
    setNeoLoading(true)
    setNeoStreaming(false)
    try {
      let assistantMessageId: string | null = null
      let streamedContent = ''
      let finalMarkdown = ''
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
      let streamRuntimeFallback = false
      let streamRuntimeFallbackReason: string | null = null

      const ensureAssistantMessage = () => {
        if (assistantMessageId) return assistantMessageId
        assistantMessageId = assistantTurnId('neo-assistant')
        setNeoStreaming(true)
        setNeoMessages((turns) => [
          ...turns,
          {
            id: assistantMessageId ?? assistantTurnId('neo-assistant'),
            role: 'assistant',
            content: '',
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          },
        ])
        scrollStreamToBottom(neoTranscriptRef)
        return assistantMessageId
      }

      const updateAssistantMessage = (updates: Partial<AssistantTurn>) => {
        if (!assistantMessageId) return
        setNeoMessages((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
        scrollStreamToBottom(neoTranscriptRef)
      }

      await api.neoChatStream(prompt, history, (event) => {
        if (event.type === 'session') {
          setNeoSessionId(event.session_id)
          return
        }
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          streamRuntimeFallback = Boolean(event.runtime_fallback)
          streamRuntimeFallbackReason = event.runtime_fallback_reason ?? null
          updateAssistantMessage({
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'token') {
          ensureAssistantMessage()
          streamedContent += event.content
          updateAssistantMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'error') {
          ensureAssistantMessage()
          updateAssistantMessage({
            content: event.message,
            provider: streamProvider || 'pydantic_ai',
            usedLiveProvider: false,
            runtimeFallback: true,
            runtimeFallbackReason: event.message,
          })
          setNeoLoading(false)
          setNeoStreaming(false)
          return
        }
        if (event.type === 'final') {
          finalMarkdown = assistantFinalMarkdown(event.response)
          if (finalMarkdown) {
            ensureAssistantMessage()
            updateAssistantMessage({ content: finalMarkdown })
          }
          return
        }
        if (event.type === 'done') {
          setNeoTable(event.response.table ?? null)
          if (event.response.action) void refreshAfterNeoAction(event.response.action)
          if (assistantMessageId) {
            const message = finalMarkdown || neoResponseMessage(event.response)
            updateAssistantMessage({
              content: message,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
              runtimeFallback: streamRuntimeFallback,
              runtimeFallbackReason: streamRuntimeFallbackReason,
            })
          } else {
            appendNeoResponse(event.response)
          }
        }
      }, neoSessionId)
      setNeoQuestion('')
    } catch {
      setNeoMessages((turns) => [
        ...turns,
        {
          id: assistantTurnId('neo-error'),
          role: 'assistant',
          content: 'Neo requires a live LLM response and could not reach the LLM service.',
          provider: 'fallback',
          usedLiveProvider: false,
          runtimeFallback: true,
        },
      ])
    } finally {
      setNeoLoading(false)
      setNeoStreaming(false)
    }
  }

  function neoResponseMessage(response: NeoChatResponse) {
    return response.answer
  }

  function refreshAfterNeoAction(action: NeoAction) {
    if (action.status !== 'completed') return
    if (action.type.includes('work_order')) {
      void loadWorkOrders()
      void loadDashboard()
      void loadAssets()
      return
    }
    if (action.type === 'manage_user' && canAdminUsers) {
      void loadUsers()
    }
  }

  function appendNeoResponse(response: NeoChatResponse) {
    const message = neoResponseMessage(response)
    setNeoMessages((turns) => [
      ...turns,
      {
        id: assistantTurnId('neo-assistant'),
        role: 'assistant',
        content: message,
        provider: response.provider,
        usedLiveProvider: response.used_live_provider,
      },
    ])
    scrollStreamToBottom(neoTranscriptRef)
  }

  async function sendFeedback(status: 'accepted' | 'rejected' | 'corrected') {
    if (!recommendation) return
    setFeedbackMessage('')
    try {
      const response = await api.feedback(recommendation.id, status, recommendation.equipment_id, {
        actualRootCause: feedbackRootCause.trim() || undefined,
        actionTaken: feedbackActionTaken.trim() || undefined,
        outcome: feedbackOutcome.trim() || undefined,
        notes: feedbackNotes.trim() || undefined,
      })
      setFeedbackMessage(`${status} feedback stored. ${response.message}`)
    } catch {
      setFeedbackMessage('Feedback could not be stored or indexed in RAG')
    }
  }

  async function downloadReport() {
    if (!recommendation) return
    setReportMessage('')
    try {
      const markdown = await api.reportMarkdown(recommendation.equipment_id)
      const blob = new Blob([markdown], { type: 'text/markdown' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${recommendation.equipment_id}-maintenance-report.md`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setReportMessage('Report downloaded')
    } catch {
      setReportMessage('Report could not be downloaded')
    }
  }

  async function downloadMaintenanceInsights(equipmentId?: string) {
    setMaintenanceInsightsExporting(true)
    setMaintenanceInsightsMessage('')
    try {
      const markdown = buildMaintenanceInsightsMarkdown({
        abnormalAlertReports,
        decisionSummaries,
        logEntries: maintenanceLogEntries,
        structuredReports,
        summary: maintenanceInsightSummary,
      })
      const blob = new Blob([markdown], { type: 'text/markdown' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${equipmentId || 'plant'}-maintenance-insights.md`
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      setMaintenanceInsightsMessage('Structured maintenance insights downloaded')
    } catch {
      setMaintenanceInsightsMessage('Structured maintenance insights could not be downloaded')
    } finally {
      setMaintenanceInsightsExporting(false)
    }
  }

  function draftWorkOrderPayload(source?: Recommendation): WorkOrderCreateRequest {
    const title = source
      ? `Follow up: ${source.probable_root_causes[0] ?? selectedHealth?.equipment.name}`
      : `Inspect ${selectedHealth?.equipment.name}`
    return {
      equipment_id: selectedEquipment,
      title,
      description: source?.diagnosis ?? selectedHealth?.notes[0] ?? 'Inspect asset condition and document findings.',
      priority: selectedHealth?.risk_level === 'critical' ? 1 : 2,
      work_type: 'CM',
      failure_class: source?.probable_root_causes.join(' ').toLowerCase().includes('thermal') ? 'ELEC' : 'MECH',
      problem_code: source?.probable_root_causes.join(' ').toLowerCase().includes('connection') ? 'LWTQCONNECT' : 'INVESTIGATE',
      classification: source?.probable_root_causes[0] ?? 'Corrective inspection',
      assigned_to: '',
      supervisor: 'Maintenance Supervisor',
      due_date: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      recommended_action: source?.immediate_actions[0] ?? selectedHealth?.notes[0] ?? 'Inspect and update work log.',
      follow_up_required: selectedHealth?.risk_level === 'critical',
      ai_summary: source?.report_summary ?? selectedHealth?.notes.join(' '),
    }
  }

  async function createWorkOrderFromContext(source?: Recommendation) {
    if (!canCreateWorkOrders) {
      setWorkOrderMessage('You do not have permission to create work orders')
      return
    }
    setWorkOrderDraft(draftWorkOrderPayload(source))
  }

  function updateWorkOrderDraft(updates: Partial<WorkOrderCreateRequest>) {
    setWorkOrderDraft((current) => current ? { ...current, ...updates } : current)
  }

  function cancelWorkOrderDraft() {
    if (workOrderSubmitting) return
    setWorkOrderDraft(null)
  }

  async function submitWorkOrderDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!workOrderDraft) return
    if (!canCreateWorkOrders) {
      setWorkOrderMessage('You do not have permission to create work orders')
      return
    }
    if (!workOrderDraft.title.trim() || !workOrderDraft.equipment_id.trim() || !workOrderDraft.due_date) {
      setWorkOrderMessage('Verify work order title, equipment, and due date before submitting')
      return
    }
    setWorkOrderSubmitting(true)
    try {
      const created = await api.createWorkOrder({
        ...workOrderDraft,
        title: workOrderDraft.title.trim(),
        equipment_id: workOrderDraft.equipment_id.trim(),
        description: workOrderDraft.description.trim(),
        recommended_action: workOrderDraft.recommended_action.trim(),
      })
      setWorkOrders((items) => [created, ...items.filter((item) => item.id !== created.id)])
      setSelectedWorkOrderId(created.id)
      setActiveView('workExecution')
      setWorkOrderDraft(null)
      setWorkOrderMessage(`Created ${created.id}`)
      void loadPlanningBacklogPage(0)
    } catch {
      setWorkOrderMessage('Work order could not be created')
    } finally {
      setWorkOrderSubmitting(false)
    }
  }

  async function draftPreventivePlan(equipmentId: string, templateId?: string) {
    setPmPlanLoading(true)
    setPmPlanMessage('')
    setPmPlanStreamText('')
    const payload = {
      equipment_id: equipmentId,
      template_id: templateId || undefined,
      convert_from_prediction: true,
      risk_threshold: 'high' as const,
      requested_focus: 'Generate proactive PM plan with monitoring thresholds and technician-ready steps.',
    }
    try {
      let streamedText = ''
      let completed = false
      await api.draftPmPlanWithMorpheusStream(payload, (event) => {
        if (event.type === 'meta') {
          setPmPlanMessage(`Morpheus is streaming PM draft content from ${event.used_live_provider ? `live ${event.provider}` : event.provider}.`)
          return
        }
        if (event.type === 'token') {
          streamedText += event.content
          setPmPlanStreamText(streamedText)
          return
        }
        if (event.type === 'done') {
          completed = true
          const response = event.response
          setPmPlans((items) => [response.plan, ...items.filter((item) => item.id !== response.plan.id)])
          setPmTemplates(response.templates.length ? response.templates : pmTemplates)
          setPmPlanMessage(`${response.message} Provider: ${response.plan.used_live_provider ? `live ${response.plan.provider}` : response.plan.provider}.`)
          setApiState('connected')
          return
        }
        if (event.type === 'error') {
          throw new Error(event.message)
        }
      })
      if (!completed) {
        setPmPlanMessage('Morpheus PM draft stream ended before the plan was ready.')
        setApiState('fallback')
      }
    } catch {
      try {
        const response = await api.draftPmPlanWithMorpheus(payload)
        setPmPlans((items) => [response.plan, ...items.filter((item) => item.id !== response.plan.id)])
        setPmTemplates(response.templates.length ? response.templates : pmTemplates)
        setPmPlanMessage(`${response.message} Provider: ${response.plan.used_live_provider ? `live ${response.plan.provider}` : response.plan.provider}.`)
        setApiState('connected')
      } catch {
        setPmPlanMessage('Morpheus could not draft the preventive maintenance plan')
        setApiState('fallback')
      }
    } finally {
      setPmPlanLoading(false)
      void loadPmPlanTablePage(0)
    }
  }

  async function convertPmPlanToWorkOrder(planId: string) {
    setPmPlanLoading(true)
    setPmPlanMessage('')
    try {
      const workOrder = await api.convertPmPlanToWorkOrder(planId)
      setWorkOrders((items) => [workOrder, ...items.filter((item) => item.id !== workOrder.id)])
      setSelectedWorkOrderId(workOrder.id)
      const plans = await api.pmPlans().catch((): PmPlan[] => [])
      setPmPlans(plans)
      void loadPmPlanTablePage(pmPlanTablePage.offset)
      void loadPlanningBacklogPage(planningBacklogPage.offset)
      setPmPlanMessage(`Converted ${planId} to planned work order ${workOrder.id}`)
      setWorkOrderMessage(`Created ${workOrder.id} from preventive maintenance plan`)
    } catch {
      setPmPlanMessage('Preventive maintenance plan could not be converted to planned work')
    } finally {
      setPmPlanLoading(false)
    }
  }

  async function createRcaCaseFromSelectedWorkOrder() {
    if (!selectedWorkOrder) {
      setRcaMessage('Select a work order before creating an RCA case')
      return
    }
    setRcaLoading(true)
    setRcaMessage('')
    try {
      const created = await api.createRcaCase({
        equipment_id: selectedWorkOrder.equipment_id,
        work_order_id: selectedWorkOrder.id,
        title: `RCA for ${selectedWorkOrder.id} ${selectedWorkOrder.title}`,
        symptoms: [
          selectedWorkOrder.description,
          selectedWorkOrder.material_blocker_note ?? '',
          selectedWorkOrder.ai_summary ?? '',
        ].filter(Boolean),
      })
      setRcaCases((items) => [created, ...items.filter((item) => item.id !== created.id)])
      setSelectedRcaCaseId(created.id)
      setRcaMessage(`Created ${created.id}`)
    } catch {
      setRcaMessage('RCA case could not be created')
    } finally {
      setRcaLoading(false)
    }
  }

  async function draftRcaCase(caseId?: string) {
    setRcaLoading(true)
    setRcaMessage('')
    setRcaDraftStreamText('')
    setRcaDraftCaseId(caseId ?? '')
    try {
      const selectedCase = rcaCases.find((item) => item.id === caseId)
      let streamedText = ''
      let completed = false
      await api.draftRcaWithMorpheusStream({
        case_id: selectedCase?.id,
        equipment_id: selectedCase?.equipment_id ?? selectedWorkOrder?.equipment_id,
        work_order_id: selectedCase?.work_order_id ?? selectedWorkOrder?.id,
        symptoms: selectedCase?.symptoms,
        question: 'Draft RCA hypotheses, evidence timeline, 5-Why, fishbone causes, corrective actions, and missing checks.',
      }, (event) => {
        if (event.type === 'meta') {
          setRcaMessage(`Morpheus is streaming RCA draft content from ${event.used_live_provider ? `live ${event.provider}` : event.provider}.`)
          return
        }
        if (event.type === 'token') {
          streamedText += event.content
          setRcaDraftStreamText(streamedText)
          return
        }
        if (event.type === 'done') {
          completed = true
          const response = event.response
          setRcaDraftCaseId(response.case.id)
          setRcaCases((items) => [response.case, ...items.filter((item) => item.id !== response.case.id)])
          setSelectedRcaCaseId(response.case.id)
          setRcaMessage(`${response.message} Provider: ${response.case.used_live_provider ? `live ${response.case.provider}` : response.case.provider}.`)
          setApiState('connected')
          return
        }
        if (event.type === 'error') {
          throw new Error(event.message)
        }
      })
      if (!completed) {
        setRcaMessage('Morpheus RCA draft stream ended before the case was ready.')
        setApiState('fallback')
      }
    } catch {
      try {
        const selectedCase = rcaCases.find((item) => item.id === caseId)
        const response = await api.draftRcaWithMorpheus({
          case_id: selectedCase?.id,
          equipment_id: selectedCase?.equipment_id ?? selectedWorkOrder?.equipment_id,
          work_order_id: selectedCase?.work_order_id ?? selectedWorkOrder?.id,
          symptoms: selectedCase?.symptoms,
          question: 'Draft RCA hypotheses, evidence timeline, 5-Why, fishbone causes, corrective actions, and missing checks.',
        })
        setRcaDraftCaseId(response.case.id)
        setRcaCases((items) => [response.case, ...items.filter((item) => item.id !== response.case.id)])
        setSelectedRcaCaseId(response.case.id)
        setRcaMessage(`${response.message} Provider: ${response.case.used_live_provider ? `live ${response.case.provider}` : response.case.provider}.`)
        setApiState('connected')
      } catch {
        setRcaMessage('Morpheus could not draft the RCA case')
        setApiState('fallback')
      }
    } finally {
      setRcaLoading(false)
    }
  }

  async function closeRcaCase(caseId: string) {
    const selectedCase = rcaCases.find((item) => item.id === caseId)
    if (!selectedCase) return
    setRcaLoading(true)
    setRcaMessage('')
    try {
      const updated = await api.updateRcaCase(caseId, {
        status: 'closed',
        closure_review: {
          reviewed_by: currentUser?.email,
          reviewed_at: new Date().toISOString(),
          accepted_for_learning: true,
          final_root_cause: selectedCase.probable_cause ?? selectedCase.hypotheses[0]?.cause ?? 'Root cause accepted from RCA review',
          recurrence_prevention: selectedCase.corrective_actions[0]?.action ?? 'Verify corrective action effectiveness after execution.',
          lessons_learned: selectedCase.morpheus_summary ?? selectedCase.problem_statement,
        },
      })
      setRcaCases((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedRcaCaseId(updated.id)
      setRcaMessage(`${updated.id} closed and accepted for learning`)
      void Promise.all([api.learningSummary(), api.learningExamplesPage({ limit: 10, offset: 0 })])
        .then(([summary, examplesPage]) => {
          setLearningSummary(summary)
          setLearningExamples(examplesPage.items)
        })
        .catch(() => undefined)
    } catch {
      setRcaMessage('RCA closure could not be saved')
    } finally {
      setRcaLoading(false)
    }
  }

  async function streamTechnicianAssistantTurn({
    workOrder,
    prompt,
    requestedStep,
    userPrompt,
    replaceTranscript = false,
    contextKey,
  }: {
    workOrder: WorkOrder
    prompt: string
    requestedStep?: string
    userPrompt?: string
    replaceTranscript?: boolean
    contextKey?: string
  }) {
    const isCurrentContext = () => !contextKey || technicianInitialContextRef.current === contextKey
    if (replaceTranscript) {
      setTechnicianChat([])
      setTechnicianAssistant(null)
    } else if (userPrompt) {
      setTechnicianChat((turns) => [
        ...turns,
        { id: assistantTurnId('technician-user'), role: 'user', content: userPrompt },
      ])
    }
    setTechnicianLoading(true)
    setTechnicianStreaming(false)
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
    const timeoutMs = WORK_EXECUTION_NEO_STREAM_TIMEOUT_MS
    let firstTokenReceived = false
    let timeoutId = controller
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : undefined
    const clearFirstTokenTimeout = () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId)
        timeoutId = undefined
      }
    }
    try {
      let assistantMessageId: string | null = null
      let streamedContent = ''
      let finalMarkdown = ''
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
      let streamRuntimeFallback = false
      let streamRuntimeFallbackReason: string | null = null

      const ensureAssistantMessage = () => {
        if (!isCurrentContext()) return null
        if (assistantMessageId) return assistantMessageId
        assistantMessageId = assistantTurnId('technician-assistant')
        setTechnicianStreaming(true)
        setTechnicianChat((turns) => [
          ...turns,
          {
            id: assistantMessageId ?? assistantTurnId('technician-assistant'),
            role: 'assistant',
            content: '',
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          },
        ])
        return assistantMessageId
      }

      const updateAssistantMessage = (updates: Partial<AssistantTurn>) => {
        if (!assistantMessageId || !isCurrentContext()) return
        setTechnicianChat((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
      }

      await api.technicianAssistStream(workOrder.id, prompt, requestedStep, (event) => {
        if (!isCurrentContext()) return
        if (event.type === 'session') {
          setTechnicianSessionId(event.session_id)
          return
        }
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          streamRuntimeFallback = Boolean(event.runtime_fallback)
          streamRuntimeFallbackReason = event.runtime_fallback_reason ?? null
          updateAssistantMessage({
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'token') {
          ensureAssistantMessage()
          if (!firstTokenReceived) {
            firstTokenReceived = true
            clearFirstTokenTimeout()
          }
          streamedContent += event.content
          updateAssistantMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'error') {
          ensureAssistantMessage()
          updateAssistantMessage({
            content: event.message,
            provider: streamProvider || 'pydantic_ai',
            usedLiveProvider: false,
            runtimeFallback: true,
            runtimeFallbackReason: event.message,
          })
          setWorkOrderMessage(event.message)
          clearFirstTokenTimeout()
          setTechnicianLoading(false)
          setTechnicianStreaming(false)
          return
        }
        if (event.type === 'final') {
          finalMarkdown = assistantFinalMarkdown(event.response)
          if (finalMarkdown) {
            ensureAssistantMessage()
            updateAssistantMessage({ content: finalMarkdown })
          }
          return
        }
        if (event.type === 'done') {
          setTechnicianAssistant(event.response)
          if (assistantMessageId) {
            updateAssistantMessage({
              content: finalMarkdown || streamedContent || event.response.next_prompt,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
              runtimeFallback: streamRuntimeFallback,
              runtimeFallbackReason: streamRuntimeFallbackReason,
            })
          } else {
            setTechnicianChat((turns) => [
              ...turns,
              {
                id: assistantTurnId('technician-assistant'),
                role: 'assistant',
                content: finalMarkdown || event.response.next_prompt,
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      }, controller?.signal, technicianSessionId)
      return true
    } catch (error) {
      if (isCurrentContext()) {
        const timeoutResponse = isAbortError(error)
          ? technicianTimeoutFallbackResponse(workOrder, prompt, timeoutMs)
          : {
              ...technicianTimeoutFallbackResponse(workOrder, prompt, timeoutMs),
              next_prompt: `Sorry, ${technicianAssistantName} could not reach the LLM service. Please retry after confirming the LLM service is responding.`,
              provider: 'fallback',
            }
        setTechnicianAssistant(timeoutResponse)
        setTechnicianChat((turns) => [
          ...turns,
          {
            id: assistantTurnId('technician-timeout-fallback'),
            role: 'assistant',
            content: timeoutResponse.next_prompt,
            provider: timeoutResponse.provider,
            usedLiveProvider: timeoutResponse.used_live_provider,
            runtimeFallback: true,
            runtimeFallbackReason: timeoutResponse.next_prompt,
          },
        ])
        const message = isAbortError(error)
          ? `${technicianAssistantName} timed out after ${Math.round(timeoutMs / 1000)} seconds and showed an LLM unavailable notice`
          : `${technicianAssistantName} could not reach the LLM service for ${workOrder.id}`
        setWorkOrderMessage(message)
      }
      return false
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId)
      if (isCurrentContext()) {
        setTechnicianLoading(false)
        setTechnicianStreaming(false)
      }
    }
  }

  async function loadTechnicianInitialContext(workOrder: WorkOrder, contextKey: string) {
    await streamTechnicianAssistantTurn({
      workOrder,
      prompt: technicianInitialContextPrompt(workOrder, currentUser?.display_name),
      requestedStep: 'initial_context',
      replaceTranscript: true,
      contextKey,
    })
  }

  async function runTechnicianAssistant() {
    if (technicianLoading) return
    if (!selectedWorkOrder) return
    const prompt = technicianObservation.trim() || 'Give me live directions for this work order.'
    const completed = await streamTechnicianAssistantTurn({
      workOrder: selectedWorkOrder,
      prompt,
      requestedStep: 'technician_observation',
      userPrompt: prompt,
    })
    if (completed) {
      setTechnicianObservation('')
      setWorkOrderMessage(`${technicianAssistantName} updated the recommended problem code and summary`)
    }
  }

  async function completeSelectedWorkOrder() {
    if (!selectedWorkOrder || !technicianAssistant) return
    try {
      const updated = await api.updateWorkOrder(selectedWorkOrder.id, {
        status: 'COMP',
        problem_code: technicianAssistant.suggested_problem_code,
        failure_class: technicianAssistant.suggested_failure_class,
        completion_summary: technicianAssistant.completion_summary,
      })
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} completed`)
    } catch {
      setWorkOrderMessage('Work order completion could not be saved')
    }
  }

  async function startWorkOrder(workOrderId: string) {
    const workOrder = workOrders.find((item) => item.id === workOrderId)
    if (workOrder && hasWorkOrderMaterialBlocker(workOrder)) {
      setSelectedWorkOrderId(workOrderId)
      setWorkOrderMessage(`Resolve material blocker before starting ${workOrderId}: ${workOrderStartBlockReason(workOrder)}`)
      return
    }
    try {
      const updated = await api.updateWorkOrder(workOrderId, { status: 'INPRG' })
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} started`)
    } catch {
      setWorkOrderMessage('Work order could not be moved to in progress')
    }
  }

  async function assignWorkOrder(workOrderId: string, assignedTo: string) {
    if (!assignedTo) return
    try {
      const updated = await api.updateWorkOrder(workOrderId, { assigned_to: assignedTo })
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} assigned to ${assignedTo}`)
      void loadPlanningBacklogPage(planningBacklogPage.offset)
    } catch {
      setWorkOrderMessage('Work order assignment could not be saved')
    }
  }

  async function planWorkOrder(workOrderId: string, payload: WorkOrderPlanningUpdate) {
    try {
      const updated = await api.updateWorkOrder(workOrderId, payload)
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} planning saved`)
      void loadPlanningBacklogPage(planningBacklogPage.offset)
    } catch {
      setWorkOrderMessage('Work order plan could not be saved')
    }
  }

  async function dispatchWorkOrder(workOrderId: string) {
    try {
      const updated = await api.updateWorkOrder(workOrderId, { planning_status: 'dispatched' })
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} dispatched`)
      void loadPlanningBacklogPage(planningBacklogPage.offset)
    } catch {
      setWorkOrderMessage('Work order dispatch could not be saved')
    }
  }

  async function approveWorkOrder(workOrderId: string) {
    try {
      const updated = await api.updateWorkOrder(workOrderId, { status: 'APPR' })
      setWorkOrders((items) => (
        items.some((item) => item.id === updated.id)
          ? items.map((item) => (item.id === updated.id ? updated : item))
          : [updated, ...items]
      ))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} approved`)
      void loadPlanningBacklogPage(planningBacklogPage.offset)
    } catch {
      setWorkOrderMessage('Work order approval could not be saved')
    }
  }

  async function runSupervisorApprovalAction(workOrderId: string) {
    const existing = workOrders.find((item) => item.id === workOrderId)
    const namePrefix = currentUser?.display_name ? `${currentUser.display_name}, ` : ''
    const appendActionResponse = (response: SupervisorAssistantResponse) => {
      setSupervisorAssistant(response)
      setSupervisorChat((turns) => [
        ...turns,
        {
          id: assistantTurnId('supervisor-action'),
          role: 'assistant',
          content: response.summary,
          provider: response.provider,
          usedLiveProvider: response.used_live_provider,
        },
      ])
    }

    if (existing && existing.status !== 'WAPPR') {
      const statusLabel = workOrderStatusLabel(existing.status)
      const response: SupervisorAssistantResponse = {
        summary: `${namePrefix}${workOrderId} is already ${statusLabel}; only work orders waiting for approval can be approved.`,
        follow_up_actions: [],
        risks: [],
        draft_work_order: null,
        referenced_work_orders: [workOrderId],
        used_live_provider: false,
        provider: 'work_order_tool',
      }
      appendActionResponse(response)
      setWorkOrderMessage(`${workOrderId} is already ${statusLabel}`)
      return
    }

    try {
      const updated = await api.updateWorkOrder(workOrderId, { status: 'APPR' })
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      const response: SupervisorAssistantResponse = {
        summary: `${namePrefix}approved ${updated.id}. It is now ${workOrderStatusLabel(updated.status)} and ready for planning, dispatch, or technician execution once materials and permits are clear.`,
        follow_up_actions: [`Review planning, assignment, and material readiness for ${updated.id}.`],
        risks: [],
        draft_work_order: null,
        referenced_work_orders: [updated.id],
        used_live_provider: false,
        provider: 'work_order_tool',
      }
      appendActionResponse(response)
      setWorkOrderMessage(`${updated.id} approved`)
    } catch {
      const response: SupervisorAssistantResponse = {
        summary: `${namePrefix}I could not approve ${workOrderId}. Confirm the work order exists, is waiting for approval, and has no approval blocker.`,
        follow_up_actions: [],
        risks: [`${workOrderId} approval was not saved.`],
        draft_work_order: null,
        referenced_work_orders: [workOrderId],
        used_live_provider: false,
        provider: 'work_order_tool',
      }
      appendActionResponse(response)
      setWorkOrderMessage(`${workOrderId} approval could not be saved`)
    }
  }

  async function loadSupervisorInitialContext(workOrder: WorkOrder | undefined, contextKey: string) {
    const isCurrentContext = () => supervisorInitialContextRef.current === contextKey
    setSupervisorAssistant(null)
    setSupervisorChat([])
    setSupervisorLoading(true)
    setSupervisorStreaming(false)
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
    const timeoutMs = WORK_EXECUTION_NEO_STREAM_TIMEOUT_MS
    let firstTokenReceived = false
    let timeoutId = controller
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : undefined
    const clearFirstTokenTimeout = () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId)
        timeoutId = undefined
      }
    }
    try {
      let assistantMessageId: string | null = null
      let streamedContent = ''
      let finalMarkdown = ''
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
      let streamRuntimeFallback = false
      let streamRuntimeFallbackReason: string | null = null
      const ensureAssistantMessage = () => {
        if (!isCurrentContext()) return null
        if (assistantMessageId) return assistantMessageId
        assistantMessageId = assistantTurnId('supervisor-assistant')
        setSupervisorStreaming(true)
        setSupervisorChat((turns) => [
          ...turns,
          {
            id: assistantMessageId ?? assistantTurnId('supervisor-assistant'),
            role: 'assistant',
            content: '',
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          },
        ])
        return assistantMessageId
      }
      const updateAssistantMessage = (updates: Partial<AssistantTurn>) => {
        if (!assistantMessageId || !isCurrentContext()) return
        setSupervisorChat((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
      }
      await api.supervisorAssistStream({
        work_order_id: workOrder?.id,
        queue_name: 'all_work',
        question: supervisorInitialContextPrompt(workOrder, workOrders, currentUser?.display_name),
        session_id: supervisorSessionId,
      }, (event) => {
        if (!isCurrentContext()) return
        if (event.type === 'session') {
          setSupervisorSessionId(event.session_id)
          return
        }
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          streamRuntimeFallback = Boolean(event.runtime_fallback)
          streamRuntimeFallbackReason = event.runtime_fallback_reason ?? null
          updateAssistantMessage({
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'token') {
          ensureAssistantMessage()
          if (!firstTokenReceived) {
            firstTokenReceived = true
            clearFirstTokenTimeout()
          }
          streamedContent += event.content
          updateAssistantMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'error') {
          ensureAssistantMessage()
          updateAssistantMessage({
            content: event.message,
            provider: streamProvider || 'pydantic_ai',
            usedLiveProvider: false,
            runtimeFallback: true,
            runtimeFallbackReason: event.message,
          })
          setWorkOrderMessage(event.message)
          clearFirstTokenTimeout()
          setSupervisorLoading(false)
          setSupervisorStreaming(false)
          return
        }
        if (event.type === 'final') {
          finalMarkdown = assistantFinalMarkdown(event.response)
          if (finalMarkdown) {
            ensureAssistantMessage()
            updateAssistantMessage({ content: finalMarkdown })
          }
          return
        }
        if (event.type === 'done') {
          setSupervisorAssistant(event.response)
          if (event.response.draft_work_order) {
            setWorkOrderDraft(event.response.draft_work_order)
          }
          if (assistantMessageId) {
            updateAssistantMessage({
              content: finalMarkdown || streamedContent || event.response.summary,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
              runtimeFallback: streamRuntimeFallback,
              runtimeFallbackReason: streamRuntimeFallbackReason,
            })
          } else {
            setSupervisorChat((turns) => [
              ...turns,
              {
                id: assistantTurnId('supervisor-assistant'),
                role: 'assistant',
                content: finalMarkdown || event.response.summary,
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      }, controller?.signal)
    } catch (error) {
      if (isCurrentContext()) {
        const fallbackResponse = supervisorTimeoutFallbackResponse('', workOrders, workOrder, timeoutMs)
        const response = isAbortError(error)
          ? fallbackResponse
          : {
              ...fallbackResponse,
              summary: `Sorry, ${supervisorAssistantName} could not reach the LLM service. Please retry after confirming the LLM service is responding.`,
              provider: 'fallback',
            }
        setSupervisorAssistant(response)
        setSupervisorChat([
          {
            id: assistantTurnId('supervisor-fallback'),
            role: 'assistant',
            content: response.summary,
            provider: response.provider,
            usedLiveProvider: response.used_live_provider,
            runtimeFallback: true,
            runtimeFallbackReason: response.summary,
          },
        ])
      }
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId)
      if (isCurrentContext()) {
        setSupervisorLoading(false)
        setSupervisorStreaming(false)
      }
    }
  }

  async function runSupervisorAssistant(workOrderId?: string) {
    if (supervisorLoading) return
    const prompt = supervisorQuestion.trim() || 'Review follow-up status.'
    setSupervisorChat((turns) => [
      ...turns,
      { id: assistantTurnId('supervisor-user'), role: 'user', content: prompt },
    ])
    setSupervisorLoading(true)
    setSupervisorStreaming(false)
    const approvalWorkOrderId = supervisorApprovalWorkOrderId(prompt)
    if (approvalWorkOrderId) {
      await runSupervisorApprovalAction(approvalWorkOrderId)
      setSupervisorQuestion('')
      setSupervisorLoading(false)
      return
    }
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
    const timeoutMs = WORK_EXECUTION_NEO_STREAM_TIMEOUT_MS
    let firstTokenReceived = false
    let timeoutId = controller
      ? window.setTimeout(() => controller.abort(), timeoutMs)
      : undefined
    const clearFirstTokenTimeout = () => {
      if (timeoutId) {
        window.clearTimeout(timeoutId)
        timeoutId = undefined
      }
    }
    try {
      let assistantMessageId: string | null = null
      let streamedContent = ''
      let finalMarkdown = ''
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
      let streamRuntimeFallback = false
      let streamRuntimeFallbackReason: string | null = null
      const payload = {
        work_order_id: workOrderId,
        queue_name: supervisorQueueNameForPrompt(prompt),
        question: prompt,
      }

      const ensureAssistantMessage = () => {
        if (assistantMessageId) return assistantMessageId
        assistantMessageId = assistantTurnId('supervisor-assistant')
        setSupervisorStreaming(true)
        setSupervisorChat((turns) => [
          ...turns,
          {
            id: assistantMessageId ?? assistantTurnId('supervisor-assistant'),
            role: 'assistant',
            content: '',
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          },
        ])
        return assistantMessageId
      }

      const updateAssistantMessage = (updates: Partial<AssistantTurn>) => {
        if (!assistantMessageId) return
        setSupervisorChat((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
      }

      await api.supervisorAssistStream({ ...payload, session_id: supervisorSessionId }, (event) => {
        if (event.type === 'session') {
          setSupervisorSessionId(event.session_id)
          return
        }
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          streamRuntimeFallback = Boolean(event.runtime_fallback)
          streamRuntimeFallbackReason = event.runtime_fallback_reason ?? null
          updateAssistantMessage({
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'token') {
          ensureAssistantMessage()
          if (!firstTokenReceived) {
            firstTokenReceived = true
            clearFirstTokenTimeout()
          }
          streamedContent += event.content
          updateAssistantMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
            runtimeFallback: streamRuntimeFallback,
            runtimeFallbackReason: streamRuntimeFallbackReason,
          })
          return
        }
        if (event.type === 'error') {
          ensureAssistantMessage()
          updateAssistantMessage({
            content: event.message,
            provider: streamProvider || 'pydantic_ai',
            usedLiveProvider: false,
            runtimeFallback: true,
            runtimeFallbackReason: event.message,
          })
          setWorkOrderMessage(event.message)
          clearFirstTokenTimeout()
          setSupervisorLoading(false)
          setSupervisorStreaming(false)
          return
        }
        if (event.type === 'final') {
          finalMarkdown = assistantFinalMarkdown(event.response)
          if (finalMarkdown) {
            ensureAssistantMessage()
            updateAssistantMessage({ content: finalMarkdown })
          }
          return
        }
        if (event.type === 'done') {
          setSupervisorAssistant(event.response)
          if (event.response.draft_work_order) {
            setWorkOrderDraft(event.response.draft_work_order)
          }
          if (assistantMessageId) {
            updateAssistantMessage({
              content: finalMarkdown || streamedContent || event.response.summary,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
              runtimeFallback: streamRuntimeFallback,
              runtimeFallbackReason: streamRuntimeFallbackReason,
            })
          } else {
            setSupervisorChat((turns) => [
              ...turns,
              {
                id: assistantTurnId('supervisor-assistant'),
                role: 'assistant',
                content: finalMarkdown || event.response.summary,
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      }, controller?.signal)
      setSupervisorQuestion('')
      setWorkOrderMessage(`${supervisorAssistantName} reviewed follow-ups`)
    } catch (error) {
      const fallbackResponse = supervisorTimeoutFallbackResponse(prompt, workOrders, selectedWorkOrder, timeoutMs)
      const response = isAbortError(error)
        ? fallbackResponse
        : {
            ...fallbackResponse,
            summary: `Sorry, ${supervisorAssistantName} could not reach the LLM service. Please retry after confirming the LLM service is responding.`,
            provider: 'fallback',
          }
      setSupervisorAssistant(response)
      setSupervisorChat((turns) => [
        ...turns,
        {
          id: assistantTurnId('supervisor-fallback'),
          role: 'assistant',
          content: response.summary,
          provider: response.provider,
          usedLiveProvider: response.used_live_provider,
          runtimeFallback: true,
          runtimeFallbackReason: response.summary,
        },
      ])
      setWorkOrderMessage(
        isAbortError(error)
          ? `${supervisorAssistantName} timed out after ${Math.round(timeoutMs / 1000)} seconds and showed an LLM unavailable notice`
          : `${supervisorAssistantName} could not reach the LLM service`,
      )
    } finally {
      if (timeoutId) window.clearTimeout(timeoutId)
      setSupervisorLoading(false)
      setSupervisorStreaming(false)
    }
  }

  function loadStreamingStatus() {
    return api
      .streamingStatus()
      .then((status) => setStreamingStatus(status))
      .catch(() => setStreamingStatus(null))
  }

  async function ingestSelectedFile() {
    if (!ingestFile) {
      setIngestionMessage('Select a file before upload')
      return
    }
    setIngestionMessage('')
    setFileIngestionLoading(true)
    try {
      const result = await api.ingestDocumentFile({
        file: ingestFile,
        sourceType: ingestSourceType,
        equipmentId: selectedEquipment,
        title: ingestTitle.trim() || undefined,
      })
      const intelligenceCount = result.intelligence?.length ?? 0
      setIngestionMessage(
        `Stored ${result.documents} document${result.documents === 1 ? '' : 's'} and extracted ${intelligenceCount} intelligence profile${intelligenceCount === 1 ? '' : 's'}`,
      )
      setIngestTitle('')
      setIngestFile(null)
      setFileIngestionLoading(false)
      void loadDashboard()
    } catch {
      setIngestionMessage('File ingestion failed')
    } finally {
      setFileIngestionLoading(false)
    }
  }

  async function ingestJsonPayload() {
    setIngestionMessage('')
    setJsonIngestionLoading(true)
    try {
      const parsed = JSON.parse(jsonPayload)
      if (jsonMode === 'documents') {
        const documents = Array.isArray(parsed) ? parsed : parsed.documents
        if (!Array.isArray(documents)) throw new Error('documents payload must be an array')
        const result = await api.ingestDocuments(documents)
        const intelligenceCount = result.intelligence?.length ?? 0
        setIngestionMessage(
          `Stored ${result.documents} document${result.documents === 1 ? '' : 's'} and extracted ${intelligenceCount} intelligence profile${intelligenceCount === 1 ? '' : 's'}`,
        )
      } else {
        const result = await api.ingestRecords(parsed)
        const total = Object.values(result.counts).reduce((sum, count) => sum + count, 0)
        setIngestionMessage(`Stored ${total} record${total === 1 ? '' : 's'}`)
      }
      setJsonPayload('')
      setJsonIngestionLoading(false)
      void loadDashboard()
    } catch {
      setIngestionMessage('JSON ingestion failed')
    } finally {
      setJsonIngestionLoading(false)
    }
  }

  async function createNewUser() {
    try {
      const user = await api.createUser({
        email: newUserEmail.trim(),
        display_name: newUserName.trim(),
        role: newUserRole,
        password: newUserPassword,
      })
      setUsers((items) => [...items, user].sort((a, b) => a.display_name.localeCompare(b.display_name)))
      setNewUserEmail('')
      setNewUserName('')
      setNewUserRole('operator')
      setNewUserPassword('')
      setUserMessage('User created')
      return true
    } catch {
      setUserMessage('User could not be created')
      return false
    }
  }

  async function toggleUserActive(user: AuthUser) {
    try {
      const updated = await api.updateUser(user.id, { is_active: !user.is_active })
      setUsers((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setUserMessage(`${updated.display_name} ${updated.is_active ? 'activated' : 'deactivated'}`)
    } catch {
      setUserMessage('User status could not be updated')
    }
  }

  function openResetPassword(user: AuthUser) {
    setResetUser(user)
    setResetPasswordValue('')
    setUserMessage('')
  }

  function closeResetPassword() {
    setResetUser(null)
    setResetPasswordValue('')
  }

  async function resetPassword() {
    if (!resetUser) return
    const password = resetPasswordValue
    if (!password) {
      setUserMessage('Enter a new password first')
      return
    }
    try {
      const updated = await api.resetUserPassword(resetUser.id, password)
      setUsers((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      closeResetPassword()
      setUserMessage(`Password reset for ${updated.display_name}`)
    } catch {
      setUserMessage('Password could not be reset')
    }
  }

  const passedEvaluationForModel = (modelId: string) =>
    learningSummary?.evaluation_runs.find((run) => run.model_version_id === modelId && run.passed)

  async function promoteLearningAdapter(model: LearningModelVersion) {
    const evaluation = passedEvaluationForModel(model.id)
    if (!evaluation) {
      setLearningMessage('Run a passing evaluation for this adapter before promotion')
      return
    }
    setLearningActionLoading('promoteAdapter', true)
    setLearningMessage('')
    try {
      const promotion = await api.promoteLearningModelVersion({
        model_version_id: model.id,
        evaluation_run_id: evaluation.id,
        runtime_provider: deploymentRuntimeProvider.trim() || undefined,
        served_model_name: model.model_name,
        base_url: deploymentBaseUrl.trim() || undefined,
        artifact_uri: model.adapter_path?.trim() || undefined,
        notes: `Promoted from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Promoted runtime-loaded adapter ${model.model_name} with audit record ${promotion.id}`)
    } catch {
      setLearningMessage('Adapter promotion requires a passing evaluation and runtime-loaded deployment')
    } finally {
      setLearningActionLoading('promoteAdapter', false)
    }
  }

  async function rollbackLearningAdapter(model: LearningModelVersion) {
    const evaluation = passedEvaluationForModel(model.id)
    if (!evaluation) {
      setLearningMessage('Run a passing evaluation for this model before rollback')
      return
    }
    setLearningActionLoading('rollbackAdapter', true)
    setLearningMessage('')
    try {
      const promotion = await api.rollbackLearningModelVersion({
        target_model_version_id: model.id,
        evaluation_run_id: evaluation.id,
        notes: `Rollback from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Rolled back to adapter version ${model.model_name} with audit record ${promotion.id}`)
    } catch {
      setLearningMessage('Adapter rollback was rejected by the evaluation or runtime deployment gate')
    } finally {
      setLearningActionLoading('rollbackAdapter', false)
    }
  }

  async function deployLearningAdapter(model: LearningModelVersion) {
    setLearningActionLoading('deployAdapter', true)
    setLearningMessage('')
    try {
      const job = await api.deployLearningModelVersion(model.id, {
        runtime_provider: deploymentRuntimeProvider.trim() || undefined,
        served_model_name: model.model_name,
        base_url: deploymentBaseUrl.trim() || undefined,
        artifact_uri: model.adapter_path?.trim() || undefined,
        notes: `Deploy requested from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const [summary, deployments] = await Promise.all([
        api.learningSummary(),
        api.learningModelDeployments().catch((): LearningModelDeployment[] => []),
      ])
      setLearningSummary(summary)
      setLearningDeployments(deployments)
      setLearningMessage(`Deployment job ${job.id} requested with status ${job.status}`)
    } catch {
      setLearningMessage('Adapter deployment could not be queued')
    } finally {
      setLearningActionLoading('deployAdapter', false)
    }
  }

  async function previewLearningArtifactCleanup() {
    setLearningActionLoading('previewArtifactCleanup', true)
    setLearningMessage('')
    try {
      const result = await api.cleanupLearningArtifacts({
        dry_run: true,
        notes: `Lifecycle preview requested from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const summary = await api.learningSummary()
      setArtifactCleanupResult(result)
      setLearningSummary(summary)
      const issueSuffix = result.errors.length ? ` ${result.errors.join(' ')}` : ''
      setLearningMessage(
        `Artifact cleanup preview found ${result.expired_count} eligible and ${result.protected_count} protected artifact(s).${issueSuffix}`,
      )
    } catch {
      setLearningMessage('Artifact cleanup preview could not be completed')
    } finally {
      setLearningActionLoading('previewArtifactCleanup', false)
    }
  }

  const openWorkOrderRoute = (workOrderId: string) => {
    setSelectedWorkOrderId(workOrderId)
    setActiveView('workExecution')
  }

  const learningReviewRoute = canReviewLearning ? (
    <LearningReviewRoute
      activateSelectedEmbeddingProfile={activateSelectedEmbeddingProfile}
      adapterBaseModel={adapterBaseModel}
      adapterModelName={adapterModelName}
      adapterNotes={adapterNotes}
      adapterPath={adapterPath}
      adapterProvider={adapterProvider}
      artifactCleanupResult={artifactCleanupResult}
      createLearningSnapshot={createLearningSnapshot}
      deployLearningAdapter={deployLearningAdapter}
      deploymentBaseUrl={deploymentBaseUrl}
      deploymentRuntimeProvider={deploymentRuntimeProvider}
      downloadLearningSnapshot={downloadLearningSnapshot}
      judgeLearningExample={judgeLearningExample}
      learningDatasetDescription={learningDatasetDescription}
      learningDatasetName={learningDatasetName}
      learningDatasets={learningDatasets}
      learningDeployments={learningDeployments}
      learningEmbeddingProfiles={learningEmbeddingProfiles}
      learningExamples={learningExamples}
      learningJudgingExampleId={learningJudgingExampleId}
      learningLoading={learningLoading}
      learningSummary={learningSummary}
      peftAdapterName={peftAdapterName}
      previewLearningArtifactCleanup={previewLearningArtifactCleanup}
      previewLearningRagMigration={previewLearningRagMigration}
      promoteLearningAdapter={promoteLearningAdapter}
      queuePeftTuningJob={queuePeftTuningJob}
      ragMigrationPreview={ragMigrationPreview}
      ragTargetCollection={ragTargetCollection}
      refreshLearningExamples={refreshLearningExamples}
      refreshLearningStatus={() => {
        void loadLearning({ silent: true })
      }}
      registerLearningAdapter={registerLearningAdapter}
      reindexLearningRag={reindexLearningRag}
      rollbackLearningAdapter={rollbackLearningAdapter}
      runLearningEvaluation={runLearningEvaluation}
      runLearningRagMigration={runLearningRagMigration}
      selectedEmbeddingProfileId={selectedEmbeddingProfileId}
      selectedLearningDatasetId={selectedLearningDatasetId}
      selectedLearningModelId={selectedLearningModelId}
      selectedLearningPromptId={selectedLearningPromptId}
      setAdapterBaseModel={setAdapterBaseModel}
      setAdapterModelName={setAdapterModelName}
      setAdapterNotes={setAdapterNotes}
      setAdapterPath={setAdapterPath}
      setAdapterProvider={setAdapterProvider}
      setDeploymentBaseUrl={setDeploymentBaseUrl}
      setDeploymentRuntimeProvider={setDeploymentRuntimeProvider}
      setLearningDatasetDescription={setLearningDatasetDescription}
      setLearningDatasetName={setLearningDatasetName}
      setPeftAdapterName={setPeftAdapterName}
      setRagTargetCollection={setRagTargetCollection}
      setSelectedEmbeddingProfileId={setSelectedEmbeddingProfileId}
      setSelectedLearningDatasetId={setSelectedLearningDatasetId}
      setSelectedLearningModelId={setSelectedLearningModelId}
      setSelectedLearningPromptId={setSelectedLearningPromptId}
      toggleLearningApproval={toggleLearningApproval}
    />
  ) : null

  const activeRoute =
    activeView === 'commandCenter' ? (
      <DashboardRoute
        approveWorkOrder={approveWorkOrder}
        canApproveWorkOrders={canApproveWorkOrders}
        canTechnicianAssistant={canTechnicianAssistant}
        dashboard={dashboard}
        dashboardMetrics={dashboardMetrics}
        neoLoading={neoLoading}
        neoMessages={neoMessages}
        neoQuestion={neoQuestion}
        neoStreaming={neoStreaming}
        neoTable={neoTable}
        neoTranscriptRef={neoTranscriptRef}
        openWorkOrder={openWorkOrderRoute}
        sendNeoQuestion={sendNeoQuestion}
        setNeoQuestion={setNeoQuestion}
        startWorkOrder={startWorkOrder}
        workOrders={workOrders}
      />
    ) : activeView === 'assets' ? (
      <AssetsRoute
        assetMessage={assetMessage}
        assets={assets}
        onOpenAsset={openAsset}
      />
    ) : activeView === 'asset' ? (
      <AssetDetailRoute
        approveWorkOrder={approveWorkOrder}
        assetDetail={assetDetail}
        assetDetailLoading={assetDetailLoading}
        assetLoadedSections={assetLoadedSections}
        assetMessage={assetMessage}
        assetReliabilityLoading={assetReliabilityLoading}
        assetReliabilityMessage={assetReliabilityMessage}
        assetReliabilityPrediction={assetReliabilityPrediction}
        assetReliabilityProvider={assetReliabilityProvider}
        assetReliabilityText={assetReliabilityText}
        assetReliabilityUsedLive={assetReliabilityUsedLive}
        assetSectionLoading={assetSectionLoading}
        assetTab={assetTab}
        assetWorkOrders={assetWorkOrders}
        canApproveWorkOrders={canApproveWorkOrders}
        canCreateWorkOrders={canCreateWorkOrders}
        canDecision={canDecision}
        canFeedback={canFeedback}
        canTechnicianAssistant={canTechnicianAssistant}
        createWorkOrderFromContext={createWorkOrderFromContext}
        diagnosisLoading={diagnosisLoading}
        diagnosisMessage={diagnosisMessage}
        diagnosisProvider={diagnosisProvider}
        diagnosisStreamText={diagnosisStreamText}
        diagnosisStreaming={diagnosisStreaming}
        diagnosisUsedLive={diagnosisUsedLive}
        downloadReport={downloadReport}
        feedbackActionTaken={feedbackActionTaken}
        feedbackMessage={feedbackMessage}
        feedbackNotes={feedbackNotes}
        feedbackOutcome={feedbackOutcome}
        feedbackRootCause={feedbackRootCause}
        morpheusProgressRef={morpheusProgressRef}
        onOpenWorkOrder={openWorkOrderRoute}
        recommendation={recommendation}
        reportMessage={reportMessage}
        reliabilityStreamRef={reliabilityStreamRef}
        runDiagnosis={runDiagnosis}
        selectedEquipment={selectedEquipment}
        sendFeedback={sendFeedback}
        setAssetTab={setAssetTab}
        setFeedbackActionTaken={setFeedbackActionTaken}
        setFeedbackNotes={setFeedbackNotes}
        setFeedbackOutcome={setFeedbackOutcome}
        setFeedbackRootCause={setFeedbackRootCause}
        startWorkOrder={startWorkOrder}
      />
    ) : activeView === 'workExecution' || activeView === 'planning' ? (
      <WorkOrdersRoute
        approveWorkOrder={approveWorkOrder}
        assignWorkOrder={assignWorkOrder}
        assets={assets}
        canApproveWorkOrders={canApproveWorkOrders}
        canAssignWorkOrders={canAssignWorkOrders}
        canSupervisorAssistant={canSupervisorAssistant}
        canTechnicianAssistant={canTechnicianAssistant}
        completeSelectedWorkOrder={completeSelectedWorkOrder}
        dispatchWorkOrder={dispatchWorkOrder}
        planWorkOrder={planWorkOrder}
        planningBacklogPage={planningBacklogPage}
        pmPlanTablePage={pmPlanTablePage}
        pmPlanLoading={pmPlanLoading}
        pmPlanStreamText={pmPlanStreamText}
        pmPlans={pmPlans}
        pmTemplates={pmTemplates}
        convertPmPlanToWorkOrder={convertPmPlanToWorkOrder}
        draftPreventivePlan={draftPreventivePlan}
        onPlanningBacklogPageChange={(offset) => void loadPlanningBacklogPage(offset)}
        onPmPlanPageChange={(offset) => void loadPmPlanTablePage(offset)}
        runSupervisorAssistant={runSupervisorAssistant}
        runTechnicianAssistant={runTechnicianAssistant}
        selectedWorkOrder={selectedWorkOrder}
        setSelectedWorkOrderId={setSelectedWorkOrderId}
        setSupervisorQuestion={setSupervisorQuestion}
        setTechnicianObservation={setTechnicianObservation}
        startWorkOrder={startWorkOrder}
        supervisorAssistant={supervisorAssistant}
        supervisorChat={supervisorChat}
        supervisorLoading={supervisorLoading}
        supervisorQuestion={supervisorQuestion}
        supervisorStreaming={supervisorStreaming}
        technicianAssistant={technicianAssistant}
        technicianChat={technicianChat}
        technicianLoading={technicianLoading}
        technicianObservation={technicianObservation}
        technicianStreaming={technicianStreaming}
        technicians={technicians}
        mode={activeView === 'planning' ? 'planning' : 'execution'}
        workOrders={workOrders}
      />
    ) : activeView === 'reports' ? (
      <ReportsRoute
        abnormalAlertReports={abnormalAlertReports}
        decisionSummaries={decisionSummaries}
        downloadMaintenanceInsights={downloadMaintenanceInsights}
        exportLoading={maintenanceInsightsExporting}
        logEntries={maintenanceLogEntries}
        loading={maintenanceInsightsLoading}
        refreshMaintenanceInsights={loadMaintenanceInsights}
        selectedEquipment={selectedEquipment}
        structuredReports={structuredReports}
        summary={maintenanceInsightSummary}
      />
    ) : activeView === 'reliability' ? (
      <section className="reliabilityRouteStack" aria-label="Reliability workspace">
        <RcaWorkspace
          closeRcaCase={closeRcaCase}
          createRcaCase={createRcaCaseFromSelectedWorkOrder}
          draftRcaCase={draftRcaCase}
          rcaCases={rcaCases}
          rcaDraftCaseId={rcaDraftCaseId}
          rcaDraftStreamText={rcaDraftStreamText}
          rcaLoading={rcaLoading}
          selectedRcaCaseId={selectedRcaCaseId}
          selectedWorkOrderId={selectedWorkOrderId}
          setSelectedRcaCaseId={setSelectedRcaCaseId}
          setSelectedWorkOrderId={setSelectedWorkOrderId}
          workOrders={workOrders}
        />
      </section>
    ) : activeView === 'learningReview' && canReviewLearning ? (
      learningReviewRoute
    ) : activeView === 'admin' && canAdminUsers ? (
      <section className="adminRouteStack" aria-label="Admin workspace">
        <div className="planningTabsShell adminTabsShell">
          <div className="planningTabRow" role="tablist" aria-label="Admin workspace tabs">
            <button
              aria-controls="admin-tab-ingestion"
              aria-selected={activeAdminTab === 'ingestion'}
              className={activeAdminTab === 'ingestion' ? 'selected' : ''}
              id="admin-tab-trigger-ingestion"
              onClick={() => setActiveAdminTab('ingestion')}
              role="tab"
              type="button"
            >
              Ingestion
            </button>
            <button
              aria-controls="admin-tab-users"
              aria-selected={activeAdminTab === 'users'}
              className={activeAdminTab === 'users' ? 'selected' : ''}
              id="admin-tab-trigger-users"
              onClick={() => setActiveAdminTab('users')}
              role="tab"
              type="button"
            >
              User management
            </button>
            <button
              aria-controls="admin-tab-learning"
              aria-selected={activeAdminTab === 'learning'}
              className={activeAdminTab === 'learning' ? 'selected' : ''}
              id="admin-tab-trigger-learning"
              onClick={() => setActiveAdminTab('learning')}
              role="tab"
              type="button"
            >
              Learning and Tuning
            </button>
          </div>
          <div
            aria-labelledby="admin-tab-trigger-ingestion"
            hidden={activeAdminTab !== 'ingestion'}
            id="admin-tab-ingestion"
            role="tabpanel"
          >
            {canIngest && (
              <IngestionRoute
                ingestJsonPayload={ingestJsonPayload}
                ingestSelectedFile={ingestSelectedFile}
                ingestSourceType={ingestSourceType}
                ingestTitle={ingestTitle}
                fileIngestionLoading={fileIngestionLoading}
                jsonIngestionLoading={jsonIngestionLoading}
                jsonMode={jsonMode}
                jsonPayload={jsonPayload}
                selectedEquipment={selectedEquipment}
                selectedHealth={selectedHealth}
                setIngestFile={setIngestFile}
                setIngestSourceType={setIngestSourceType}
                setIngestTitle={setIngestTitle}
                setJsonMode={setJsonMode}
                setJsonPayload={setJsonPayload}
                streamingStatus={streamingStatus}
              />
            )}
          </div>
          <div
            aria-labelledby="admin-tab-trigger-users"
            hidden={activeAdminTab !== 'users'}
            id="admin-tab-users"
            role="tabpanel"
          >
            <UsersRoute
              closeResetPassword={closeResetPassword}
              createNewUser={createNewUser}
              newUserEmail={newUserEmail}
              newUserName={newUserName}
              newUserPassword={newUserPassword}
              newUserRole={newUserRole}
              openResetPassword={openResetPassword}
              resetPassword={resetPassword}
              resetPasswordValue={resetPasswordValue}
              resetUser={resetUser}
              setNewUserEmail={setNewUserEmail}
              setNewUserName={setNewUserName}
              setNewUserPassword={setNewUserPassword}
              setNewUserRole={setNewUserRole}
              setResetPasswordValue={setResetPasswordValue}
              toggleUserActive={toggleUserActive}
              users={users}
            />
          </div>
          <div
            aria-labelledby="admin-tab-trigger-learning"
            hidden={activeAdminTab !== 'learning'}
            id="admin-tab-learning"
            role="tabpanel"
          >
            {learningReviewRoute}
          </div>
        </div>
      </section>
    ) : (
      <DashboardRoute
        approveWorkOrder={approveWorkOrder}
        canApproveWorkOrders={canApproveWorkOrders}
        canTechnicianAssistant={canTechnicianAssistant}
        dashboard={dashboard}
        dashboardMetrics={dashboardMetrics}
        neoLoading={neoLoading}
        neoMessages={neoMessages}
        neoQuestion={neoQuestion}
        neoStreaming={neoStreaming}
        neoTable={neoTable}
        neoTranscriptRef={neoTranscriptRef}
        openWorkOrder={openWorkOrderRoute}
        sendNeoQuestion={sendNeoQuestion}
        setNeoQuestion={setNeoQuestion}
        startWorkOrder={startWorkOrder}
        workOrders={workOrders}
      />
    )

  if (!authReady) {
    return <AuthLoadingRoute />
  }

  if (!session) {
    return (
      <LoginRoute
        authMessage={authMessage}
        loginEmail={loginEmail}
        loginPassword={loginPassword}
        onLogin={handleLogin}
        setLoginEmail={setLoginEmail}
        setLoginPassword={setLoginPassword}
      />
    )
  }

  if (currentUser?.role === 'iot_service') {
    return <ApiOnlyRoute currentUser={currentUser} onLogout={handleLogout} />
  }

  return (
    <main className="appShell">
      <ToastStack dismissToast={dismissToast} toasts={toasts} />
      {workOrderDraft && (
        <WorkOrderReviewDialog
          assets={assets}
          draft={workOrderDraft}
          onCancel={cancelWorkOrderDraft}
          onChange={updateWorkOrderDraft}
          onSubmit={submitWorkOrderDraft}
          submitting={workOrderSubmitting}
          technicians={technicians}
        />
      )}
      <header className="topBar">
        <div>
          <p className="eyebrow">Steel Plant Maintenance</p>
          <h1>{applicationTitle}</h1>
        </div>
        <div className="statusCluster">
          <div className="userPill">
            <strong>{currentUser?.display_name}</strong>
            <span>{currentUser ? roleLabels[currentUser.role] : ''}</span>
          </div>
          <button className="logoutButton" onClick={handleLogout} title="Logout">
            <LogOut size={16} />
            Logout
          </button>
        </div>
      </header>

      <section className="metricsGrid" aria-label="Plant health summary">
        <Metric icon={<Gauge />} label="Average Health" value={`${dashboard.average_health_score}%`} />
        <Metric icon={<AlertTriangle />} label="Active Alerts" value={dashboard.active_alert_count.toString()} />
        <Metric icon={<ShieldAlert />} label="Critical Alerts" value={dashboard.critical_alert_count.toString()} />
        <Metric icon={<Activity />} label="Assets Tracked" value={dashboard.equipment_count.toString()} />
      </section>

      {roleProfile && (
        <section className="roleContextBar" aria-label="Role workspace context">
          <div>
            <strong>{currentUser ? `Signed in as ${roleLabels[currentUser.role]}` : roleProfile.focus}</strong>
            <span>{roleProfile.mission}</span>
          </div>
          <div>
            <strong>{activeNavigationItem.label}</strong>
            <span>{activeNavigationItem.purpose}</span>
          </div>
        </section>
      )}

      <section className={`workArea ${activeView !== 'commandCenter' || !canDecision ? 'ingestionMode' : ''}`}>
        <aside className="leftNav" aria-label="Maintenance navigation">
          <nav className="primaryNav" aria-label="Primary navigation">
            {navigationItems.map((item) => {
              const selected = item.id === 'assets'
                ? activeView === 'assets' || activeView === 'asset'
                : activeView === item.id
              return (
                <button
                  className={`navButton ${selected ? 'selected' : ''}`}
                  key={item.id}
                  aria-label={item.label}
                  onClick={() => setActiveView(item.id)}
                  title={item.purpose}
                >
                  {navigationIcon(item.icon)}
                  <span>
                    <strong>{item.label}</strong>
                    <small>{item.purpose}</small>
                  </span>
                </button>
              )
            })}
          </nav>
          <section className="navFavorites" aria-label="Favorite shortcuts">
            <h2>{roleProfile?.focus ?? 'Favorites'}</h2>
            {currentUser && canAccessAppView(currentUser.role, 'workExecution') && (
              <button className="linkButton" onClick={() => setActiveView('workExecution')}>Assigned work</button>
            )}
            {currentUser && canAccessAppView(currentUser.role, 'planning') && (
              <button className="linkButton" onClick={() => setActiveView('planning')}>Planning board</button>
            )}
            <button className="linkButton" onClick={() => openAsset(selectedEquipment)}>Selected Asset</button>
          </section>
          {(canCreateWorkOrders || canSupervisorAssistant) && (
            <section className="navQuickActions" aria-label="Quick actions">
              <h2>Quick actions</h2>
              {canCreateWorkOrders && (
                <button className="textButton" onClick={() => createWorkOrderFromContext()}>
                  <Briefcase size={16} />
                  Create work order
                </button>
              )}
              {canSupervisorAssistant && (
                <button className="textButton" onClick={() => runSupervisorAssistant()}>
                  <Bot size={16} />
                  Review follow-ups
                </button>
              )}
            </section>
          )}
          <div className="sectionHeader compactHeader">
            <Wrench size={18} />
            <h2>Priority Assets ({dashboard.highest_risk_equipment.length})</h2>
          </div>
          <div className="assetListScroller" aria-label="Tracked priority assets">
            {dashboard.highest_risk_equipment.map((item) => (
              <button
                className={`assetRow ${item.equipment.id === selectedEquipment ? 'selected' : ''}`}
                key={item.equipment.id}
                onClick={() => openAsset(item.equipment.id)}
              >
                <span>
                  <strong>{item.equipment.name}</strong>
                  <small>{item.equipment.area}</small>
                </span>
                <span className={`riskBadge ${item.risk_level}`}>{item.risk_level}</span>
              </button>
            ))}
          </div>
        </aside>

        {activeRoute}
      </section>
    </main>
  )
}
