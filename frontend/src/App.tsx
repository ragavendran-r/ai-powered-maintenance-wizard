import { useEffect, useMemo, useState } from 'react'
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
  MessageSquare,
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
  type AuthSession,
  type AuthUser,
  type DashboardSummary,
  type HealthSummary,
  type NeoChatResponse,
  type NeoTable,
  type Recommendation,
  type SupervisorAssistantResponse,
  type TechnicianAssistantResponse,
  type StreamingStatus,
  type UserRole,
  type WorkOrder,
  type WorkOrderCreateRequest,
} from './services/api'

const riskRank = { low: 1, medium: 2, high: 3, critical: 4 }
type AppView = 'dashboard' | 'asset' | 'workOrders' | 'ingestion' | 'users'
type AssetTab = 'summary' | 'maintenance' | 'performance' | 'reliability' | 'documents' | 'workOrders'

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
const feedbackRoles: UserRole[] = ['admin', 'maintenance_engineer', 'reliability_engineer']
const ingestionRoles: UserRole[] = ['admin', 'reliability_engineer']
const streamingRoles: UserRole[] = ['admin', 'reliability_engineer']

const fallbackWorkOrders: WorkOrder[] = [
  {
    id: 'WO-8304',
    equipment_id: 'RM-DRIVE-01',
    title: 'Inspect main drive bearing vibration',
    description: 'Inspect bearing housing, coupling alignment, lubrication condition, and foundation bolts.',
    status: 'INPRG',
    priority: 1,
    work_type: 'CM',
    failure_class: 'MECH',
    problem_code: 'BRGVIB',
    classification: 'Bearing vibration',
    assigned_to: 'Maintenance Engineer',
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
    status: 'APPR',
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
]

function hasRole(user: AuthUser | undefined, roles: UserRole[]) {
  return Boolean(user && roles.includes(user.role))
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

export function App() {
  const [session, setSession] = useState<AuthSession | null>(() => api.restoreSession())
  const [authReady, setAuthReady] = useState(false)
  const [loginEmail, setLoginEmail] = useState('admin@plant.local')
  const [loginPassword, setLoginPassword] = useState('DemoPass123!')
  const [authMessage, setAuthMessage] = useState('')
  const [dashboard, setDashboard] = useState<DashboardSummary>(fallbackDashboard)
  const [activeView, setActiveView] = useState<AppView>('dashboard')
  const [selectedEquipment, setSelectedEquipment] = useState('RM-DRIVE-01')
  const [assetTab, setAssetTab] = useState<AssetTab>('summary')
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null)
  const [workOrders, setWorkOrders] = useState<WorkOrder[]>(fallbackWorkOrders)
  const [selectedWorkOrderId, setSelectedWorkOrderId] = useState('WO-8304')
  const [workOrderMessage, setWorkOrderMessage] = useState('')
  const [technicianObservation, setTechnicianObservation] = useState('There are hotspots and looseness around the checked connections.')
  const [technicianAssistant, setTechnicianAssistant] = useState<TechnicianAssistantResponse | null>(null)
  const [technicianChat, setTechnicianChat] = useState<AssistantTurn[]>([
    {
      id: 'technician-welcome',
      role: 'assistant',
      content: 'Let’s start the work order. Do you observe any problems?',
    },
  ])
  const [supervisorQuestion, setSupervisorQuestion] = useState('Summarize follow-up actions for completed work orders.')
  const [supervisorAssistant, setSupervisorAssistant] = useState<SupervisorAssistantResponse | null>(null)
  const [supervisorChat, setSupervisorChat] = useState<AssistantTurn[]>([
    {
      id: 'supervisor-welcome',
      role: 'assistant',
      content: 'Ask me to summarize follow-ups, risks, or draft a follow-up work order.',
    },
  ])
  const [question, setQuestion] = useState('Why is the hot strip mill main drive vibrating?')
  const [answer, setAnswer] = useState('')
  const [neoQuestion, setNeoQuestion] = useState('Show work orders needing follow-up')
  const [neoTable, setNeoTable] = useState<NeoTable | null>(null)
  const [neoLoading, setNeoLoading] = useState(false)
  const [neoStreaming, setNeoStreaming] = useState(false)
  const [neoMessages, setNeoMessages] = useState<AssistantTurn[]>([
    {
      id: 'neo-welcome',
      role: 'assistant',
      content: 'I’m Neo. Ask me for assets, work orders, or users and I’ll update the dashboard table.',
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
  const [userMessage, setUserMessage] = useState('')
  const [newUserEmail, setNewUserEmail] = useState('')
  const [newUserName, setNewUserName] = useState('')
  const [newUserRole, setNewUserRole] = useState<UserRole>('operator')
  const [newUserPassword, setNewUserPassword] = useState('')
  const [resetUser, setResetUser] = useState<AuthUser | null>(null)
  const [resetPasswordValue, setResetPasswordValue] = useState('')

  const currentUser = session?.user
  const canDecision = hasRole(currentUser, decisionRoles)
  const canTechnicianAssistant = hasRole(currentUser, technicianAssistantRoles)
  const canSupervisorAssistant = hasRole(currentUser, supervisorAssistantRoles)
  const canFeedback = hasRole(currentUser, feedbackRoles)
  const canIngest = hasRole(currentUser, ingestionRoles)
  const canStreaming = hasRole(currentUser, streamingRoles)
  const canAdminUsers = currentUser?.role === 'admin'

  function clearSession(message = '') {
    api.setSession(null)
    setSession(null)
    setActiveView('dashboard')
    setRecommendation(null)
    setAnswer('')
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
        if (topAsset) setSelectedEquipment(topAsset.equipment.id)
      })
      .catch(() => setApiState('fallback'))
  }

  function loadUsers() {
    return api
      .users()
      .then((items) => setUsers(items))
      .catch(() => setUserMessage('Users could not be loaded'))
  }

  function loadWorkOrders() {
    return api
      .workOrders()
      .then((items) => {
        if (!Array.isArray(items)) {
          setWorkOrders(fallbackWorkOrders)
          return
        }
        setWorkOrders(items)
        if (items.length && !items.some((item) => item.id === selectedWorkOrderId)) {
          setSelectedWorkOrderId(items[0].id)
        }
      })
      .catch(() => setWorkOrders(fallbackWorkOrders))
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
      })
      .catch(() => clearSession('Session expired. Sign in again.'))
      .finally(() => setAuthReady(true))
    return () => api.onUnauthorized(null)
  }, [])

  useEffect(() => {
    if (!authReady || !session || session.user.role === 'iot_service') return
    loadDashboard()
    loadWorkOrders()
    if (canStreaming) loadStreamingStatus()
  }, [authReady, session?.user.id])

  useEffect(() => {
    if (activeView === 'ingestion' && canStreaming) loadStreamingStatus()
    if (activeView === 'ingestion' && !canIngest) setActiveView('dashboard')
    if (activeView === 'users' && !canAdminUsers) setActiveView('dashboard')
  }, [activeView, canIngest, canStreaming, canAdminUsers])

  useEffect(() => {
    if (activeView === 'users' && canAdminUsers) loadUsers()
  }, [activeView, canAdminUsers])

  const selectedHealth = useMemo(
    () => dashboard.highest_risk_equipment.find((item) => item.equipment.id === selectedEquipment) ?? dashboard.highest_risk_equipment[0],
    [dashboard, selectedEquipment],
  )
  const selectedWorkOrder = useMemo(
    () => workOrders.find((item) => item.id === selectedWorkOrderId) ?? workOrders[0],
    [selectedWorkOrderId, workOrders],
  )
  const assetWorkOrders = useMemo(
    () => workOrders.filter((item) => item.equipment_id === selectedEquipment),
    [selectedEquipment, workOrders],
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
    setActiveView('asset')
  }

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

  async function sendNeoQuestion() {
    if (neoLoading) return
    const prompt = neoQuestion.trim() || 'Show assets'
    const history = neoMessages.map((turn) => ({ role: turn.role, content: turn.content }))
    setNeoMessages((turns) => [
      ...turns,
      { id: assistantTurnId('neo-user'), role: 'user', content: prompt },
    ])
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
        return assistantMessageId
      }

      const updateAssistantMessage = (updates: Partial<AssistantTurn>) => {
        if (!assistantMessageId) return
        setNeoMessages((turns) => turns.map((turn) => (turn.id === assistantMessageId ? { ...turn, ...updates } : turn)))
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
          if (assistantMessageId) {
            const message = neoResponseMessage(event.response)
            updateAssistantMessage({
              content: message,
              details: event.response.table ? [`Updated table: ${event.response.table.title}`, `${event.response.table.rows.length} row(s)`] : undefined,
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
    return response.table
      ? `I found ${response.table.rows.length} row${response.table.rows.length === 1 ? '' : 's'} for ${response.table.title}. The table is updated in the dashboard.`
      : response.answer
  }

  function appendNeoResponse(response: NeoChatResponse) {
    const message = neoResponseMessage(response)
    setNeoMessages((turns) => [
      ...turns,
      {
        id: assistantTurnId('neo-assistant'),
        role: 'assistant',
        content: message,
        details: response.table ? [`Updated table: ${response.table.title}`, `${response.table.rows.length} row(s)`] : undefined,
        provider: response.provider,
        usedLiveProvider: response.used_live_provider,
      },
    ])
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

  async function runTechnicianAssistant() {
    if (!selectedWorkOrder) return
    const prompt = technicianObservation.trim() || 'Give me live directions for this work order.'
    setTechnicianChat((turns) => [
      ...turns,
      { id: assistantTurnId('technician-user'), role: 'user', content: prompt },
    ])
    try {
      const response = await api.technicianAssist(selectedWorkOrder.id, prompt)
      setTechnicianAssistant(response)
      setTechnicianChat((turns) => [
        ...turns,
        {
          id: assistantTurnId('technician-assistant'),
          role: 'assistant',
          content: response.next_prompt,
          details: [
            ...response.live_directions,
            ...response.recommendations,
            ...response.safety_reminders.map((item) => `Safety: ${item}`),
            `Problem code: ${response.suggested_problem_code}`,
            `Summary: ${response.completion_summary}`,
          ],
          provider: response.provider,
          usedLiveProvider: response.used_live_provider,
        },
      ])
      setTechnicianObservation('')
      setWorkOrderMessage('Technician assistant updated the recommended problem code and summary')
    } catch {
      const fallbackResponse = {
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
          details: [
            ...fallbackResponse.live_directions,
            ...fallbackResponse.recommendations,
            ...fallbackResponse.safety_reminders.map((item) => `Safety: ${item}`),
            `Problem code: ${fallbackResponse.suggested_problem_code}`,
            `Summary: ${fallbackResponse.completion_summary}`,
          ],
          provider: fallbackResponse.provider,
          usedLiveProvider: fallbackResponse.used_live_provider,
        },
      ])
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

  async function runSupervisorAssistant(workOrderId?: string) {
    const prompt = supervisorQuestion.trim() || 'Review follow-up status.'
    setSupervisorChat((turns) => [
      ...turns,
      { id: assistantTurnId('supervisor-user'), role: 'user', content: prompt },
    ])
    try {
      const response = await api.supervisorAssist({
        work_order_id: workOrderId,
        queue_name: 'follow_up',
        question: prompt,
      })
      setSupervisorAssistant(response)
      setSupervisorChat((turns) => [
        ...turns,
        {
          id: assistantTurnId('supervisor-assistant'),
          role: 'assistant',
          content: response.summary,
          details: [
            ...response.follow_up_actions,
            ...response.risks.map((item) => `Risk: ${item}`),
            ...(response.draft_work_order ? [`Draft work order: ${response.draft_work_order.title}`] : []),
          ],
          provider: response.provider,
          usedLiveProvider: response.used_live_provider,
        },
      ])
      setSupervisorQuestion('')
      setWorkOrderMessage('Supervisor assistant reviewed follow-ups')
    } catch {
      const fallbackResponse = {
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
          details: [
            ...fallbackResponse.follow_up_actions,
            ...fallbackResponse.risks.map((item) => `Risk: ${item}`),
          ],
          provider: fallbackResponse.provider,
          usedLiveProvider: fallbackResponse.used_live_provider,
        },
      ])
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
    <div className="recommendationSection">
      <div className="sectionHeader">
        <CheckCircle2 size={18} />
        <h2>Recommendation</h2>
      </div>
      {recommendation ? (
        <>
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
            <button className="textButton" onClick={() => createWorkOrderFromContext(recommendation)}>
              <Briefcase size={16} />
              Create Work Order
            </button>
          </div>
          {reportMessage && <p className="inlineStatus">{reportMessage}</p>}
        </>
      ) : (
        <p className="emptyState">Run diagnosis or ask a question to generate cited maintenance actions.</p>
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
            <div className="neoTranscript" aria-label="Neo chat transcript">
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
          <section className="detailPanel quickActionsPanel">
            <h2>Quick actions</h2>
            <button className="textButton" onClick={() => createWorkOrderFromContext()}>
              <Briefcase size={16} />
              Create work order
            </button>
            {canSupervisorAssistant && (
              <button className="textButton" onClick={() => runSupervisorAssistant()}>
                <Bot size={16} />
                Review follow-ups
              </button>
            )}
          </section>
        </div>
      </div>
    </section>
  )

  const assetDetailView = (
    <section className="assetDetailGrid">
      <div className="pageHeader">
        <p className="breadcrumb">Operational dashboard / Assets /</p>
        <h1>{selectedHealth?.equipment.name}</h1>
        <span>Last updated from live maintenance data</span>
      </div>
      <div className="tabRow">
        {(['summary', 'maintenance', 'performance', 'reliability', 'documents', 'workOrders'] as AssetTab[]).map((tab) => (
          <button className={assetTab === tab ? 'selected' : ''} onClick={() => setAssetTab(tab)} key={tab}>
            {tab === 'workOrders' ? 'Work Orders' : tab[0].toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>
      <section className="detailPanel performanceInsights">
        <div className="sectionHeader">
          <Sparkles size={18} />
          <h2>Performance insights</h2>
        </div>
        <div className="insightHero">
          <span>Risk</span>
          <strong>{100 - (selectedHealth?.health_score ?? 0)}%</strong>
          <small>Probable cause</small>
          <h2>{selectedHealth?.active_alerts[0]?.message ?? selectedHealth?.notes[0]}</h2>
        </div>
        <button className="outlineButton" onClick={runDiagnosis}>View data</button>
      </section>
      <section className="detailPanel">
        <h2>Recommended actions</h2>
        <ol className="actionList">
          {(recommendation?.immediate_actions ?? selectedHealth?.notes ?? []).slice(0, 3).map((action) => (
            <li key={action}>{action}</li>
          ))}
        </ol>
        <button className="outlineButton" onClick={() => createWorkOrderFromContext(recommendation ?? undefined)}>
          Create work order
        </button>
      </section>
      <section className="healthStack">
        <HealthTile label="Health" value={selectedHealth?.health_score ?? 0} />
        <HealthTile label="Efficiency" value={Math.max(0, (selectedHealth?.health_score ?? 0) - 4)} />
      </section>
      <section className="detailPanel">
        <h2>Maintenance history</h2>
        <WorkOrderTable workOrders={assetWorkOrders} compact onOpen={(id) => { setSelectedWorkOrderId(id); setActiveView('workOrders') }} />
      </section>
      <LineChartCard title="Primary signal trend" health={selectedHealth} />
      <LineChartCard title="Secondary signal trend" health={selectedHealth} />
      <section className="detailPanel assetVisual">
        <h2>Sub-systems</h2>
        <ol>
          <li>Drive train and coupling</li>
          <li>Bearing housing and lubrication</li>
          <li>Control and protection signals</li>
        </ol>
      </section>
      <section className="detailPanel">
        <h2>{assetTab === 'documents' ? 'Knowledge Retrieval' : 'Asset Context'}</h2>
        <p>{selectedHealth?.notes.join(' ')}</p>
        <ul>{selectedHealth?.top_spares_constraints.map((spare) => <li key={spare.id}>{spare.name}: {spare.available_qty} stock</li>)}</ul>
      </section>
      {canDecision && (
        <section className="detailPanel assistantPanelWide">
          <div className="diagnoseActionRow">
            <button className="textButton" onClick={runDiagnosis}>
              <CheckCircle2 size={16} />
              Diagnose
            </button>
          </div>
          <div className="chatPanel">
            <div className="sectionHeader">
              <MessageSquare size={18} />
              <h2>Engineer Query</h2>
            </div>
            <div className="queryRow">
              <textarea aria-label="Engineer question" rows={3} value={question} onChange={(event) => setQuestion(event.target.value)} />
              <button onClick={sendQuestion} title="Ask maintenance wizard">
                <Send size={18} />
                <span>Send</span>
              </button>
            </div>
            {answer && <p className="answer">{answer}</p>}
          </div>
          {recommendationPanel}
        </section>
      )}
    </section>
  )

  const workOrdersView = (
    <section className="workOrderLayout">
      <section className="detailPanel">
        <div className="sectionHeader">
          <Briefcase size={18} />
          <h2>WOs with follow up actions</h2>
        </div>
        <WorkOrderTable workOrders={workOrders} onOpen={(id) => setSelectedWorkOrderId(id)} />
        {workOrderMessage && <p className="inlineStatus">{workOrderMessage}</p>}
      </section>
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
            <div className={canTechnicianAssistant && canSupervisorAssistant ? 'assistantSplit' : 'assistantSplit singleAssistant'}>
              {canTechnicianAssistant && (
                <section className="assistantBox technician">
                  <div className="sectionHeader">
                    <Bot size={18} />
                    <div>
                      <h2>Technician AI Assistant</h2>
                      <small>LLM work-order guidance for assigned technicians</small>
                    </div>
                  </div>
                  <div className="assistantTranscript" aria-label="Technician assistant chat">
                    {technicianChat.map((turn) => (
                      <div className={`chatBubble ${turn.role}`} key={turn.id}>
                        <span>{turn.role === 'assistant' ? 'Assistant' : 'You'}</span>
                        {turn.provider && <small>{turn.usedLiveProvider ? 'Live LLM' : 'LLM fallback'} · {turn.provider}</small>}
                        <AssistantMessageContent turn={turn} />
                        {turn.details && <ul>{turn.details.map((item) => <li key={item}>{item}</li>)}</ul>}
                      </div>
                    ))}
                  </div>
                  <form className="assistantComposer" onSubmit={(event) => {
                    event.preventDefault()
                    runTechnicianAssistant()
                  }}>
                    <textarea
                      aria-label="Technician observation"
                      value={technicianObservation}
                      onChange={(event) => setTechnicianObservation(event.target.value)}
                    />
                    <button className="textButton" type="submit">
                      <Send size={16} />
                      Send
                    </button>
                    <button className="textButton" type="button" onClick={completeSelectedWorkOrder}>Submit completed work</button>
                  </form>
                </section>
              )}
              {canSupervisorAssistant && (
                <section className="assistantBox supervisor">
                  <div className="sectionHeader">
                    <Bot size={18} />
                    <div>
                      <h2>Supervisor AI Assistant</h2>
                      <small>LLM follow-up review for maintenance supervisors</small>
                    </div>
                  </div>
                  <div className="assistantTranscript" aria-label="Supervisor assistant chat">
                    {supervisorChat.map((turn) => (
                      <div className={`chatBubble ${turn.role}`} key={turn.id}>
                        <span>{turn.role === 'assistant' ? 'Assistant' : 'You'}</span>
                        {turn.provider && <small>{turn.usedLiveProvider ? 'Live LLM' : 'LLM fallback'} · {turn.provider}</small>}
                        <AssistantMessageContent turn={turn} />
                        {turn.details && <ul>{turn.details.map((item) => <li key={item}>{item}</li>)}</ul>}
                      </div>
                    ))}
                  </div>
                  <form className="assistantComposer" onSubmit={(event) => {
                    event.preventDefault()
                    runSupervisorAssistant(selectedWorkOrder.id)
                  }}>
                    <textarea
                      aria-label="Supervisor question"
                      value={supervisorQuestion}
                      onChange={(event) => setSupervisorQuestion(event.target.value)}
                    />
                    <button className="textButton" type="submit">
                      <Send size={16} />
                      Send
                    </button>
                  </form>
                </section>
              )}
              {!canTechnicianAssistant && !canSupervisorAssistant && (
                <section className="assistantBox">
                  <p className="emptyState">Role-specific AI assistants are available to technician and supervisor accounts.</p>
                </section>
              )}
            </div>
          </>
        ) : (
          <p className="emptyState">Select a work order to review.</p>
        )}
      </section>
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
        ) : activeView === 'asset' ? (
          assetDetailView
        ) : activeView === 'workOrders' ? (
          workOrdersView
        ) : activeView === 'ingestion' ? (
          ingestionView
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

function WorkOrderTable({
  workOrders,
  onOpen,
  compact = false,
}: {
  workOrders: WorkOrder[]
  onOpen: (id: string) => void
  compact?: boolean
}) {
  return (
    <div className={`workOrderTable ${compact ? 'compact' : ''}`}>
      <div className="workOrderHead">
        <span>Work order</span>
        <span>Description</span>
        {!compact && <span>Recommended action</span>}
        <span>Status</span>
        <span>Asset</span>
      </div>
      {workOrders.map((order) => (
        <button className="workOrderRow" onClick={() => onOpen(order.id)} key={order.id}>
          <strong>{order.id}</strong>
          <span>{order.title}</span>
          {!compact && <span>{order.recommended_action}</span>}
          <span>{order.status}</span>
          <span>{order.equipment_id}</span>
        </button>
      ))}
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

function HealthTile({ label, value }: { label: string; value: number }) {
  return (
    <section className="healthTile">
      <h2>{label}</h2>
      <strong>{value}%</strong>
      <small>{value < 70 ? 'Under target' : 'On target'}</small>
    </section>
  )
}

function LineChartCard({ title, health }: { title: string; health?: HealthSummary }) {
  const points = (health?.anomalies.length ? health.anomalies : []).slice(0, 8)
  const values = points.length ? points.map((item) => Math.min(100, Math.max(5, item.value))) : [42, 48, 45, 55, 52, 60, 58, 70]
  const path = values
    .map((value, index) => `${index === 0 ? 'M' : 'L'} ${20 + index * 42} ${120 - value}`)
    .join(' ')
  return (
    <section className="detailPanel chartCard">
      <h2>{title}</h2>
      <svg viewBox="0 0 340 140" role="img" aria-label={`${title} line chart`}>
        <path d="M20 120 H320" className="axis" />
        <path d="M20 20 V120" className="axis" />
        <path d={path} className="linePath" />
      </svg>
    </section>
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
