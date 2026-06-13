import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Bot,
  Briefcase,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  Database,
  Download,
  FileJson,
  FileText,
  Gauge,
  KeyRound,
  LogIn,
  LogOut,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  Upload,
  UserPlus,
  Users,
  Wrench,
} from 'lucide-react'
import {
  api,
  fallbackDashboard,
  type AssetDetail,
  type AssetDetailSection,
  type AssetDocument,
  type AssetListItem,
  type AssetMetricSnapshot,
  type AssetPerformanceChart,
  type AssetReliabilityMetric,
  type AssetSubsystem,
  type AuthSession,
  type AuthUser,
  type DashboardSummary,
  type HealthSummary,
  type LearningDatasetSnapshot,
  type LearningEvaluationRun,
  type LearningExample,
  type LearningArtifact,
  type LearningJob,
  type LearningModelPromotion,
  type LearningModelVersion,
  type LearningSummary,
  type MaintenanceEvent,
  type NeoAction,
  type NeoChatResponse,
  type NeoTable,
  type PredictionResponse,
  type Recommendation,
  type SupervisorAssistantResponse,
  type TechnicianAssistantResponse,
  type StreamingStatus,
  type UserRole,
  type WorkOrder,
  type WorkOrderCreateRequest,
} from './services/api'

const riskRank = { low: 1, medium: 2, high: 3, critical: 4 }
type AppView = 'dashboard' | 'assets' | 'asset' | 'workOrders' | 'ingestion' | 'learning' | 'users'
type AssetTab = 'summary' | 'maintenance' | 'performance' | 'reliability' | 'documents' | 'workOrders'

const assetSectionsByTab: Record<AssetTab, AssetDetailSection[]> = {
  summary: ['summary'],
  maintenance: ['maintenance'],
  performance: ['performance'],
  reliability: ['reliability'],
  documents: ['documents'],
  workOrders: ['work_orders'],
}

function mergeAssetDetail(
  current: AssetDetail | null,
  next: AssetDetail,
  sections: AssetDetailSection[],
): AssetDetail {
  const merged: AssetDetail = current
    ? { ...current, profile: next.profile, health: next.health }
    : { ...next }
  const requested = new Set(sections)

  if (requested.has('summary')) {
    merged.metrics = next.metrics
    merged.recommendations = next.recommendations
    merged.subsystems = next.subsystems
  }
  if (requested.has('maintenance')) {
    merged.maintenance_events = next.maintenance_events
    merged.work_orders = next.work_orders
  }
  if (requested.has('performance')) {
    merged.metrics = next.metrics
    merged.performance_charts = next.performance_charts
  }
  if (requested.has('reliability')) {
    merged.reliability_metrics = next.reliability_metrics
    merged.prediction = next.prediction
  }
  if (requested.has('documents')) {
    merged.documents = next.documents
    merged.knowledge = next.knowledge
  }
  if (requested.has('work_orders')) {
    merged.work_orders = next.work_orders
  }

  return merged
}

const roleLabels: Record<UserRole, string> = {
  admin: 'Admin',
  maintenance_engineer: 'Maintenance Engineer',
  maintenance_technician: 'Maintenance Technician',
  maintenance_supervisor: 'Maintenance Supervisor',
  reliability_engineer: 'Reliability Engineer',
  planner: 'Planner',
  operator: 'Operator',
  iot_service: 'IoT Service',
}

const roleOptions: UserRole[] = [
  'admin',
  'maintenance_engineer',
  'maintenance_technician',
  'maintenance_supervisor',
  'reliability_engineer',
  'planner',
  'operator',
  'iot_service',
]

const decisionRoles: UserRole[] = ['admin', 'maintenance_engineer', 'reliability_engineer', 'planner']
const technicianAssistantRoles: UserRole[] = ['maintenance_technician']
const supervisorAssistantRoles: UserRole[] = ['maintenance_supervisor']
const workOrderCreationRoles: UserRole[] = [
  'admin',
  'maintenance_engineer',
  'maintenance_technician',
  'maintenance_supervisor',
  'reliability_engineer',
  'planner',
]
const workOrderAssignmentRoles: UserRole[] = ['admin', 'maintenance_supervisor']
const diagnosisAssistantName = 'Morpheus'
const reliabilityAssistantName = 'Smith'
const technicianAssistantName = 'Neo'
const supervisorAssistantName = 'Neo'
const feedbackRoles: UserRole[] = ['admin', 'maintenance_engineer', 'reliability_engineer']
const ingestionRoles: UserRole[] = ['admin', 'reliability_engineer']
const streamingRoles: UserRole[] = ['admin', 'reliability_engineer']
const learningRoles: UserRole[] = ['admin', 'maintenance_engineer', 'reliability_engineer']

const fallbackWorkOrders: WorkOrder[] = [
  {
    id: 'WO-8304',
    equipment_id: 'RM-DRIVE-01',
    title: 'Inspect main drive bearing vibration',
    description: 'Inspect bearing housing, coupling alignment, lubrication condition, and foundation bolts.',
    status: 'APPR',
    priority: 1,
    work_type: 'CM',
    failure_class: 'MECH',
    problem_code: 'BRGVIB',
    classification: 'Bearing vibration',
    assigned_to: 'Maintenance Technician',
    supervisor: 'Maintenance Supervisor',
    due_date: '2026-06-12T18:00:00+05:30',
    recommended_action: 'Reduce load if vibration persists and verify coupling alignment.',
    follow_up_required: true,
    ai_summary: 'High-risk drive vibration needs mechanical inspection before restart.',
    completion_summary: null,
    created_at: '2026-06-11T08:00:00+05:30',
    updated_at: '2026-06-11T11:00:00+05:30',
    completed_at: null,
    logs: [],
  },
  {
    id: 'WO-8311',
    equipment_id: 'BF-BLOWER-02',
    title: 'Verify inlet guide vane actuator response',
    description: 'Check actuator travel, linkage looseness, and position feedback drift.',
    status: 'WAPPR',
    priority: 2,
    work_type: 'CM',
    failure_class: 'CTRL',
    problem_code: 'IGVACT',
    classification: 'Control actuator',
    assigned_to: 'Reliability Engineer',
    supervisor: 'Blast Furnace Supervisor',
    due_date: '2026-06-13T12:00:00+05:30',
    recommended_action: 'Stroke-test the guide vane actuator and compare response to pressure variance.',
    follow_up_required: false,
    ai_summary: 'Pressure variance points to actuator or linkage response drift.',
    completion_summary: null,
    created_at: '2026-06-11T09:00:00+05:30',
    updated_at: '2026-06-11T09:30:00+05:30',
    completed_at: null,
    logs: [],
  },
  {
    id: 'WO-8297',
    equipment_id: 'OH-CRANE-05',
    title: 'Inspect hoist brake temperature and current',
    description: 'Review hoist current and brake temperature after heavy-lift restriction.',
    status: 'COMP',
    priority: 1,
    work_type: 'EM',
    failure_class: 'ELEC',
    problem_code: 'HOISTBRK',
    classification: 'Hoist braking',
    assigned_to: 'Crane Technician',
    supervisor: 'Melt Shop Supervisor',
    due_date: '2026-06-11T17:00:00+05:30',
    recommended_action: 'Plan brake shoe replacement follow-up.',
    follow_up_required: true,
    ai_summary: 'Completed inspection still needs supervisor follow-up.',
    completion_summary: 'Brake temperature normalized after lift restriction.',
    created_at: '2026-06-10T09:00:00+05:30',
    updated_at: '2026-06-11T16:35:00+05:30',
    completed_at: '2026-06-11T16:35:00+05:30',
    logs: [],
  },
  {
    id: 'WO-8275',
    equipment_id: 'HYD-SYS-04',
    title: 'Investigate hydraulic oil temperature rise',
    description: 'Inspect cooler fouling, pump cartridge condition, and pressure pulsation.',
    status: 'WMATL',
    priority: 2,
    work_type: 'PM',
    failure_class: 'HYD',
    problem_code: 'OILTEMP',
    classification: 'Hydraulic temperature',
    assigned_to: 'Hydraulic Technician',
    supervisor: 'Rolling Mill Supervisor',
    due_date: '2026-06-14T10:00:00+05:30',
    recommended_action: 'Reserve pump cartridge assembly and inspect cooler differential temperature.',
    follow_up_required: false,
    ai_summary: 'Hydraulic temperature work is waiting for material coordination.',
    completion_summary: null,
    created_at: '2026-06-11T10:00:00+05:30',
    updated_at: '2026-06-11T10:30:00+05:30',
    completed_at: null,
    logs: [],
  },
]

function hasRole(user: AuthUser | undefined, roles: UserRole[]) {
  return Boolean(user && roles.includes(user.role))
}

function fallbackWorkOrdersForUser(user?: AuthUser | null) {
  if (user?.role === 'maintenance_technician') {
    return fallbackWorkOrders.filter((order) => order.assigned_to === user.display_name)
  }
  return fallbackWorkOrders
}

type AssistantTurn = {
  id: string
  role: 'user' | 'assistant'
  content: string
  details?: string[]
  provider?: string
  usedLiveProvider?: boolean
}

