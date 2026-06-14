import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import {
  Activity,
  AlertTriangle,
  Bot,
  Briefcase,
  CalendarClock,
  ClipboardList,
  Gauge,
  LogOut,
  ShieldAlert,
  Sparkles,
  Users,
  Wrench,
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
  type LearningModelVersion,
  type LearningSummary,
  type NeoAction,
  type NeoChatResponse,
  type NeoTable,
  type PmPlan,
  type PmTemplate,
  type PredictionResponse,
  type RcaCase,
  type Recommendation,
  type SupervisorAssistantResponse,
  type TechnicianAssistantResponse,
  type StreamingStatus,
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

const WORK_EXECUTION_NEO_TIMEOUT_MS = 15_000

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
      `Open selected work order ${workOrder.id} for technician context.`,
      `Current status is ${statusLabel}, and field execution is blocked by material availability.`,
      `Material blocker: ${materialBlockReason}.`,
      'Explain the blocker, expected availability or substitute limitations if supplied, and the next permissible technician action without starting field execution.',
    ].join(' ')
  }
  return [
    nameInstruction,
    `Open selected work order ${workOrder.id} for technician context.`,
    `Current status is ${statusLabel}.`,
    'Summarize the immediate technician context from the work order, material plan, asset evidence, and approved learning notes.',
    'Ask for the next observation only if field execution is allowed.',
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
    'Open supervisor Work Execution initial context.',
    selected,
    `Queue context: ${approvals.length} waiting approval, ${followUps.length} follow-up, ${materialBlocked.length} material-blocked.`,
    'Write the initial supervisor welcome/context from this work execution queue.',
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
    completion_summary: `${workOrder.id} Neo query timed out before a live LLM answer was received.`,
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
  const [selectedWorkOrderId, setSelectedWorkOrderId] = useState('WO-8304')
  const [workOrderMessage, setWorkOrderMessage] = useState('')
  const [pmTemplates, setPmTemplates] = useState<PmTemplate[]>([])
  const [pmPlans, setPmPlans] = useState<PmPlan[]>([])
  const [pmPlanLoading, setPmPlanLoading] = useState(false)
  const [pmPlanMessage, setPmPlanMessage] = useState('')
  const [pmPlanStreamText, setPmPlanStreamText] = useState('')
  const [technicianObservation, setTechnicianObservation] = useState('There are hotspots and looseness around the checked connections.')
  const [technicianAssistant, setTechnicianAssistant] = useState<TechnicianAssistantResponse | null>(null)
  const [technicianLoading, setTechnicianLoading] = useState(false)
  const [technicianStreaming, setTechnicianStreaming] = useState(false)
  const [technicianChat, setTechnicianChat] = useState<AssistantTurn[]>([])
  const [supervisorQuestion, setSupervisorQuestion] = useState('Summarize follow-up actions for completed work orders.')
  const [supervisorAssistant, setSupervisorAssistant] = useState<SupervisorAssistantResponse | null>(null)
  const [supervisorLoading, setSupervisorLoading] = useState(false)
  const [supervisorStreaming, setSupervisorStreaming] = useState(false)
  const [supervisorChat, setSupervisorChat] = useState<AssistantTurn[]>([
  ])
  const [neoQuestion, setNeoQuestion] = useState('Show work orders needing follow-up')
  const [neoTable, setNeoTable] = useState<NeoTable | null>(null)
  const [neoLoading, setNeoLoading] = useState(false)
  const [neoStreaming, setNeoStreaming] = useState(false)
  const [neoMessages, setNeoMessages] = useState<AssistantTurn[]>([
  ])
  const [apiState, setApiState] = useState<'connected' | 'fallback'>('fallback')
  const [ingestSourceType, setIngestSourceType] = useState('sop')
  const [ingestTitle, setIngestTitle] = useState('')
  const [ingestFile, setIngestFile] = useState<File | null>(null)
  const [jsonMode, setJsonMode] = useState<'documents' | 'records'>('documents')
  const [jsonPayload, setJsonPayload] = useState('')
  const [ingestionMessage, setIngestionMessage] = useState('')
  const [streamingStatus, setStreamingStatus] = useState<StreamingStatus | null>(null)
  const [feedbackMessage, setFeedbackMessage] = useState('')
  const [feedbackRootCause, setFeedbackRootCause] = useState('')
  const [feedbackActionTaken, setFeedbackActionTaken] = useState('')
  const [feedbackOutcome, setFeedbackOutcome] = useState('')
  const [feedbackNotes, setFeedbackNotes] = useState('')
  const [reportMessage, setReportMessage] = useState('')
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
  const [selectedEmbeddingProfileId, setSelectedEmbeddingProfileId] = useState('')
  const [ragMigrationPreview, setRagMigrationPreview] = useState<LearningRagMigrationPlan | null>(null)
  const [ragTargetCollection, setRagTargetCollection] = useState('')
  const [artifactCleanupResult, setArtifactCleanupResult] = useState<LearningArtifactCleanupResult | null>(null)
  const [learningMessage, setLearningMessage] = useState('')
  const [learningLoading, setLearningLoading] = useState(false)
  const [learningDatasetName, setLearningDatasetName] = useState('maintenance-wizard-learning-snapshot')
  const [learningDatasetDescription, setLearningDatasetDescription] = useState('Approved examples for local LLM adapter tuning and evaluation.')
  const [adapterProvider, setAdapterProvider] = useState('openai')
  const [adapterModelName, setAdapterModelName] = useState('qwen2.5-7b-instruct-lora-candidate')
  const [adapterBaseModel, setAdapterBaseModel] = useState('qwen2.5-7b-instruct')
  const [adapterPath, setAdapterPath] = useState('')
  const [adapterNotes, setAdapterNotes] = useState('Offline PEFT adapter candidate trained from approved judge-qualified examples.')
  const [deploymentRuntimeProvider, setDeploymentRuntimeProvider] = useState('lm_studio')
  const [deploymentBaseUrl, setDeploymentBaseUrl] = useState('http://localhost:1234/v1')
  const [peftAdapterName, setPeftAdapterName] = useState('maintenance-wizard-qwen-lora')
  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserName, setNewUserName] = useState('')
  const [newUserRole, setNewUserRole] = useState<UserRole>('operator')
  const [newUserPassword, setNewUserPassword] = useState('')
  const [resetUser, setResetUser] = useState<AuthUser | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')
  const neoTranscriptRef = useRef<HTMLDivElement | null>(null)
  const morpheusProgressRef = useRef<HTMLDivElement | null>(null)
  const reliabilityStreamRef = useRef<HTMLDivElement | null>(null)
  const technicianInitialContextRef = useRef('')
  const supervisorInitialContextRef = useRef('')

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
    setTechnicianAssistant(null)
    setTechnicianChat([])
    setTechnicianLoading(false)
    setTechnicianStreaming(false)
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
    setLearningLoading(false)
    setAdapterProvider('openai')
    setAdapterModelName('qwen2.5-7b-instruct-lora-candidate')
    setAdapterBaseModel('qwen2.5-7b-instruct')
    setAdapterPath('')
    setAdapterNotes('Offline PEFT adapter candidate trained from approved judge-qualified examples.')
    setDeploymentRuntimeProvider('lm_studio')
    setDeploymentBaseUrl('http://localhost:1234/v1')
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

  function loadLearning() {
    setLearningLoading(true)
    setLearningMessage('')
    return Promise.all([
      api.learningSummary(),
      api.learningExamples(),
      api.learningDatasets(),
      api.learningModelDeployments().catch((): LearningModelDeployment[] => []),
      api.learningEmbeddingProfiles().catch((): LearningEmbeddingProfile[] => []),
    ])
      .then(([summary, examples, datasets, deployments, embeddingProfiles]) => {
        setLearningSummary(summary)
        setLearningExamples(examples)
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
        setApiState('connected')
      })
      .catch(() => {
        setLearningMessage('Learning data could not be loaded')
        setApiState('fallback')
      })
      .finally(() => setLearningLoading(false))
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

  async function refreshLearningExamples() {
    setLearningLoading(true)
    setLearningMessage('')
    try {
      const examples = await api.refreshLearningExamples()
      const summary = await api.learningSummary()
      setLearningExamples(examples)
      setLearningSummary(summary)
      setLearningMessage(`Refreshed ${examples.length} learning example${examples.length === 1 ? '' : 's'}`)
      setApiState('connected')
    } catch {
      setLearningMessage('Learning examples could not be refreshed')
      setApiState('fallback')
    } finally {
      setLearningLoading(false)
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
    try {
      const updated = await api.judgeLearningExample(example.id)
      setLearningExamples((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Judge scored ${updated.source_type} at ${Math.round(updated.judge_score * 100)}%`)
    } catch {
      setLearningMessage('Learning judge could not score the example')
    }
  }

  async function createLearningSnapshot() {
    setLearningLoading(true)
    setLearningMessage('')
    try {
      const snapshot = await api.createLearningDataset({
        name: learningDatasetName.trim() || 'maintenance-wizard-learning-snapshot',
        description: learningDatasetDescription.trim() || undefined,
        approved_only: true,
        min_judge_score: 0.65,
      })
      setLearningDatasets((items) => [snapshot, ...items])
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Created dataset snapshot with ${snapshot.example_count} approved example${snapshot.example_count === 1 ? '' : 's'}`)
    } catch {
      setLearningMessage('Learning dataset snapshot could not be created')
    } finally {
      setLearningLoading(false)
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
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  async function runLearningEvaluation() {
    const dataset = learningDatasets[0] ?? learningSummary?.recent_snapshots[0]
    const model = learningSummary?.model_versions[0]
    const prompt = learningSummary?.prompt_versions.find((item) => item.assistant === 'neo') ?? learningSummary?.prompt_versions[0]
    if (!dataset || !model || !prompt) {
      setLearningMessage('Create a dataset snapshot and keep model/prompt versions available before evaluation')
      return
    }
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  async function queuePeftTuningJob() {
    const dataset = learningDatasets[0] ?? learningSummary?.recent_snapshots[0]
    const model = learningSummary?.model_versions[0]
    const prompt = learningSummary?.prompt_versions.find((item) => item.assistant === 'neo') ?? learningSummary?.prompt_versions[0]
    if (!dataset || !model || !prompt) {
      setLearningMessage('Create a dataset snapshot and keep model/prompt versions available before queuing PEFT tuning')
      return
    }
    setLearningLoading(true)
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
      setLearningSummary(summary)
      setLearningMessage(`Queued PEFT tuning job ${job.id} with status ${job.status}`)
    } catch {
      setLearningMessage('PEFT tuning job could not be queued')
    } finally {
      setLearningLoading(false)
    }
  }

  async function reindexLearningRag() {
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  async function activateSelectedEmbeddingProfile() {
    if (!selectedEmbeddingProfileId) return
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  async function previewLearningRagMigration() {
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  async function runLearningRagMigration() {
    setLearningLoading(true)
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
      setLearningLoading(false)
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

  function loadPmPlanning() {
    setPmPlanLoading(true)
    setPmPlanMessage('')
    return Promise.all([
      api.pmTemplates().catch((): PmTemplate[] => []),
      api.pmPlans().catch((): PmPlan[] => []),
    ])
      .then(([templates, plans]) => {
        setPmTemplates(templates)
        setPmPlans(plans)
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
    let streamProvider = 'openai'
    let streamUsedLiveProvider = true
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
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          updateMessage({ provider: streamProvider, usedLiveProvider: streamUsedLiveProvider })
          return
        }
        if (event.type === 'token') {
          ensureMessage()
          streamedContent += event.content
          updateMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
          })
          return
        }
        if (event.type === 'done') {
          setNeoTable(event.response.table ?? null)
          if (event.response.action) void refreshAfterNeoAction(event.response.action)
          if (messageId) {
            updateMessage({
              content: streamedContent || event.response.answer,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
            })
          } else {
            setNeoMessages([
              {
                id: 'neo-welcome',
                role: 'assistant',
                content: event.response.answer,
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      })
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
    if (activeView === 'admin' && canStreaming) loadStreamingStatus()
  }, [activeView, canStreaming, currentUser?.role])

  useEffect(() => {
    if (activeView === 'admin' && canAdminUsers) loadUsers()
  }, [activeView, canAdminUsers])

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
    if (activeView === 'learningReview' && canReviewLearning) {
      void loadLearning()
    }
  }, [activeView, canReviewLearning])

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
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true

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
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          updateAssistantMessage({ provider: streamProvider, usedLiveProvider: streamUsedLiveProvider })
          return
        }
        if (event.type === 'token') {
          ensureAssistantMessage()
          streamedContent += event.content
          updateAssistantMessage({
            content: streamedContent,
            provider: streamProvider,
            usedLiveProvider: streamUsedLiveProvider,
          })
          return
        }
        if (event.type === 'done') {
          setNeoTable(event.response.table ?? null)
          if (event.response.action) void refreshAfterNeoAction(event.response.action)
          if (assistantMessageId) {
            const message = neoResponseMessage(event.response)
            updateAssistantMessage({
              content: message,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
            })
          } else {
            appendNeoResponse(event.response)
          }
        }
      })
      setNeoQuestion('')
    } catch {
      const fallback: NeoChatResponse = {
        answer: 'Sorry, Neo could not get a live LLM response right now. Please retry after confirming the LLM service is responding.',
        table: null,
        used_live_provider: false,
        provider: 'fallback',
      }
      appendNeoResponse(fallback)
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

  async function downloadReport() {
    if (!recommendation) return
    try {
      const markdown = await api.reportMarkdown(recommendation.equipment_id)
      const blob = new Blob([markdown], { type: 'text/markdown' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `${recommendation.equipment_id}-maintenance-report.md`
      link.click()
      window.URL.revokeObjectURL(url)
      setReportMessage('Report downloaded')
    } catch {
      setReportMessage('Report could not be downloaded')
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
      assigned_to: currentUser?.display_name ?? 'Maintenance Engineer',
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
    try {
      const created = await api.createWorkOrder(draftWorkOrderPayload(source))
      setWorkOrders((items) => [created, ...items.filter((item) => item.id !== created.id)])
      setSelectedWorkOrderId(created.id)
      setActiveView('workExecution')
      setWorkOrderMessage(`Created ${created.id}`)
    } catch {
      setWorkOrderMessage('Work order could not be created')
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
      void Promise.all([api.learningSummary(), api.learningExamples()])
        .then(([summary, examples]) => {
          setLearningSummary(summary)
          setLearningExamples(examples)
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
    const timeoutMs = WORK_EXECUTION_NEO_TIMEOUT_MS
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
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true

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
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          updateAssistantMessage({ provider: streamProvider, usedLiveProvider: streamUsedLiveProvider })
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
          })
          return
        }
        if (event.type === 'done') {
          setTechnicianAssistant(event.response)
          if (assistantMessageId) {
            updateAssistantMessage({
              content: streamedContent || event.response.next_prompt,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
            })
          } else {
            setTechnicianChat((turns) => [
              ...turns,
              {
                id: assistantTurnId('technician-assistant'),
                role: 'assistant',
                content: event.response.next_prompt,
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      }, controller?.signal)
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
    } catch {
      setWorkOrderMessage('Work order dispatch could not be saved')
    }
  }

  async function approveWorkOrder(workOrderId: string) {
    try {
      const updated = await api.updateWorkOrder(workOrderId, { status: 'APPR' })
      setWorkOrders((items) => items.map((item) => (item.id === updated.id ? updated : item)))
      setSelectedWorkOrderId(updated.id)
      setWorkOrderMessage(`${updated.id} approved`)
    } catch {
      setWorkOrderMessage('Work order approval could not be saved')
    }
  }

  async function loadSupervisorInitialContext(workOrder: WorkOrder | undefined, contextKey: string) {
    const isCurrentContext = () => supervisorInitialContextRef.current === contextKey
    setSupervisorAssistant(null)
    setSupervisorChat([])
    setSupervisorLoading(true)
    setSupervisorStreaming(false)
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
    const timeoutMs = WORK_EXECUTION_NEO_TIMEOUT_MS
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
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
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
      }, (event) => {
        if (!isCurrentContext()) return
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          updateAssistantMessage({ provider: streamProvider, usedLiveProvider: streamUsedLiveProvider })
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
          })
          return
        }
        if (event.type === 'done') {
          setSupervisorAssistant(event.response)
          if (assistantMessageId) {
            updateAssistantMessage({
              content: streamedContent || event.response.summary,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
            })
          } else {
            setSupervisorChat((turns) => [
              ...turns,
              {
                id: assistantTurnId('supervisor-assistant'),
                role: 'assistant',
                content: event.response.summary,
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
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
    const timeoutMs = WORK_EXECUTION_NEO_TIMEOUT_MS
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
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
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
          },
        ])
        return assistantMessageId
      }

      const updateAssistantMessage = (updates: Partial<AssistantTurn>) => {
        if (!assistantMessageId) return
        setSupervisorChat((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
      }

      await api.supervisorAssistStream(payload, (event) => {
        if (event.type === 'meta') {
          streamProvider = event.provider
          streamUsedLiveProvider = event.used_live_provider
          updateAssistantMessage({ provider: streamProvider, usedLiveProvider: streamUsedLiveProvider })
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
          })
          return
        }
        if (event.type === 'done') {
          setSupervisorAssistant(event.response)
          if (assistantMessageId) {
            updateAssistantMessage({
              content: streamedContent || event.response.summary,
              provider: event.response.provider,
              usedLiveProvider: event.response.used_live_provider,
            })
          } else {
            setSupervisorChat((turns) => [
              ...turns,
              {
                id: assistantTurnId('supervisor-assistant'),
                role: 'assistant',
                content: event.response.summary,
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
      await loadDashboard()
    } catch {
      setIngestionMessage('JSON ingestion failed')
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
    } catch {
      setUserMessage('User could not be created')
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
    setLearningLoading(true)
    setLearningMessage('')
    try {
      const promotion = await api.promoteLearningModelVersion({
        model_version_id: model.id,
        evaluation_run_id: evaluation.id,
        notes: `Promoted from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Promoted adapter ${model.model_name} with audit record ${promotion.id}`)
    } catch {
      setLearningMessage('Adapter promotion was rejected by the evaluation gate')
    } finally {
      setLearningLoading(false)
    }
  }

  async function rollbackLearningAdapter(model: LearningModelVersion) {
    const evaluation = passedEvaluationForModel(model.id)
    if (!evaluation) {
      setLearningMessage('Run a passing evaluation for this model before rollback')
      return
    }
    setLearningLoading(true)
    setLearningMessage('')
    try {
      const promotion = await api.rollbackLearningModelVersion({
        target_model_version_id: model.id,
        evaluation_run_id: evaluation.id,
        notes: `Rollback from Learning Review by ${currentUser?.email ?? 'reviewer'}.`,
      })
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      setLearningMessage(`Rolled back to ${model.model_name} with audit record ${promotion.id}`)
    } catch {
      setLearningMessage('Model rollback was rejected by the evaluation gate')
    } finally {
      setLearningLoading(false)
    }
  }

  async function deployLearningAdapter(model: LearningModelVersion) {
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  async function previewLearningArtifactCleanup() {
    setLearningLoading(true)
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
      setLearningLoading(false)
    }
  }

  const openWorkOrderRoute = (workOrderId: string) => {
    setSelectedWorkOrderId(workOrderId)
    setActiveView('workExecution')
  }

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
        reliabilityStreamRef={reliabilityStreamRef}
        reportMessage={reportMessage}
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
        pmPlanLoading={pmPlanLoading}
        pmPlanMessage={pmPlanMessage}
        pmPlanStreamText={pmPlanStreamText}
        pmPlans={pmPlans}
        pmTemplates={pmTemplates}
        convertPmPlanToWorkOrder={convertPmPlanToWorkOrder}
        draftPreventivePlan={draftPreventivePlan}
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
        workOrderMessage={workOrderMessage}
        workOrders={workOrders}
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
          rcaMessage={rcaMessage}
          selectedRcaCaseId={selectedRcaCaseId}
          selectedWorkOrderId={selectedWorkOrderId}
          setSelectedRcaCaseId={setSelectedRcaCaseId}
          setSelectedWorkOrderId={setSelectedWorkOrderId}
          workOrders={workOrders}
        />
      </section>
    ) : activeView === 'learningReview' && canReviewLearning ? (
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
        learningLoading={learningLoading}
        learningMessage={learningMessage}
        learningSummary={learningSummary}
        peftAdapterName={peftAdapterName}
        previewLearningArtifactCleanup={previewLearningArtifactCleanup}
        previewLearningRagMigration={previewLearningRagMigration}
        promoteLearningAdapter={promoteLearningAdapter}
        queuePeftTuningJob={queuePeftTuningJob}
        ragMigrationPreview={ragMigrationPreview}
        ragTargetCollection={ragTargetCollection}
        refreshLearningExamples={refreshLearningExamples}
        registerLearningAdapter={registerLearningAdapter}
        reindexLearningRag={reindexLearningRag}
        rollbackLearningAdapter={rollbackLearningAdapter}
        runLearningEvaluation={runLearningEvaluation}
        runLearningRagMigration={runLearningRagMigration}
        selectedEmbeddingProfileId={selectedEmbeddingProfileId}
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
        toggleLearningApproval={toggleLearningApproval}
      />
    ) : activeView === 'admin' && canAdminUsers ? (
      <section className="adminRouteStack" aria-label="Admin workspace">
        <section className="detailPanel pageIntroPanel">
          <div className="sectionHeader">
            <Users size={18} />
            <div>
              <h2>Admin</h2>
              <small>Users, ingestion, and system status</small>
            </div>
          </div>
          <p className="emptyState">Admin controls are isolated from every non-admin role.</p>
        </section>
        {canIngest && (
          <IngestionRoute
            ingestJsonPayload={ingestJsonPayload}
            ingestSelectedFile={ingestSelectedFile}
            ingestSourceType={ingestSourceType}
            ingestTitle={ingestTitle}
            ingestionMessage={ingestionMessage}
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
          userMessage={userMessage}
          users={users}
        />
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