function assistantTurnId(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function assistantProviderLabel(turn: AssistantTurn) {
  if (!turn.provider) return ''
  if (turn.provider === 'deterministic') return 'Dashboard data'
  return `${turn.usedLiveProvider ? 'Live LLM' : 'LLM fallback'} · ${turn.provider}`
}

function AssistantMessageContent({ turn }: { turn: AssistantTurn }) {
  if (turn.role === 'assistant') {
    return <FormattedAssistantContent content={turn.content} />
  }
  return <p>{turn.content}</p>
}

function scrollStreamToBottom(ref: { current: HTMLElement | null }) {
  const scroll = () => {
    const node = ref.current
    if (!node) return
    node.scrollTop = node.scrollHeight
    if (typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'end', inline: 'nearest', behavior: 'auto' })
      node.scrollTop = node.scrollHeight
    }
  }

  scroll()

  if (typeof window !== 'undefined' && window.requestAnimationFrame) {
    window.requestAnimationFrame(scroll)
    window.setTimeout(scroll, 0)
    window.setTimeout(scroll, 50)
    window.setTimeout(scroll, 150)
    window.setTimeout(scroll, 300)
    return
  }

  scroll()
}

function usePinnedStreamScroll(ref: { current: HTMLElement | null }, trigger: string) {
  useEffect(() => {
    const node = ref.current
    if (!node) return

    scrollStreamToBottom(ref)

    if (typeof MutationObserver === 'undefined') return

    const observer = new MutationObserver(() => scrollStreamToBottom(ref))
    observer.observe(node, {
      childList: true,
      characterData: true,
      subtree: true,
    })

    return () => observer.disconnect()
  }, [ref, trigger])
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
  const [activeView, setActiveView] = useState<AppView>('dashboard')
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
  const [technicianObservation, setTechnicianObservation] = useState('There are hotspots and looseness around the checked connections.')
  const [technicianAssistant, setTechnicianAssistant] = useState<TechnicianAssistantResponse | null>(null)
  const [technicianLoading, setTechnicianLoading] = useState(false)
  const [technicianStreaming, setTechnicianStreaming] = useState(false)
  const [technicianChat, setTechnicianChat] = useState<AssistantTurn[]>([
    {
      id: 'technician-welcome',
      role: 'assistant',
      content: `I’m ${technicianAssistantName}. Let’s start the work order. Do you observe any problems?`,
    },
  ])
  const [supervisorQuestion, setSupervisorQuestion] = useState('Summarize follow-up actions for completed work orders.')
  const [supervisorAssistant, setSupervisorAssistant] = useState<SupervisorAssistantResponse | null>(null)
  const [supervisorLoading, setSupervisorLoading] = useState(false)
  const [supervisorStreaming, setSupervisorStreaming] = useState(false)
  const [supervisorChat, setSupervisorChat] = useState<AssistantTurn[]>([
    {
      id: 'supervisor-welcome',
      role: 'assistant',
      content: `I’m ${supervisorAssistantName}. Ask me to summarize follow-ups, risks, or draft a follow-up work order.`,
    },
  ])
  const [neoQuestion, setNeoQuestion] = useState('Show work orders needing follow-up')
  const [neoTable, setNeoTable] = useState<NeoTable | null>(null)
  const [neoLoading, setNeoLoading] = useState(false)
  const [neoStreaming, setNeoStreaming] = useState(false)
  const [neoMessages, setNeoMessages] = useState<AssistantTurn[]>([
    {
      id: 'neo-welcome',
      role: 'assistant',
      content: 'I’m Neo. I’m checking your role-aware attention queue.',
    },
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
  const [learningMessage, setLearningMessage] = useState('')
  const [learningLoading, setLearningLoading] = useState(false)
  const [learningDatasetName, setLearningDatasetName] = useState('maintenance-wizard-learning-snapshot')
  const [learningDatasetDescription, setLearningDatasetDescription] = useState('Approved examples for local LLM adapter tuning and evaluation.')
  const [adapterProvider, setAdapterProvider] = useState('openai')
  const [adapterModelName, setAdapterModelName] = useState('qwen2.5-7b-instruct-lora-candidate')
  const [adapterBaseModel, setAdapterBaseModel] = useState('qwen2.5-7b-instruct')
  const [adapterPath, setAdapterPath] = useState('')
  const [adapterNotes, setAdapterNotes] = useState('Offline PEFT adapter candidate trained from approved judge-qualified examples.')
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

  const currentUser = session?.user
  const canDecision = hasRole(currentUser, decisionRoles)
  const canTechnicianAssistant = hasRole(currentUser, technicianAssistantRoles)
  const canSupervisorAssistant = hasRole(currentUser, supervisorAssistantRoles)
  const canFeedback = hasRole(currentUser, feedbackRoles)
  const canIngest = hasRole(currentUser, ingestionRoles)
  const canStreaming = hasRole(currentUser, streamingRoles)
  const canReviewLearning = hasRole(currentUser, learningRoles)
  const canAdminUsers = currentUser?.role === 'admin'
  const canCreateWorkOrders = hasRole(currentUser, workOrderCreationRoles)
  const canAssignWorkOrders = hasRole(currentUser, workOrderAssignmentRoles)
  const canApproveWorkOrders = canAssignWorkOrders

  function clearSession(message = '') {
    api.setSession(null)
    setSession(null)
    setActiveView('dashboard')
    setWorkOrders(fallbackWorkOrders)
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
    setNeoTable(null)
    setLearningSummary(null)
    setLearningExamples([])
    setLearningDatasets([])
    setLearningMessage('')
    setLearningLoading(false)
    setAdapterProvider('openai')
    setAdapterModelName('qwen2.5-7b-instruct-lora-candidate')
    setAdapterBaseModel('qwen2.5-7b-instruct')
    setAdapterPath('')
    setAdapterNotes('Offline PEFT adapter candidate trained from approved judge-qualified examples.')
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
      setActiveView('dashboard')
    } catch {
      setAuthMessage('Invalid email or password')
    }
  }

  async function handleLogout() {
    try {
      await api.logout()
    } catch {
      // Client-side token removal is still valid if the logout request fails.
    }
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
    return Promise.all([api.learningSummary(), api.learningExamples(), api.learningDatasets()])
      .then(([summary, examples, datasets]) => {
        setLearningSummary(summary)
        setLearningExamples(examples)
        setLearningDatasets(datasets)
        setApiState('connected')
      })
      .catch(() => {
        setLearningMessage('Learning data could not be loaded')
        setApiState('fallback')
      })
      .finally(() => setLearningLoading(false))
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
      const job = await api.reindexLearningRag()
      const summary = await api.learningSummary()
      setLearningSummary(summary)
      const chunkCount = Number(job.output_refs?.chunk_count ?? 0)
      setLearningMessage(`Reindexed ${chunkCount} RAG chunk${chunkCount === 1 ? '' : 's'} with status ${job.status}`)
    } catch {
      setLearningMessage('RAG vector reindex could not be completed')
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

  function loadNeoWelcome() {
    setNeoMessages([
      {
        id: 'neo-welcome-loading',
        role: 'assistant',
        content: 'I’m Neo. I’m checking your role-aware attention queue.',
      },
    ])
    setNeoTable(null)
    return api
      .neoWelcome()
      .then((response) => {
        setNeoTable(response.table ?? null)
        setNeoMessages([
          {
            id: 'neo-welcome',
            role: 'assistant',
            content: response.answer,
            details: neoResponseDetails(response),
            provider: response.provider,
            usedLiveProvider: response.used_live_provider,
          },
        ])
        setApiState('connected')
      })
      .catch(() => {
        setNeoMessages([
          {
            id: 'neo-welcome-fallback',
            role: 'assistant',
            content: 'I’m Neo. I could not load your role-aware attention queue yet. Ask me for assigned work, assets, work orders, or users and I’ll use your role permissions.',
            provider: 'fallback',
            usedLiveProvider: false,
          },
        ])
        setApiState('fallback')
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
    if (activeView === 'ingestion' && canStreaming) loadStreamingStatus()
    if (activeView === 'ingestion' && !canIngest) setActiveView('dashboard')
    if (activeView === 'learning' && !canReviewLearning) setActiveView('dashboard')
    if (activeView === 'users' && !canAdminUsers) setActiveView('dashboard')
  }, [activeView, canIngest, canReviewLearning, canStreaming, canAdminUsers])

  useEffect(() => {
    if (activeView === 'users' && canAdminUsers) loadUsers()
  }, [activeView, canAdminUsers])

  useEffect(() => {
    if (activeView === 'learning' && canReviewLearning) void loadLearning()
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
              details: neoResponseDetails(event.response),
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
        answer: 'Neo could not reach the assistant service. Try assets, work orders, or users again after the backend reconnects.',
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
    if (response.action) return response.answer
    return response.table
      ? `I found ${response.table.rows.length} row${response.table.rows.length === 1 ? '' : 's'} for ${response.table.title}. The table is updated in the dashboard.`
      : response.answer
  }

  function neoResponseDetails(response: NeoChatResponse) {
    const details: string[] = []
    if (response.action) {
      details.push(`${response.action.label}: ${response.action.status.replace('_', ' ')}`)
      if (response.action.target_id) details.push(`Target: ${response.action.target_id}`)
      if (response.action.detail) details.push(response.action.detail)
    }
    if (response.table) {
      details.push(`Updated table: ${response.table.title}`)
      details.push(`${response.table.rows.length} row(s)`)
    }
    return details.length ? details : undefined
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
        details: neoResponseDetails(response),
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
      setActiveView('workOrders')
      setWorkOrderMessage(`Created ${created.id}`)
    } catch {
      setWorkOrderMessage('Work order could not be created')
    }
  }

  function technicianAssistantDetails(response: TechnicianAssistantResponse) {
    return [
      ...response.live_directions,
      ...response.recommendations,
      ...response.safety_reminders.map((item) => `Safety: ${item}`),
      `Problem code: ${response.suggested_problem_code}`,
      `Summary: ${response.completion_summary}`,
    ]
  }

  function supervisorAssistantDetails(response: SupervisorAssistantResponse) {
    return [
      ...response.follow_up_actions,
      ...response.risks.map((item) => `Risk: ${item}`),
      ...(response.draft_work_order ? [`Draft work order: ${response.draft_work_order.title}`] : []),
    ]
  }

  async function runTechnicianAssistant() {
    if (technicianLoading) return
    if (!selectedWorkOrder) return
    const prompt = technicianObservation.trim() || 'Give me live directions for this work order.'
    setTechnicianChat((turns) => [
      ...turns,
      { id: assistantTurnId('technician-user'), role: 'user', content: prompt },
    ])
    setTechnicianLoading(true)
    setTechnicianStreaming(false)
    try {
      let assistantMessageId: string | null = null
      let streamedContent = ''
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true

      const ensureAssistantMessage = () => {
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
        if (!assistantMessageId) return
        setTechnicianChat((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
      }

      await api.technicianAssistStream(selectedWorkOrder.id, prompt, (event) => {
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
          setTechnicianAssistant(event.response)
          if (assistantMessageId) {
            updateAssistantMessage({
              content: streamedContent || event.response.next_prompt,
              details: technicianAssistantDetails(event.response),
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
                details: technicianAssistantDetails(event.response),
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      })
      setTechnicianObservation('')
      setWorkOrderMessage(`${technicianAssistantName} updated the recommended problem code and summary`)
    } catch {
      const fallbackResponse: TechnicianAssistantResponse = {
        work_order_id: selectedWorkOrder.id,
        next_prompt: 'What abnormal condition do you observe?',
        live_directions: [selectedWorkOrder.recommended_action],
        recommendations: ['Record the observed condition and before/after readings.'],
        safety_reminders: ['Apply lockout/tagout before intrusive inspection.'],
        suggested_problem_code: selectedWorkOrder.problem_code,
        suggested_failure_class: selectedWorkOrder.failure_class,
        completion_summary: prompt,
        evidence: [],
        used_live_provider: false,
        provider: 'fallback',
      }
      setTechnicianAssistant(fallbackResponse)
      setTechnicianChat((turns) => [
        ...turns,
        {
          id: assistantTurnId('technician-fallback'),
          role: 'assistant',
          content: fallbackResponse.next_prompt,
          details: technicianAssistantDetails(fallbackResponse),
          provider: fallbackResponse.provider,
          usedLiveProvider: fallbackResponse.used_live_provider,
        },
      ])
    } finally {
      setTechnicianLoading(false)
      setTechnicianStreaming(false)
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

  async function runSupervisorAssistant(workOrderId?: string) {
    if (supervisorLoading) return
    const prompt = supervisorQuestion.trim() || 'Review follow-up status.'
    setSupervisorChat((turns) => [
      ...turns,
      { id: assistantTurnId('supervisor-user'), role: 'user', content: prompt },
    ])
    setSupervisorLoading(true)
    setSupervisorStreaming(false)
    try {
      let assistantMessageId: string | null = null
      let streamedContent = ''
      let streamProvider = 'openai'
      let streamUsedLiveProvider = true
      const payload = {
        work_order_id: workOrderId,
        queue_name: 'follow_up',
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
              details: supervisorAssistantDetails(event.response),
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
                details: supervisorAssistantDetails(event.response),
                provider: event.response.provider,
                usedLiveProvider: event.response.used_live_provider,
              },
            ])
          }
        }
      })
      setSupervisorQuestion('')
      setWorkOrderMessage(`${supervisorAssistantName} reviewed follow-ups`)
    } catch {
      const fallbackResponse: SupervisorAssistantResponse = {
        summary: `${workOrders.length} work order(s) reviewed locally.`,
        follow_up_actions: workOrders.filter((item) => item.follow_up_required).map((item) => `${item.id}: ${item.recommended_action}`),
        risks: workOrders.filter((item) => item.priority === 1 && !['COMP', 'CLOSE'].includes(item.status)).map((item) => `${item.id} remains ${item.status}`),
        draft_work_order: null,
        referenced_work_orders: workOrders.map((item) => item.id),
        used_live_provider: false,
        provider: 'fallback',
      }
      setSupervisorAssistant(fallbackResponse)
      setSupervisorChat((turns) => [
        ...turns,
        {
          id: assistantTurnId('supervisor-fallback'),
          role: 'assistant',
          content: fallbackResponse.summary,
          details: supervisorAssistantDetails(fallbackResponse),
          provider: fallbackResponse.provider,
          usedLiveProvider: fallbackResponse.used_live_provider,
        },
      ])
    } finally {
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

  const recommendationPanel = (
    <div className="recommendationSection morpheusPanel">
      <div className="assistantHeaderCompact">
        <span className="assistantAvatar">M</span>
        <div>
          <h2>{diagnosisAssistantName}</h2>
          <small>Diagnosis assistant</small>
        </div>
      </div>
      {(diagnosisProvider || diagnosisLoading) && (
        <small className="providerLine">
          {diagnosisLoading && <span className="loadingSpinner" aria-hidden="true" />}
          {diagnosisProvider
            ? `${diagnosisUsedLive ? 'Live LLM' : 'LLM fallback'} · ${diagnosisProvider}`
            : 'Starting diagnosis stream'}
        </small>
      )}
      {diagnosisStreamText && (
        <div className="morpheusProgress" ref={morpheusProgressRef} aria-live="polite">
          <FormattedAssistantContent content={diagnosisStreamText} />
        </div>
      )}
      {diagnosisMessage && <p className="inlineStatus errorText">{diagnosisMessage}</p>}
      {recommendation ? (
        <>
          <div className="sectionHeader recommendationTitle">
            <CheckCircle2 size={18} />
            <h3>Recommendation</h3>
          </div>
          <p className="diagnosis">{recommendation.diagnosis}</p>
          <div className="recommendationBadges">
            <span className={`riskBadge ${recommendation.risk_level}`}>{recommendation.risk_level}</span>
            <span className="rolePill">
              {recommendation.used_live_provider ? 'Live LLM' : 'LLM fallback'} · {recommendation.provider}
            </span>
          </div>
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
          <h3>Immediate Actions</h3>
          <ul>{recommendation.immediate_actions.map((action) => <li key={action}>{action}</li>)}</ul>
          <h3>Planned Actions</h3>
          <ul>{recommendation.planned_actions.map((action) => <li key={action}>{action}</li>)}</ul>
          <h3>Evidence</h3>
          {recommendation.evidence.slice(0, 3).map((evidence) => (
            <p className="evidence" key={evidence.source_id}>
              <strong>{evidence.title}</strong>
              {evidence.excerpt}
              {evidence.relevance_reason && <small>{evidence.relevance_reason}</small>}
            </p>
          ))}
          {canFeedback && (
            <>
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
            </>
          )}
          <div className="buttonRow">
            <button className="downloadReport" onClick={downloadReport}>
              <Download size={16} />
              Export Report
            </button>
            {canCreateWorkOrders && (
              <button className="textButton" onClick={() => createWorkOrderFromContext(recommendation)}>
                <Briefcase size={16} />
                Create Work Order
              </button>
            )}
          </div>
          {reportMessage && <p className="inlineStatus">{reportMessage}</p>}
        </>
      ) : (
        <p className="emptyState">
          {diagnosisLoading || diagnosisStreaming
            ? `${diagnosisAssistantName} is preparing the diagnosis...`
            : `Run ${diagnosisAssistantName} to generate cited maintenance actions.`}
        </p>
      )}
    </div>
  )

  const operationalDashboardView = (
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
                  {turn.details && <ul>{turn.details.map((item) => <li key={item}>{item}</li>)}</ul>}
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
              onOpen={(id) => {
                setSelectedWorkOrderId(id)
                setActiveView('workOrders')
              }}
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
            <MiniBars values={[92, 78, 64, 88]} />
          </section>
        </div>
      </div>
    </section>
  )

  const assetMetricByKey = new Map((assetDetail?.metrics ?? []).map((metric) => [metric.metric_key, metric]))
  const assetHealth = assetDetail?.health
  const assetProfile = assetDetail?.profile
  const isAssetSectionPending = (section: AssetDetailSection) =>
    !assetLoadedSections.includes(section) || Boolean(assetSectionLoading[section])
  const assetLoadingPanel = (label: string) => (
    <section className="detailPanel widePanel">
      <p className="emptyState">Loading {label} data...</p>
    </section>
  )

  const assetSummaryTab = assetDetail ? (
    <div className="assetSummaryGrid">
      <section className="detailPanel summarySubsystems">
        <h2>Sub-systems</h2>
        <AssetSubsystemList subsystems={assetDetail.subsystems} />
      </section>
      <section className="healthStack summaryHealthStack">
        <AssetMetricTile metric={assetMetricByKey.get('health')} fallbackValue={assetHealth?.health_score} />
        <AssetMetricTile metric={assetMetricByKey.get('efficiency')} />
        <AssetMetricTile metric={assetMetricByKey.get('risk')} />
      </section>
      <section className="detailPanel assetFactsPanel summaryProfile">
        <h2>Asset profile</h2>
        <AssetProfileFacts detail={assetDetail} />
      </section>
      <section className="detailPanel performanceInsights summaryInsight">
        <div className="sectionHeader">
          <Sparkles size={18} />
          <h2>Performance insights</h2>
        </div>
        <div className="insightHero">
          <span>Risk</span>
          <strong>{100 - (assetHealth?.health_score ?? 0)}%</strong>
          <small>Probable cause</small>
          <h2>{assetHealth?.active_alerts[0]?.message ?? assetHealth?.notes[0]}</h2>
        </div>
        <button className="outlineButton" disabled={diagnosisLoading} onClick={runDiagnosis}>
          {diagnosisLoading ? <span className="loadingSpinner" aria-hidden="true" /> : null}
          View data
        </button>
      </section>
      <section className="detailPanel summaryActions">
        <h2>Recommended actions</h2>
        <ol className="actionList">
          {assetDetail.recommendations.slice(0, 3).map((action) => (
            <li key={action.id}>
              <strong>{action.title}</strong>
              <span>{action.description}</span>
            </li>
          ))}
        </ol>
        {canCreateWorkOrders && (
          <button className="outlineButton" onClick={() => createWorkOrderFromContext(recommendation ?? undefined)}>
            Create work order
          </button>
        )}
      </section>
      {canDecision && (
        <section className="detailPanel assetDecisionPanel">
          <div className="sectionHeader">
            <CheckCircle2 size={18} />
            <h2>Diagnosis and recommendation</h2>
          </div>
          <div className="diagnoseActionRow">
            <button className="textButton" disabled={diagnosisLoading} onClick={runDiagnosis}>
              {diagnosisLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <CheckCircle2 size={16} />}
              {diagnosisLoading ? `${diagnosisAssistantName} is diagnosing...` : `Run ${diagnosisAssistantName}`}
            </button>
          </div>
          {recommendationPanel}
        </section>
      )}
    </div>
  ) : null

  const assetTabContent = assetDetail ? (
    <>
      {assetTab === 'summary' && assetSummaryTab}
      {assetTab === 'maintenance' && (isAssetSectionPending('maintenance') ? assetLoadingPanel('maintenance') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Maintenance history</h2>
            <MaintenanceEventTable events={assetDetail.maintenance_events} />
          </section>
          <section className="detailPanel widePanel">
            <h2>Related work orders</h2>
            <WorkOrderTable
              workOrders={assetWorkOrders}
              compact
              canApprove={canApproveWorkOrders}
              canStart={canTechnicianAssistant}
              onApprove={approveWorkOrder}
              onStart={startWorkOrder}
              onOpen={(id) => { setSelectedWorkOrderId(id); setActiveView('workOrders') }}
            />
          </section>
        </div>
      ))}
      {assetTab === 'performance' && (isAssetSectionPending('performance') ? assetLoadingPanel('performance') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Performance metrics</h2>
            <AssetMetricGrid metrics={assetDetail.metrics} />
          </section>
          {assetDetail.performance_charts.map((chart) => (
            <SignalLineChartCard chart={chart} key={chart.signal} />
          ))}
        </div>
      ))}
      {assetTab === 'reliability' && (isAssetSectionPending('reliability') ? assetLoadingPanel('reliability') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Reliability metrics</h2>
            <ReliabilityMetricGrid metrics={assetDetail.reliability_metrics} />
          </section>
          <section className="detailPanel widePanel smithPredictionPanel">
            <div className="assistantHeaderCompact">
              <span className="assistantAvatar">S</span>
              <div>
                <h2>{reliabilityAssistantName}</h2>
                <small>Predictive failure assistant</small>
              </div>
            </div>
            <div
              className="reliabilityPredictionStream"
              ref={reliabilityStreamRef}
              aria-label={`${reliabilityAssistantName} failure prediction stream`}
              aria-live="polite"
            >
              {(assetReliabilityProvider || assetReliabilityLoading) && (
                <small className="providerLine">
                  {assetReliabilityLoading && <span className="loadingSpinner" aria-hidden="true" />}
                  {assetReliabilityProvider
                    ? `${assetReliabilityUsedLive ? 'Live LLM' : 'LLM unavailable'} · ${assetReliabilityProvider}`
                    : `${reliabilityAssistantName} is starting the prediction stream`}
                </small>
              )}
              {assetReliabilityText && <FormattedAssistantContent content={assetReliabilityText} />}
              {assetReliabilityMessage && <p className="inlineStatus errorText">{assetReliabilityMessage}</p>}
              {assetReliabilityPrediction ? (
                <>
                  <div className="predictionSummary">
                    <span className={`riskBadge ${assetReliabilityPrediction.risk_level}`}>{assetReliabilityPrediction.risk_level}</span>
                    <strong>{Math.round(assetReliabilityPrediction.failure_probability * 100)}% failure probability</strong>
                    <small>{assetReliabilityPrediction.remaining_useful_life_days} days estimated RUL</small>
                  </div>
                  <ul className="actionList">
                    {assetReliabilityPrediction.drivers.slice(0, 6).map((driver) => <li key={driver}>{driver}</li>)}
                  </ul>
                </>
              ) : !assetReliabilityText && !assetReliabilityMessage && (
                <p className="emptyState">{reliabilityAssistantName} is streaming live LLM failure prediction...</p>
              )}
            </div>
          </section>
        </div>
      ))}
      {assetTab === 'documents' && (isAssetSectionPending('documents') ? assetLoadingPanel('document') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Knowledge Retrieval</h2>
            <KnowledgeEvidenceList evidence={assetDetail.knowledge} />
          </section>
          <section className="detailPanel widePanel">
            <h2>SOP, manual, log, and history evidence</h2>
            <AssetDocumentList documents={assetDetail.documents} />
          </section>
        </div>
      ))}
      {assetTab === 'workOrders' && (isAssetSectionPending('work_orders') ? assetLoadingPanel('work order') : (
        <section className="detailPanel widePanel">
          <h2>Related work orders</h2>
          <WorkOrderTable
            workOrders={assetWorkOrders}
            canApprove={canApproveWorkOrders}
            canStart={canTechnicianAssistant}
            onApprove={approveWorkOrder}
            onStart={startWorkOrder}
            onOpen={(id) => { setSelectedWorkOrderId(id); setActiveView('workOrders') }}
          />
        </section>
      ))}
    </>
  ) : null

  const assetDetailView = (
    <section className="assetDetailGrid">
      <div className="pageHeader">
        <p className="breadcrumb">Operational dashboard / Assets /</p>
        <h1>{assetProfile?.name ?? selectedEquipment}</h1>
        <span>{assetProfile ? `Last updated ${formatDate(assetProfile.last_updated)}` : 'Loading live asset data'}</span>
      </div>
      <div className="tabRow">
        {(['summary', 'maintenance', 'performance', 'reliability', 'documents', 'workOrders'] as AssetTab[]).map((tab) => (
          <button className={assetTab === tab ? 'selected' : ''} onClick={() => setAssetTab(tab)} key={tab}>
            {tab === 'workOrders' ? 'Work Orders' : tab[0].toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>
      {assetDetailLoading && <section className="detailPanel widePanel"><p className="emptyState">Loading asset detail data...</p></section>}
      {!assetDetailLoading && assetMessage && <section className="detailPanel widePanel"><p className="inlineStatus errorText">{assetMessage}</p></section>}
      {assetDetail && (
        <>
          {assetTabContent}
        </>
      )}
    </section>
  )

  const workOrdersView = (
    <section className="workOrderLayout">
      <section className="workOrderCenterColumn" aria-label="Work order center pane">
        <section className="detailPanel workOrderAssistantPanel">
          {selectedWorkOrder ? (
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
                        {turn.details && <ul>{turn.details.map((item) => <li key={item}>{item}</li>)}</ul>}
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
                        {turn.details && <ul>{turn.details.map((item) => <li key={item}>{item}</li>)}</ul>}
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
          {canTechnicianAssistant && selectedWorkOrder && (
            <button
              className="textButton completeWorkOrderButton"
              type="button"
              disabled={technicianLoading || !technicianAssistant}
              onClick={completeSelectedWorkOrder}
            >
              Submit completed work
            </button>
          )}
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
                <span className="statusPill fallback">{selectedWorkOrder.status}</span>
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

  const assetsView = (
    <section className="detailPanel assetsView">
      <div className="sectionHeader">
        <Activity size={18} />
        <h2>Assets</h2>
      </div>
      {assets.length > 0 ? (
        <AssetsTable assets={assets} onOpen={openAsset} />
      ) : (
        <p className="emptyState">Asset table data is unavailable until the backend API responds.</p>
      )}
      {assetMessage && <p className="inlineStatus">{assetMessage}</p>}
    </section>
  )

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
      <div className="streamingStatusPanel">
        <div className="sectionHeader compactHeader">
          <Activity size={18} />
          <h3>IoT Stream</h3>
        </div>
        <div className="streamingStatusGrid">
          <span>State</span>
          <strong className={`streamState ${streamingStatus?.state ?? 'error'}`}>{streamingStatus?.state ?? 'unavailable'}</strong>
          <span>Broker</span>
          <strong>{streamingStatus?.broker ?? 'nats'}</strong>
          <span>Stream</span>
          <strong>{streamingStatus?.stream ?? 'MW_IOT'}</strong>
          <span>Consumer</span>
          <strong>{streamingStatus?.consumer ?? 'maintenance-wizard-ingestor'}</strong>
          <span>Processed</span>
          <strong>{streamingStatus?.processed_count ?? 0}</strong>
          <span>Failed</span>
          <strong>{streamingStatus?.failed_count ?? 0}</strong>
          <span>Last Message</span>
          <strong>{streamingStatus?.last_message_timestamp ?? 'None yet'}</strong>
        </div>
        {streamingStatus?.last_error && <p className="inlineStatus errorText">{streamingStatus.last_error}</p>}
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

  const learningModels: LearningModelVersion[] = learningSummary?.model_versions ?? []
  const learningPrompts = learningSummary?.prompt_versions ?? []
  const learningEvaluations: LearningEvaluationRun[] = learningSummary?.evaluation_runs ?? []
  const learningJobs: LearningJob[] = learningSummary?.recent_jobs ?? []
  const learningArtifacts: LearningArtifact[] = learningSummary?.recent_artifacts ?? []
  const learningPromotions: LearningModelPromotion[] = learningSummary?.recent_promotions ?? []
  const passedEvaluationForModel = (modelId: string) =>
    learningEvaluations.find((run) => run.model_version_id === modelId && run.passed)

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

  const learningView = (
    <section className="detailPanel learningView">
      <div className="sectionHeader">
        <Sparkles size={18} />
        <h2>Learning and Tuning</h2>
      </div>
      <p className="emptyState">
        Review approved human feedback, maintenance labels, work-order outcomes, ingested documents, and assistant interactions before exporting a local tuning dataset.
      </p>
      <div className="learningToolbar">
        <button className="textButton" onClick={refreshLearningExamples} disabled={learningLoading}>
          {learningLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
          Refresh examples
        </button>
        <label className="field">
          <span>Snapshot name</span>
          <input value={learningDatasetName} onChange={(event) => setLearningDatasetName(event.target.value)} />
        </label>
        <label className="field">
          <span>Description</span>
          <input value={learningDatasetDescription} onChange={(event) => setLearningDatasetDescription(event.target.value)} />
        </label>
        <button className="textButton" onClick={createLearningSnapshot} disabled={learningLoading}>
          <FileJson size={16} />
          Create JSONL snapshot
        </button>
      </div>
      <div className="learningStats">
        {(['interactions', 'examples', 'approved_examples', 'snapshots', 'artifacts', 'promotions'] as const).map((key) => (
          <span className="learningStat" key={key}>
            <small>{key.replace(/_/g, ' ')}</small>
            <strong>{learningSummary?.counts[key] ?? 0}</strong>
          </span>
        ))}
      </div>
      <div className="vectorStoreStatus">
        <span>
          <strong>RAG vector DB</strong>
          <small>
            {learningSummary?.vector_store?.store ?? 'unknown'} · {learningSummary?.vector_store?.state ?? 'not checked'}
          </small>
        </span>
        <span>
          <small>Collection</small>
          <strong>{learningSummary?.vector_store?.collection ?? 'local fallback'}</strong>
        </span>
        <span>
          <small>Embedding</small>
          <strong>
            {String(learningSummary?.vector_store?.embedding_profile?.model ?? 'unknown')} · v
            {String(learningSummary?.vector_store?.embedding_profile?.version ?? 'unknown')}
          </strong>
        </span>
        <span>
          <small>Migration</small>
          <strong>{learningSummary?.vector_store?.migration_required ? 'Required' : 'Current'}</strong>
        </span>
        <button className="textButton" onClick={reindexLearningRag} disabled={learningLoading}>
          {learningLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Database size={16} />}
          Reindex RAG
        </button>
      </div>
      <div className="servingModelStatus">
        <span>
          <strong>Serving LLM</strong>
          <small>
            {learningSummary?.serving_model?.source?.replace(/_/g, ' ') ?? 'unknown'} · {learningSummary?.serving_model?.provider ?? 'unknown'}
          </small>
        </span>
        <span>
          <small>Model</small>
          <strong>
            {learningSummary?.serving_model?.provider === 'ollama'
              ? learningSummary?.serving_model?.ollama_model
              : learningSummary?.serving_model?.openai_model}
          </strong>
        </span>
        {learningSummary?.serving_model?.active_model_version_id && (
          <span>
            <small>Active version</small>
            <strong>{learningSummary.serving_model.active_model_version_id}</strong>
          </span>
        )}
        {learningSummary?.serving_model?.adapter_path && (
          <span>
            <small>Adapter</small>
            <strong>{learningSummary.serving_model.adapter_path}</strong>
          </span>
        )}
        {learningSummary?.serving_model?.warning && (
          <span>
            <small>Status</small>
            <strong>{learningSummary.serving_model.warning}</strong>
          </span>
        )}
      </div>
      <div className="artifactStoreStatus">
        <span>
          <strong>Artifact store</strong>
          <small>
            {String(learningSummary?.artifact_store?.store ?? 'unknown')} · {String(learningSummary?.artifact_store?.state ?? 'not checked')}
          </small>
        </span>
        <span>
          <small>Location</small>
          <strong>
            {String(
              learningSummary?.artifact_store?.store === 's3'
                ? learningSummary?.artifact_store?.bucket ?? 'bucket not configured'
                : learningSummary?.artifact_store?.local_dir ?? 'local dir not configured',
            )}
          </strong>
        </span>
        {Boolean(learningSummary?.artifact_store?.prefix) && (
          <span>
            <small>Prefix</small>
            <strong>{String(learningSummary?.artifact_store?.prefix)}</strong>
          </span>
        )}
      </div>
      <div className="peftTrainerStatus">
        <span>
          <strong>PEFT trainer</strong>
          <small>
            {String(learningSummary?.peft_trainer?.mode ?? 'unknown')} · {String(learningSummary?.peft_trainer?.configured ? 'configured' : 'not configured')}
          </small>
        </span>
        <span>
          <small>Timeout</small>
          <strong>{String(learningSummary?.peft_trainer?.timeout_seconds ?? 'not checked')}s</strong>
        </span>
        <span>
          <small>Output</small>
          <strong>{String(learningSummary?.peft_trainer?.output_dir ?? 'not configured')}</strong>
        </span>
      </div>
      <div className="learningGrid">
        <section className="learningPanel">
          <h3>Approved Controls</h3>
          <div className="learningExamples" aria-label="Learning examples">
            {learningExamples.length ? learningExamples.slice(0, 30).map((example) => (
              <article className={`learningExample ${example.approved ? 'approved' : ''}`} key={example.id}>
                <div>
                  <strong>{example.source_type.replace(/_/g, ' ')}</strong>
                  <small>{example.equipment_id ?? 'company-wide'} · {formatDate(example.created_at)}</small>
                </div>
                <div className="judgeScoreRow">
                  <span className={`judgeBadge ${example.judge_label}`}>
                    {Math.round(example.judge_score * 100)}% · {example.judge_label.replace(/_/g, ' ')}
                  </span>
                  <small>{example.judge_used_live_provider ? 'Live LLM judge' : 'Judge fallback'} · {example.judge_provider}</small>
                </div>
                <p>{example.instruction}</p>
                <blockquote>{clipText(example.expected_output, 220)}</blockquote>
                {example.judge_rationale && <p className="judgeRationale">{clipText(example.judge_rationale, 220)}</p>}
                <div className="learningExampleActions">
                  <button className="outlineButton" onClick={() => judgeLearningExample(example)}>
                    Judge
                  </button>
                  <button className={example.approved ? 'outlineButton' : 'textButton'} onClick={() => toggleLearningApproval(example)}>
                    {example.approved ? 'Remove approval' : 'Approve'}
                  </button>
                </div>
              </article>
            )) : (
              <p className="emptyState">No learning examples have been generated yet.</p>
            )}
          </div>
        </section>
        <section className="learningPanel">
          <h3>Model and Prompt Versions</h3>
          <div className="versionList">
            {learningModels.map((model) => {
              const promotionEvaluation = passedEvaluationForModel(model.id)
              const canPromoteModel = model.status !== 'active' && Boolean(promotionEvaluation)
              const canRollbackModel = model.status === 'retired' && Boolean(promotionEvaluation)
              return (
                <div className="versionRow" key={model.id}>
                  <strong>{model.model_name}</strong>
                  <small>{model.provider} · {model.status}</small>
                  {model.adapter_path && <small>Adapter {model.adapter_path}</small>}
                  {promotionEvaluation ? (
                    <small>Promotion gate passed by evaluation {promotionEvaluation.id}</small>
                  ) : model.status !== 'active' ? (
                    <small>Promotion gate requires a passing evaluation for this model.</small>
                  ) : null}
                  {model.notes && <p>{model.notes}</p>}
                  {(canPromoteModel || canRollbackModel) && (
                    <div className="versionActions">
                      {canPromoteModel && (
                        <button className="textButton" onClick={() => promoteLearningAdapter(model)} disabled={learningLoading}>
                          <CheckCircle2 size={16} />
                          Promote adapter
                        </button>
                      )}
                      {canRollbackModel && (
                        <button className="outlineButton" onClick={() => rollbackLearningAdapter(model)} disabled={learningLoading}>
                          Roll back to this model
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            {learningPrompts.map((prompt) => (
              <div className="versionRow" key={prompt.id}>
                <strong>{prompt.assistant} / {prompt.version}</strong>
                <small>{prompt.status}</small>
                {prompt.notes && <p>{prompt.notes}</p>}
              </div>
            ))}
          </div>
          <h3>Promotion Audit</h3>
          <div className="promotionList">
            {learningPromotions.length ? learningPromotions.map((promotion) => (
              <div className={`promotionRow ${promotion.action}`} key={promotion.id}>
                <span>
                  <strong>{promotion.action === 'promote' ? 'Adapter promoted' : 'Rollback completed'}</strong>
                  <small>{promotion.model_version_id} · {formatDate(promotion.created_at)}</small>
                </span>
                <small>Evaluation {promotion.evaluation_run_id} · Dataset {promotion.dataset_id}</small>
                <small>Reviewer {promotion.reviewer_email}</small>
                {promotion.previous_active_model_id && <small>Previous active {promotion.previous_active_model_id}</small>}
                {promotion.notes && <p>{promotion.notes}</p>}
              </div>
            )) : (
              <p className="emptyState">Adapter promotions and rollbacks will appear after a reviewer activates a passed model.</p>
            )}
          </div>
          <h3>Adapter Candidate</h3>
          <div className="learningAdapterGrid">
            <label className="field">
              <span>Provider</span>
              <input value={adapterProvider} onChange={(event) => setAdapterProvider(event.target.value)} />
            </label>
            <label className="field">
              <span>Model</span>
              <input value={adapterModelName} onChange={(event) => setAdapterModelName(event.target.value)} />
            </label>
            <label className="field">
              <span>Base model</span>
              <input value={adapterBaseModel} onChange={(event) => setAdapterBaseModel(event.target.value)} />
            </label>
            <label className="field">
              <span>Adapter path</span>
              <input value={adapterPath} onChange={(event) => setAdapterPath(event.target.value)} placeholder="adapter registry path or artifact URI" />
            </label>
            <label className="field adapterNotesField">
              <span>Notes</span>
              <textarea value={adapterNotes} onChange={(event) => setAdapterNotes(event.target.value)} />
            </label>
            <button className="textButton" onClick={registerLearningAdapter} disabled={learningLoading || !adapterModelName.trim()}>
              <Sparkles size={16} />
              Register adapter
            </button>
          </div>
          <h3>Dataset Snapshots</h3>
          <div className="datasetList">
            {learningDatasets.length ? learningDatasets.map((snapshot) => (
              <div className="datasetRow" key={snapshot.id}>
                <span>
                  <strong>{snapshot.name}</strong>
                  <small>{snapshot.example_count} examples · {formatDate(snapshot.created_at)}</small>
                </span>
                <button className="iconTextButton" onClick={() => downloadLearningSnapshot(snapshot)}>
                  <Download size={16} />
                  JSONL
                </button>
              </div>
            )) : (
              <p className="emptyState">Create a snapshot after approving examples.</p>
            )}
          </div>
          <h3>Evaluation Runs</h3>
          <button className="textButton fullWidthAction" onClick={runLearningEvaluation} disabled={learningLoading}>
            <CheckCircle2 size={16} />
            Run dataset evaluation
          </button>
          <div className="evaluationList">
            {learningEvaluations.length ? learningEvaluations.map((run) => (
              <div className={`evaluationRow ${run.passed ? 'passed' : 'review'}`} key={run.id}>
                <span>
                  <strong>{run.passed ? 'Passed' : 'Needs review'}</strong>
                  <small>{formatDate(run.created_at)}</small>
                </span>
                <div className="evaluationMetrics">
                  <span>Quality <strong>{metricValue(run.metrics.quality_score)}</strong></span>
                  <span>Avg judge <strong>{metricValue(run.metrics.average_judge_score)}</strong></span>
                  <span>Sources <strong>{metricValue(run.metrics.source_type_coverage)}</strong></span>
                  <span>Assets <strong>{metricValue(run.metrics.asset_coverage)}</strong></span>
                </div>
                {run.notes && <p>{run.notes}</p>}
              </div>
            )) : (
              <p className="emptyState">Run an evaluation after creating a dataset snapshot.</p>
            )}
          </div>
          <h3>Async Learning Jobs</h3>
          <div className="learningAdapterGrid">
            <label className="field adapterNotesField">
              <span>PEFT adapter job name</span>
              <input value={peftAdapterName} onChange={(event) => setPeftAdapterName(event.target.value)} />
            </label>
            <button className="textButton fullWidthAction" onClick={queuePeftTuningJob} disabled={learningLoading}>
              <Sparkles size={16} />
              Queue PEFT tuning job
            </button>
          </div>
          <div className="jobList">
            {learningJobs.length ? learningJobs.map((job) => (
              <div className={`jobRow ${job.status}`} key={job.id}>
                <span>
                  <strong>{job.job_type.replace(/_/g, ' ')}</strong>
                  <small>{job.status} · {formatDate(job.updated_at)}</small>
                </span>
                <small>{job.subject}</small>
                {job.error && <p>{job.error}</p>}
                {typeof job.output_refs.dispatch === 'string' && <p>{job.output_refs.dispatch}</p>}
              </div>
            )) : (
              <p className="emptyState">Learning jobs will appear after review, dataset, evaluation, or PEFT queue actions.</p>
            )}
          </div>
          <h3>Learning Artifacts</h3>
          <div className="artifactList">
            {learningArtifacts.length ? learningArtifacts.map((artifact) => (
              <div className="artifactRow" key={artifact.id}>
                <span>
                  <strong>{artifact.artifact_type.replace(/_/g, ' ')}</strong>
                  <small>{artifact.job_id} · {formatDate(artifact.created_at)}</small>
                </span>
                <small>sha256 {artifact.content_hash.slice(0, 12)}</small>
              </div>
            )) : (
              <p className="emptyState">Worker-produced datasets, manifests, and adapter artifacts will appear here.</p>
            )}
          </div>
        </section>
      </div>
      {learningMessage && <p className="inlineStatus">{learningMessage}</p>}
    </section>
  )

  const usersView = (
    <section className="detailPanel usersView">
      <div className="sectionHeader">
        <Users size={18} />
        <h2>Users</h2>
      </div>
      <div className="userCreateGrid">
        <label className="field">
          <span>Email</span>
          <input value={newUserEmail} onChange={(event) => setNewUserEmail(event.target.value)} />
        </label>
        <label className="field">
          <span>Name</span>
          <input value={newUserName} onChange={(event) => setNewUserName(event.target.value)} />
        </label>
        <label className="field">
          <span>Role</span>
          <select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value as UserRole)}>
            {roleOptions.map((role) => (
              <option value={role} key={role}>
                {roleLabels[role]}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Password</span>
          <input type="password" value={newUserPassword} onChange={(event) => setNewUserPassword(event.target.value)} />
        </label>
        <button onClick={createNewUser} title="Create user">
          <UserPlus size={16} />
          Create
        </button>
      </div>
      <div className="userList" aria-label="Application users">
        {users.map((user) => (
          <div className="userRow" key={user.id}>
            <span>
              <strong>{user.display_name}</strong>
              <small>{user.email}</small>
            </span>
            <span className="rolePill">{roleLabels[user.role]}</span>
            <span className={`activePill ${user.is_active ? 'active' : 'inactive'}`}>
              {user.is_active ? 'Active' : 'Inactive'}
            </span>
            <button className="textButton subtleButton" onClick={() => toggleUserActive(user)}>
              {user.is_active ? 'Deactivate' : 'Activate'}
            </button>
            <button className="iconTextButton" onClick={() => openResetPassword(user)} title="Reset password">
              <KeyRound size={16} />
              Reset
            </button>
          </div>
        ))}
      </div>
      {userMessage && <p className="inlineStatus">{userMessage}</p>}
      {resetUser && (
        <div className="modalOverlay" role="presentation">
          <section className="modalPanel" role="dialog" aria-modal="true" aria-labelledby="reset-password-title">
            <div className="sectionHeader compactHeader">
              <KeyRound size={18} />
              <h2 id="reset-password-title">Reset Password</h2>
            </div>
            <p className="modalContext">
              {resetUser.display_name}
              <small>{resetUser.email}</small>
            </p>
            <label className="field">
              <span>New Password</span>
              <input
                autoFocus
                type="password"
                value={resetPasswordValue}
                onChange={(event) => setResetPasswordValue(event.target.value)}
              />
            </label>
            <div className="modalActions">
              <button className="outlineButton" onClick={closeResetPassword}>
                Cancel
              </button>
              <button className="iconTextButton" onClick={resetPassword}>
                <KeyRound size={16} />
                Reset
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  )

  if (!authReady) {
    return (
      <main className="loginShell">
        <section className="loginPanel">
          <div className="sectionHeader">
            <ShieldAlert size={20} />
            <h1>Maintenance Wizard</h1>
          </div>
          <p className="emptyState">Checking session...</p>
        </section>
      </main>
    )
  }

  if (!session) {
    return (
      <main className="loginShell">
        <form className="loginPanel" onSubmit={handleLogin}>
          <div className="sectionHeader">
            <ShieldAlert size={20} />
            <h1>Maintenance Wizard</h1>
          </div>
          <p className="eyebrow">Steel Plant Maintenance</p>
          <label className="field">
            <span>Email</span>
            <input value={loginEmail} onChange={(event) => setLoginEmail(event.target.value)} />
          </label>
          <label className="field">
            <span>Password</span>
            <input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} />
          </label>
          <button className="loginButton" type="submit">
            <LogIn size={18} />
            Sign In
          </button>
          <p className="demoHint">Demo users use password DemoPass123!</p>
          {authMessage && <p className="inlineStatus errorText">{authMessage}</p>}
        </form>
      </main>
    )
  }

  if (currentUser?.role === 'iot_service') {
    return (
      <main className="appShell">
        <header className="topBar">
          <div>
            <p className="eyebrow">Steel Plant Maintenance</p>
            <h1>Maintenance Wizard</h1>
          </div>
          <button className="logoutButton" onClick={handleLogout}>
            <LogOut size={16} />
            Logout
          </button>
        </header>
        <section className="detailPanel apiOnlyPanel">
          <div className="sectionHeader">
            <Database size={18} />
            <h2>{currentUser.display_name}</h2>
          </div>
          <p className="emptyState">This account is enabled for API ingestion and does not have application navigation.</p>
        </section>
      </main>
    )
  }

  return (
    <main className="appShell">
      <header className="topBar">
        <div>
          <p className="eyebrow">Steel Plant Maintenance</p>
          <h1>Maintenance Wizard</h1>
        </div>
        <div className="statusCluster">
          <div className={`statusPill ${apiState}`}>
            <Database size={16} />
            {apiState === 'connected' ? 'API connected' : 'Sample view'}
          </div>
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

      <section className={`workArea ${activeView !== 'dashboard' || !canDecision ? 'ingestionMode' : ''}`}>
        <aside className="leftNav" aria-label="Maintenance navigation">
          <nav className="primaryNav" aria-label="Primary navigation">
            <button className={`navButton ${activeView === 'dashboard' ? 'selected' : ''}`} onClick={() => setActiveView('dashboard')}>
              <ClipboardList size={17} />
              Dashboard
            </button>
            <button className={`navButton ${activeView === 'assets' || activeView === 'asset' ? 'selected' : ''}`} onClick={() => setActiveView('assets')}>
              <Activity size={17} />
              Assets
            </button>
            <button className={`navButton ${activeView === 'workOrders' ? 'selected' : ''}`} onClick={() => setActiveView('workOrders')}>
              <Briefcase size={17} />
              Work Orders
            </button>
            {canIngest && (
              <button className={`navButton ${activeView === 'ingestion' ? 'selected' : ''}`} onClick={() => setActiveView('ingestion')}>
                <Upload size={17} />
                Ingestion
              </button>
            )}
            {canReviewLearning && (
              <button className={`navButton ${activeView === 'learning' ? 'selected' : ''}`} onClick={() => setActiveView('learning')}>
                <Sparkles size={17} />
                Learning
              </button>
            )}
            {canAdminUsers && (
              <button className={`navButton ${activeView === 'users' ? 'selected' : ''}`} onClick={() => setActiveView('users')}>
                <Users size={17} />
                Users
              </button>
            )}
          </nav>
          <section className="navFavorites" aria-label="Favorite shortcuts">
            <h2>Favorites</h2>
            <button className="linkButton" onClick={() => setActiveView('workOrders')}>Work Orders</button>
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

        {activeView === 'dashboard' ? (
          operationalDashboardView
        ) : activeView === 'assets' ? (
          assetsView
        ) : activeView === 'asset' ? (
          assetDetailView
        ) : activeView === 'workOrders' ? (
          workOrdersView
        ) : activeView === 'ingestion' ? (
          ingestionView
        ) : activeView === 'learning' ? (
          learningView
        ) : (
          usersView
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

function KpiCard({ title, value, unit, detail, ai, className = '' }: { title: string; value: string; unit: string; detail: string; ai?: string; className?: string }) {
  const [open, setOpen] = useState(false)
  return (
    <section className={`kpiCard ${className}`}>
      <div className="kpiHeader">
        <h2>{title}</h2>
        {ai && (
          <button className="aiBadge" onClick={() => setOpen(!open)} title="Explain with AI">
            AI
          </button>
        )}
      </div>
      <p>
        <strong>{value}</strong> {unit}
      </p>
      <small>{detail}</small>
      {open && <div className="aiPopover">{ai}</div>}
    </section>
  )
}

type AssistantContentBlock =
  | { type: 'heading'; level: number; text: string }
  | { type: 'paragraph'; text: string }
  | { type: 'ol' | 'ul'; items: string[] }

function FormattedAssistantContent({ content }: { content: string }) {
  const blocks = parseAssistantContent(content)
  return (
    <div className="assistantFormattedContent">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const HeadingTag = block.level >= 4 ? 'h4' : 'h3'
          return <HeadingTag key={`heading-${index}`}>{renderInlineMarkdown(block.text, `heading-${index}`)}</HeadingTag>
        }
        if (block.type === 'ol') {
          return (
            <ol key={`ol-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item, `ol-${index}-${itemIndex}`)}</li>
              ))}
            </ol>
          )
        }
        if (block.type === 'ul') {
          return (
            <ul key={`ul-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`${item}-${itemIndex}`}>{renderInlineMarkdown(item, `ul-${index}-${itemIndex}`)}</li>
              ))}
            </ul>
          )
        }
        if (block.type === 'paragraph') {
          return <p key={`paragraph-${index}`}>{renderInlineMarkdown(block.text, `paragraph-${index}`)}</p>
        }
        return null
      })}
    </div>
  )
}

function parseAssistantContent(content: string): AssistantContentBlock[] {
  const normalized = normalizeAssistantContent(content)
  const blocks: AssistantContentBlock[] = []
  let listType: 'ol' | 'ul' | null = null
  let listItems: string[] = []

  function flushList() {
    if (listType && listItems.length > 0) {
      blocks.push({ type: listType, items: listItems })
    }
    listType = null
    listItems = []
  }

  normalized.split('\n').forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      flushList()
      return
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      flushList()
      blocks.push({
        type: 'heading',
        level: heading[1].length,
        text: stripMarkdownHeadingSuffix(heading[2]),
      })
      return
    }

    const ordered = trimmed.match(/^\d+\.\s+(.+)$/)
    if (ordered) {
      if (listType !== 'ol') flushList()
      listType = 'ol'
      listItems.push(ordered[1])
      return
    }

    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    if (unordered) {
      if (listType !== 'ul') flushList()
      listType = 'ul'
      listItems.push(unordered[1])
      return
    }

    flushList()
    blocks.push({ type: 'paragraph', text: trimmed })
  })

  flushList()
  return blocks.length > 0 ? blocks : [{ type: 'paragraph', text: content }]
}

function normalizeAssistantContent(content: string) {
  return content
    .replace(/\r\n/g, '\n')
    .replace(/\s+(#{1,4}\s+)/g, '\n$1')
    .replace(/(#{1,4}\s+[^:\n]+:)\s+(\d+\.\s+)/g, '$1\n$2')
    .replace(/\s+(\d+\.\s+(?:\*\*|[A-Z]))/g, '\n$1')
    .replace(/\s+-\s+(?=[A-Z*])/g, '\n- ')
}

function stripMarkdownHeadingSuffix(text: string) {
  return text.replace(/\s+#+$/, '')
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-strong-${index}`}>{part.slice(2, -2)}</strong>
    }
    return <span key={`${keyPrefix}-text-${index}`}>{part}</span>
  })
}

function NeoResultTable({ table }: { table: NeoTable }) {
  return (
    <div className="neoResultTable" aria-label={`${table.title} results table`}>
      <div className="neoResultHead" style={{ gridTemplateColumns: `repeat(${table.columns.length}, minmax(120px, 1fr))` }}>
        {table.columns.map((column) => <span key={column}>{column}</span>)}
      </div>
      {table.rows.map((row, index) => (
        <div className="neoResultRow" style={{ gridTemplateColumns: `repeat(${table.columns.length}, minmax(120px, 1fr))` }} key={`${table.title}-${index}`}>
          {table.columns.map((column) => <span key={column}>{String(row[column] ?? '')}</span>)}
        </div>
      ))}
    </div>
  )
}

function AssetsTable({ assets, onOpen }: { assets: AssetListItem[]; onOpen: (assetId: string) => void }) {
  return (
    <div className="assetsTable" aria-label="Company assets table">
      <div className="assetsTableHead">
        <span>Asset</span>
        <span>Type</span>
        <span>Location</span>
        <span>Criticality</span>
        <span>Health</span>
        <span>Risk</span>
        <span>Open WOs</span>
        <span>Supervisor</span>
      </div>
      {assets.map((asset) => (
        <div className="assetsTableRow" key={asset.id}>
          <button className="workOrderCellButton" type="button" onClick={() => onOpen(asset.id)}>
            <strong>{asset.name}</strong>
            <small>{asset.id}</small>
          </button>
          <span>{asset.asset_type}</span>
          <span>
            {asset.location_code}
            <small>{asset.area}</small>
          </span>
          <span>{asset.criticality}</span>
          <span>{asset.health_score}%</span>
          <span className={`riskBadge ${asset.risk_level}`}>{asset.risk_level}</span>
          <span>{asset.open_work_orders}</span>
          <span>{asset.supervisor}</span>
        </div>
      ))}
    </div>
  )
}

function AssetProfileFacts({ detail }: { detail: AssetDetail }) {
  const profile = detail.profile
  const facts = [
    ['Asset ID', profile.equipment_id],
    ['Type', profile.asset_type],
    ['Location', `${profile.location_code} · ${profile.location_name}`],
    ['System', profile.parent_system],
    ['Manufacturer', profile.manufacturer],
    ['Model', profile.model],
    ['Serial', profile.serial_number],
    ['Installed', profile.installed_at],
    ['Owner', profile.owner_team],
    ['Supervisor', profile.supervisor],
  ]
  return (
    <>
      <p>{profile.description}</p>
      <dl className="assetFactGrid">
        {facts.map(([label, value]) => (
          <span key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </span>
        ))}
      </dl>
    </>
  )
}

function AssetMetricTile({ metric, fallbackValue }: { metric?: AssetMetricSnapshot; fallbackValue?: number }) {
  if (!metric && fallbackValue === undefined) return null
  const label = metric?.label ?? 'Health'
  const value = metric?.value ?? fallbackValue ?? 0
  const unit = metric?.unit ?? '%'
  return (
    <section className="healthTile">
      <h2>{label}</h2>
      <strong>{Math.round(value)}{unit}</strong>
      <small>{metric?.detail ?? 'Computed from live health data.'}</small>
    </section>
  )
}

function AssetMetricGrid({ metrics }: { metrics: AssetMetricSnapshot[] }) {
  return (
    <div className="assetMetricGrid">
      {metrics.map((metric) => (
        <span className="assetMetric" key={metric.id}>
          <small>{metric.label}</small>
          <strong>{Math.round(metric.value)}{metric.unit}</strong>
          <em>{metric.status.replace('_', ' ')}</em>
          <p>{metric.detail}</p>
        </span>
      ))}
    </div>
  )
}

function AssetSubsystemList({ subsystems }: { subsystems: AssetSubsystem[] }) {
  return (
    <ol className="assetSubsystemList">
      {subsystems.map((subsystem) => (
        <li key={subsystem.id}>
          <strong>{subsystem.name}</strong>
          <span>{subsystem.component}</span>
          <small className={`riskBadge ${subsystem.condition === 'critical' ? 'critical' : subsystem.condition === 'degraded' ? 'high' : 'medium'}`}>
            {subsystem.condition}
          </small>
          <p>{subsystem.detail}</p>
        </li>
      ))}
    </ol>
  )
}

function MaintenanceEventTable({ events }: { events: MaintenanceEvent[] }) {
  if (!events.length) return <p className="emptyState">No maintenance history is available for this asset.</p>
  return (
    <div className="maintenanceEventTable" aria-label="Maintenance history table">
      <div className="maintenanceEventHead">
        <span>Date</span>
        <span>Issue</span>
        <span>Root cause</span>
        <span>Action</span>
        <span>Downtime</span>
      </div>
      {events.map((event) => (
        <div className="maintenanceEventRow" key={event.id}>
          <span>{formatDate(event.date)}</span>
          <span>{event.issue}</span>
          <span>{event.root_cause}</span>
          <span>{event.action}</span>
          <span>{event.downtime_hours}h</span>
        </div>
      ))}
    </div>
  )
}

function SignalLineChartCard({ chart }: { chart: AssetPerformanceChart }) {
  if (!chart.points.length) {
    return (
      <section className="detailPanel chartCard">
        <h2>{chart.title}</h2>
        <p className="emptyState">No performance readings are available for this signal.</p>
      </section>
    )
  }
  const values = chart.points.map((point) => point.value)
  const min = Math.min(...values, ...chart.points.map((point) => point.threshold))
  const max = Math.max(...values, ...chart.points.map((point) => point.threshold))
  const span = Math.max(1, max - min)
  const xStep = chart.points.length > 1 ? 300 / (chart.points.length - 1) : 300
  const path = chart.points
    .map((point, index) => {
      const x = 20 + index * xStep
      const y = 120 - ((point.value - min) / span) * 95
      return `${index === 0 ? 'M' : 'L'} ${x} ${y}`
    })
    .join(' ')
  const thresholdY = 120 - (((chart.points[0]?.threshold ?? min) - min) / span) * 95
  return (
    <section className="detailPanel chartCard">
      <h2>{chart.title}</h2>
      <svg viewBox="0 0 340 140" role="img" aria-label={`${chart.title} line chart`}>
        <path d="M20 120 H320" className="axis" />
        <path d="M20 20 V120" className="axis" />
        <path d={`M20 ${thresholdY} H320`} className="thresholdPath" />
        <path d={path} className="linePath" />
      </svg>
      <small>{chart.points.length} readings · {chart.unit}</small>
    </section>
  )
}

function ReliabilityMetricGrid({ metrics }: { metrics: AssetReliabilityMetric[] }) {
  return (
    <div className="assetMetricGrid reliabilityGrid">
      {metrics.map((metric) => (
        <span className="assetMetric" key={metric.id}>
          <small>{metric.metric_name}</small>
          <strong>{metric.value}{metric.unit}</strong>
          <em>{metric.status.replace('_', ' ')}</em>
          <p>{metric.detail}</p>
        </span>
      ))}
    </div>
  )
}

function AssetDocumentList({ documents }: { documents: AssetDocument[] }) {
  if (!documents.length) return <p className="emptyState">No documents are linked to this asset.</p>
  return (
    <div className="assetDocumentList">
      {documents.map((document) => (
        <article className="assetDocument" key={document.id}>
          <span className="rolePill">{document.source_type}</span>
          <h3>{document.title}</h3>
          <p>{document.excerpt}</p>
        </article>
      ))}
    </div>
  )
}

function KnowledgeEvidenceList({ evidence }: { evidence: AssetDetail['knowledge'] }) {
  if (!evidence.length) return <p className="emptyState">No retrieved evidence is available for this asset.</p>
  return (
    <div className="assetDocumentList">
      {evidence.map((item) => (
        <article className="assetDocument" key={item.source_id}>
          <span className="rolePill">{item.source_type}</span>
          <h3>{item.title}</h3>
          <p>{item.excerpt}</p>
          {item.relevance_reason && <small>{item.relevance_reason}</small>}
        </article>
      ))}
    </div>
  )
}

function WorkOrderTable({
  workOrders,
  onOpen,
  compact = false,
  canAssign = false,
  canApprove = false,
  canStart = false,
  technicians = [],
  onAssign,
  onApprove,
  onStart,
}: {
  workOrders: WorkOrder[]
  onOpen: (id: string) => void
  compact?: boolean
  canAssign?: boolean
  canApprove?: boolean
  canStart?: boolean
  technicians?: AuthUser[]
  onAssign?: (workOrderId: string, assignedTo: string) => void
  onApprove?: (workOrderId: string) => void
  onStart?: (workOrderId: string) => void
}) {
  return (
    <div className={`workOrderTable ${compact ? 'compact' : ''} ${canAssign && !compact ? 'assignable' : ''} ${canApprove ? 'approvable' : ''}`}>
      <div className="workOrderHead">
        <span>Work order</span>
        <span>Description</span>
        {!compact && <span>Recommended action</span>}
        <span>Status</span>
        <span>Asset</span>
        {canAssign && !compact && <span>Assigned to</span>}
      </div>
      {workOrders.map((order) => {
        const technicianOptions = technicians.some((technician) => technician.display_name === order.assigned_to)
          ? technicians
          : [
              {
                id: `current-${order.id}`,
                email: '',
                display_name: order.assigned_to,
                role: 'maintenance_technician' as UserRole,
                is_active: true,
              },
              ...technicians,
            ]
        const canApproveOrder = canApprove && order.status === 'WAPPR'
        const canStartOrder = canStart && ['APPR', 'WMATL'].includes(order.status)
        return (
          <div className="workOrderRow" key={order.id}>
            <button className="workOrderCellButton workOrderIdButton" type="button" onClick={() => onOpen(order.id)}>
              {order.id}
            </button>
            <button className="workOrderCellButton" type="button" onClick={() => onOpen(order.id)}>
              {order.title}
            </button>
            {!compact && <span>{order.recommended_action}</span>}
            <span className="workOrderStatusCell">
              <span>{order.status}</span>
              {canApproveOrder && (
                <button
                  aria-label={`Approve ${order.id}`}
                  className="miniActionButton"
                  type="button"
                  onClick={() => onApprove?.(order.id)}
                >
                  Approve
                </button>
              )}
              {canStartOrder && (
                <button
                  aria-label={`Start ${order.id}`}
                  className="miniActionButton"
                  type="button"
                  onClick={() => onStart?.(order.id)}
                >
                  Start work
                </button>
              )}
            </span>
            <span>{order.equipment_id}</span>
            {canAssign && !compact && (
              <select
                aria-label={`Assign ${order.id}`}
                value={order.assigned_to}
                onChange={(event) => onAssign?.(order.id, event.target.value)}
              >
                {technicianOptions.map((technician) => (
                  <option value={technician.display_name} key={`${order.id}-${technician.id}`}>
                    {technician.display_name}
                  </option>
                ))}
              </select>
            )}
          </div>
        )
      })}
    </div>
  )
}

function BarChart({ assets }: { assets: HealthSummary[] }) {
  return (
    <div className="barChart" aria-label="Equipment efficiency bar chart">
      {assets.map((item) => (
        <div className="barGroup" key={item.equipment.id}>
          <span style={{ height: `${Math.max(8, item.health_score)}%` }} />
          <small>{item.equipment.id.split('-')[0]}</small>
        </div>
      ))}
    </div>
  )
}

function MiniBars({ values }: { values: number[] }) {
  return (
    <div className="miniBars">
      {values.map((value, index) => (
        <span style={{ height: `${value}%` }} key={`${value}-${index}`} />
      ))}
    </div>
  )
}

function StatusTimeline({ status }: { status: string }) {
  const statuses = ['WAPPR', 'WMATL', 'APPR', 'INPRG', 'COMP', 'CLOSE']
  const activeIndex = Math.max(0, statuses.indexOf(status))
  return (
    <div className="statusTimeline" aria-label="Work order status">
      {statuses.map((item, index) => (
        <span className={index <= activeIndex ? 'active' : ''} key={item}>
          <i />
          {item}
        </span>
      ))}
    </div>
  )
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  } catch {
    return value
  }
}

function metricValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? `${value}` : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
  }
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return '0'
}

function clipText(value: string, limit: number) {
  const compact = value.replace(/\s+/g, ' ').trim()
  if (compact.length <= limit) return compact
  return `${compact.slice(0, limit - 1).trim()}…`
}
