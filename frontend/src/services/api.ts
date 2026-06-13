export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type UserRole =
  | 'admin'
  | 'maintenance_engineer'
  | 'maintenance_technician'
  | 'maintenance_supervisor'
  | 'reliability_engineer'
  | 'planner'
  | 'operator'
  | 'iot_service'

export interface AuthUser {
  id: string
  email: string
  display_name: string
  role: UserRole
  is_active: boolean
  created_at?: string | null
  updated_at?: string | null
  last_login_at?: string | null
}

export interface AuthSession {
  accessToken: string
  user: AuthUser
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export interface Equipment {
  id: string
  name: string
  area: string
  process: string
  criticality: number
  status: string
}

export interface AssetProfile {
  equipment_id: string
  name: string
  area: string
  process: string
  criticality: number
  status: string
  asset_type: string
  location_code: string
  location_name: string
  parent_system: string
  manufacturer: string
  model: string
  serial_number: string
  installed_at: string
  owner_team: string
  supervisor: string
  description: string
  last_updated: string
}

export interface AssetMetricSnapshot {
  id: string
  equipment_id: string
  metric_key: string
  label: string
  value: number
  unit: string
  target_value?: number | null
  status: string
  trend: string
  detail: string
  captured_at: string
  sort_order: number
}

export interface AssetRecommendation {
  id: string
  equipment_id: string
  action_type: string
  title: string
  description: string
  priority: number
  source: string
  created_at: string
  sort_order: number
}

export interface AssetSubsystem {
  id: string
  equipment_id: string
  name: string
  component: string
  condition: string
  detail: string
  sort_order: number
}

export interface AssetReliabilityMetric {
  id: string
  equipment_id: string
  metric_name: string
  value: number
  unit: string
  target_value?: number | null
  status: string
  trend: string
  detail: string
  sort_order: number
}

export interface Alert {
  id: string
  equipment_id: string
  timestamp: string
  signal: string
  value: number
  unit: string
  threshold: number
  severity: RiskLevel
  message: string
}

export interface Evidence {
  source_type: string
  source_id: string
  title: string
  excerpt: string
  equipment_id?: string
  timestamp?: string
  relevance_reason?: string | null
}

export interface SparePart {
  id: string
  equipment_id: string
  name: string
  available_qty: number
  lead_time_days: number
  criticality: number
}

export interface AnomalyFinding {
  equipment_id: string
  signal: string
  timestamp: string
  value: number
  unit: string
  baseline_mean: number
  z_score: number
  threshold: number
  threshold_breached: boolean
  trend_delta: number
  risk_level: RiskLevel
  explanation: string
  context_class?: string | null
  context_rationale?: string | null
  recommended_inspection_steps?: string[]
}

export interface ReasoningExplanation {
  subject_type: 'prediction' | 'anomaly' | 'recommendation' | 'retrieval'
  summary: string
  driver_explanations: string[]
  cautions: string[]
  recommended_next_steps: string[]
  used_live_provider: boolean
  provider: string
}

export interface HealthSummary {
  equipment: Equipment
  risk_level: RiskLevel
  health_score: number
  active_alerts: Alert[]
  anomalies: AnomalyFinding[]
  top_spares_constraints: SparePart[]
  notes: string[]
}

export interface MaintenanceEvent {
  id: string
  equipment_id: string
  date: string
  issue: string
  root_cause: string
  action: string
  downtime_hours: number
}

export interface DashboardSummary {
  equipment_count: number
  active_alert_count: number
  critical_alert_count: number
  average_health_score: number
  highest_risk_equipment: HealthSummary[]
}

export interface Recommendation {
  id: string
  equipment_id: string
  diagnosis: string
  probable_root_causes: string[]
  risk_level: RiskLevel
  urgency: string
  remaining_useful_life_days: number | null
  confidence: number
  immediate_actions: string[]
  planned_actions: string[]
  spares_strategy: string[]
  evidence: Evidence[]
  learning_notes: string[]
  reasoning_explanation?: ReasoningExplanation | null
  used_live_provider: boolean
  provider: string
  report_summary: string
}

export interface PredictionResponse {
  equipment_id: string
  risk_level: RiskLevel
  failure_probability: number
  remaining_useful_life_days: number
  drivers: string[]
  reasoning_explanation?: ReasoningExplanation | null
}

export interface AssetDocument {
  id: string
  source_type: string
  equipment_id?: string | null
  title: string
  excerpt: string
}

export interface AssetPerformancePoint {
  timestamp: string
  value: number
  threshold: number
}

export interface AssetPerformanceChart {
  signal: string
  title: string
  unit: string
  points: AssetPerformancePoint[]
}

export interface AssetListItem {
  id: string
  name: string
  asset_type: string
  area: string
  process: string
  location_code: string
  location_name: string
  criticality: number
  status: string
  health_score: number
  risk_level: RiskLevel
  active_alerts: number
  open_work_orders: number
  supervisor: string
  last_updated: string
}

export type AssetDetailSection = 'summary' | 'maintenance' | 'performance' | 'reliability' | 'documents' | 'work_orders'

export interface AssetDetail {
  profile: AssetProfile
  health: HealthSummary
  metrics: AssetMetricSnapshot[]
  recommendations: AssetRecommendation[]
  maintenance_events: MaintenanceEvent[]
  work_orders: WorkOrder[]
  subsystems: AssetSubsystem[]
  reliability_metrics: AssetReliabilityMetric[]
  performance_charts: AssetPerformanceChart[]
  documents: AssetDocument[]
  knowledge: Evidence[]
  prediction: PredictionResponse | null
}

export type AssetReliabilityPredictionStreamEvent =
  | { type: 'meta'; provider: string; used_live_provider: boolean }
  | { type: 'token'; content: string }
  | { type: 'done'; answer: string; prediction: PredictionResponse; provider: string; used_live_provider: boolean }
  | { type: 'error'; message: string; provider: string; used_live_provider: false }

export interface ChatResponse {
  answer: string
  recommendation: Recommendation
  evidence: Evidence[]
}

export type DiagnosisStreamEvent =
  | { type: 'meta'; provider: string; used_live_provider: boolean }
  | { type: 'token'; content: string }
  | { type: 'done'; recommendation: Recommendation }
  | { type: 'error'; message: string }

export interface NeoTable {
  title: string
  columns: string[]
  rows: Record<string, string | number | boolean | null>[]
}

export interface NeoAction {
  type: string
  label: string
  status: 'completed' | 'blocked' | 'not_allowed' | 'not_found'
  target_id?: string | null
  detail?: string | null
}

export interface NeoChatResponse {
  answer: string
  table?: NeoTable | null
  action?: NeoAction | null
  used_live_provider: boolean
  provider: string
}

export type NeoStreamEvent =
  | { type: 'meta'; provider: string; used_live_provider: boolean }
  | { type: 'token'; content: string }
  | { type: 'done'; response: NeoChatResponse }

export type AssistantStreamEvent<TResponse> =
  | { type: 'meta'; provider: string; used_live_provider: boolean }
  | { type: 'token'; content: string }
  | { type: 'done'; response: TResponse }

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
const AUTH_SESSION_KEY = 'maintenance_wizard_auth_session'

let authSession: AuthSession | null = loadStoredSession()
let unauthorizedHandler: (() => void) | null = null

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function loadStoredSession(): AuthSession | null {
  try {
    const value = window.sessionStorage.getItem(AUTH_SESSION_KEY)
    return value ? (JSON.parse(value) as AuthSession) : null
  } catch {
    return null
  }
}

export function storeSession(session: AuthSession | null) {
  authSession = session
  if (!session) {
    window.sessionStorage.removeItem(AUTH_SESSION_KEY)
    return
  }
  window.sessionStorage.setItem(AUTH_SESSION_KEY, JSON.stringify(session))
}

export function setUnauthorizedHandler(handler: (() => void) | null) {
  unauthorizedHandler = handler
}

function authHeaders(): Record<string, string> {
  if (!authSession?.accessToken) return {}
  return { Authorization: `Bearer ${authSession.accessToken}` }
}

async function request<T>(path: string, init?: RequestInit, includeAuth = true): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(includeAuth ? authHeaders() : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    if (response.status === 401 && includeAuth) unauthorizedHandler?.()
    throw new ApiError(response.status, `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function formRequest<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: authHeaders(),
    body,
  })
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.()
    throw new ApiError(response.status, `Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

async function textRequest(path: string): Promise<string> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.()
    throw new ApiError(response.status, `Request failed: ${response.status}`)
  }
  return response.text()
}

async function streamRequest<TEvent>(
  path: string,
  init: RequestInit,
  onEvent: (event: TEvent) => void,
): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...authHeaders(),
      ...(init.headers ?? {}),
    },
    ...init,
  })
  if (!response.ok) {
    if (response.status === 401) unauthorizedHandler?.()
    throw new ApiError(response.status, `Request failed: ${response.status}`)
  }
  if (!response.body) throw new ApiError(response.status, 'Streaming response body is unavailable')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    buffer = flushSseBuffer(buffer, onEvent)
  }
  buffer += decoder.decode()
  flushSseBuffer(`${buffer}\n\n`, onEvent)
}

function flushSseBuffer<TEvent>(buffer: string, onEvent: (event: TEvent) => void): string {
  let remaining = buffer
  let boundary = remaining.indexOf('\n\n')
  while (boundary !== -1) {
    const rawEvent = remaining.slice(0, boundary)
    remaining = remaining.slice(boundary + 2)
    const data = rawEvent
      .split('\n')
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n')
    if (data) onEvent(JSON.parse(data) as TEvent)
    boundary = remaining.indexOf('\n\n')
  }
  return remaining
}

export interface DocumentIngestResponse {
  status: string
  documents: number
  document?: {
    id: string
    source_type: string
    equipment_id?: string
    title: string
    content: string
  }
  intelligence?: DocumentIntelligence[]
}

export interface RecordIngestResponse {
  status: string
  counts: Record<string, number>
}

export interface StreamingStatus {
  enabled: boolean
  state: 'disabled' | 'disconnected' | 'connected' | 'error'
  broker: string
  stream: string
  consumer: string
  subjects: string[]
  processed_count: number
  failed_count: number
  last_message_timestamp?: string
  last_error?: string
}

export interface DocumentIntelligence {
  document_id: string
  summary: string
  asset_ids: string[]
  components: string[]
  failure_modes: string[]
  symptoms: string[]
  safety_constraints: string[]
  spares: string[]
  thresholds: string[]
  used_live_provider: boolean
  provider: string
}

export interface MaintenanceLabel {
  source_type: 'maintenance_event' | 'feedback'
  source_id: string
  equipment_id?: string | null
  failure_mode: string
  component: string
  root_cause: string
  action_class: string
  outcome_status: string
  signal_hints: string[]
  usable_for_training: boolean
  used_live_provider: boolean
  provider: string
}

export interface MaintenanceLabelsResponse {
  equipment_id?: string | null
  labels: MaintenanceLabel[]
}

export interface LearningExample {
  id: string
  source_type: string
  source_id: string
  equipment_id?: string | null
  work_order_id?: string | null
  instruction: string
  input_text: string
  expected_output: string
  metadata: Record<string, unknown>
  approved: boolean
  judge_score: number
  judge_label: string
  judge_rationale?: string | null
  judge_provider: string
  judge_used_live_provider: boolean
  judged_at?: string | null
  created_at: string
}

export interface LearningDatasetSnapshot {
  id: string
  name: string
  description?: string | null
  example_count: number
  approved_only: boolean
  jsonl_content: string
  created_by?: string | null
  created_at: string
}

export interface LearningModelVersion {
  id: string
  provider: string
  model_name: string
  base_model?: string | null
  adapter_path?: string | null
  status: string
  notes?: string | null
  created_at: string
}

export interface LearningPromptVersion {
  id: string
  assistant: string
  version: string
  prompt: string
  status: string
  notes?: string | null
  created_at: string
}

export interface LearningEvaluationRun {
  id: string
  dataset_id?: string | null
  model_version_id?: string | null
  prompt_version_id?: string | null
  metrics: Record<string, unknown>
  notes?: string | null
  passed: boolean
  created_at: string
}

export interface LearningJob {
  id: string
  job_type: string
  subject: string
  status: 'queued' | 'published' | 'running' | 'completed' | 'failed'
  requested_by?: string | null
  correlation_id: string
  input_refs: Record<string, unknown>
  output_refs: Record<string, unknown>
  error?: string | null
  retry_count: number
  created_at: string
  updated_at: string
}

export interface LearningArtifact {
  id: string
  job_id: string
  artifact_type: string
  uri: string
  content_hash: string
  metadata: Record<string, unknown>
  created_at: string
}

export interface LearningSummary {
  counts: Record<string, number>
  recent_examples: LearningExample[]
  recent_snapshots: LearningDatasetSnapshot[]
  model_versions: LearningModelVersion[]
  prompt_versions: LearningPromptVersion[]
  evaluation_runs: LearningEvaluationRun[]
  recent_jobs: LearningJob[]
  recent_artifacts: LearningArtifact[]
  vector_store: {
    store?: string
    enabled?: boolean
    collection?: string
    url?: string
    state?: string
    error?: string | null
  }
}

export type WorkOrderStatus = 'WAPPR' | 'WMATL' | 'APPR' | 'INPRG' | 'COMP' | 'CLOSE'

export interface WorkOrderLog {
  id: number
  work_order_id: string
  author: string
  entry_type: string
  content: string
  created_at: string
}

export interface WorkOrder {
  id: string
  equipment_id: string
  title: string
  description: string
  status: WorkOrderStatus
  priority: number
  work_type: string
  failure_class: string
  problem_code: string
  classification: string
  assigned_to: string
  supervisor: string
  due_date: string
  recommended_action: string
  follow_up_required: boolean
  ai_summary?: string | null
  completion_summary?: string | null
  created_at: string
  updated_at: string
  completed_at?: string | null
  logs: WorkOrderLog[]
}

export interface WorkOrderCreateRequest {
  equipment_id: string
  title: string
  description: string
  priority: number
  work_type: string
  failure_class: string
  problem_code: string
  classification: string
  assigned_to: string
  supervisor: string
  due_date: string
  recommended_action: string
  follow_up_required?: boolean
  ai_summary?: string
}

export interface TechnicianAssistantResponse {
  work_order_id: string
  next_prompt: string
  live_directions: string[]
  recommendations: string[]
  safety_reminders: string[]
  suggested_problem_code: string
  suggested_failure_class: string
  completion_summary: string
  evidence: Evidence[]
  used_live_provider: boolean
  provider: string
}

export interface SupervisorAssistantResponse {
  summary: string
  follow_up_actions: string[]
  risks: string[]
  draft_work_order?: WorkOrderCreateRequest | null
  referenced_work_orders: string[]
  used_live_provider: boolean
  provider: string
}

export interface UserCreateRequest {
  email: string
  display_name: string
  role: UserRole
  password: string
  is_active?: boolean
}

export interface UserUpdateRequest {
  display_name?: string
  role?: UserRole
  is_active?: boolean
}

export const api = {
  restoreSession: () => authSession,
  setSession: storeSession,
  onUnauthorized: setUnauthorizedHandler,
  login: (email: string, password: string) =>
    request<LoginResponse>(
      '/api/auth/login',
      {
        method: 'POST',
        body: JSON.stringify({ email, password }),
      },
      false,
    ),
  me: () => request<AuthUser>('/api/auth/me'),
  logout: () => request<{ status: string }>('/api/auth/logout', { method: 'POST' }),
  users: () => request<AuthUser[]>('/api/users'),
  technicians: () => request<AuthUser[]>('/api/users/technicians'),
  createUser: (payload: UserCreateRequest) =>
    request<AuthUser>('/api/users', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateUser: (userId: string, payload: UserUpdateRequest) =>
    request<AuthUser>(`/api/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  resetUserPassword: (userId: string, password: string) =>
    request<AuthUser>(`/api/users/${userId}/reset-password`, {
      method: 'POST',
      body: JSON.stringify({ password }),
    }),
  equipment: () => request<Equipment[]>('/api/equipment'),
  assets: () => request<AssetListItem[]>('/api/assets'),
  assetDetail: (equipmentId: string, sections: AssetDetailSection[] = ['summary']) =>
    request<AssetDetail>(`/api/assets/${equipmentId}?sections=${encodeURIComponent(sections.join(','))}`),
  assetReliabilityPredictionStream: (
    equipmentId: string,
    onEvent: (event: AssetReliabilityPredictionStreamEvent) => void,
  ) =>
    streamRequest<AssetReliabilityPredictionStreamEvent>(
      `/api/assets/${equipmentId}/reliability/stream`,
      { method: 'GET' },
      onEvent,
    ),
  dashboard: () => request<DashboardSummary>('/api/dashboard/summary'),
  streamingStatus: () => request<StreamingStatus>('/api/streaming/status'),
  health: (equipmentId: string) => request<HealthSummary>(`/api/equipment/${equipmentId}/health`),
  alerts: () => request<Alert[]>('/api/alerts'),
  diagnose: (equipmentId: string, alertId?: string) =>
    request<Recommendation>('/api/diagnose', {
      method: 'POST',
      body: JSON.stringify({ equipment_id: equipmentId, alert_id: alertId }),
    }),
  diagnoseStream: (equipmentId: string, alertId: string | undefined, onEvent: (event: DiagnosisStreamEvent) => void) =>
    streamRequest<DiagnosisStreamEvent>(
      '/api/diagnose/stream',
      {
        method: 'POST',
        body: JSON.stringify({ equipment_id: equipmentId, alert_id: alertId }),
      },
      onEvent,
    ),
  chat: (equipmentId: string, message: string) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ equipment_id: equipmentId, message }),
    }),
  neoWelcome: () => request<NeoChatResponse>('/api/neo/welcome'),
  neoChat: (message: string, history: { role: 'user' | 'assistant'; content: string }[] = []) =>
    request<NeoChatResponse>('/api/neo/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history }),
    }),
  neoChatStream: (
    message: string,
    history: { role: 'user' | 'assistant'; content: string }[] = [],
    onEvent: (event: NeoStreamEvent) => void,
  ) =>
    streamRequest<NeoStreamEvent>(
      '/api/neo/chat/stream',
      {
        method: 'POST',
        body: JSON.stringify({ message, history }),
      },
      onEvent,
    ),
  ingestDocumentFile: (input: { file: File; sourceType: string; equipmentId?: string; title?: string }) => {
    const body = new FormData()
    body.append('file', input.file)
    body.append('source_type', input.sourceType)
    if (input.equipmentId) body.append('equipment_id', input.equipmentId)
    if (input.title) body.append('title', input.title)
    return formRequest<DocumentIngestResponse>('/api/ingest/document-file', body)
  },
  ingestDocuments: (documents: unknown[]) =>
    request<DocumentIngestResponse>('/api/ingest/documents', {
      method: 'POST',
      body: JSON.stringify({ documents }),
    }),
  ingestRecords: (payload: unknown) =>
    request<RecordIngestResponse>('/api/ingest/records', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  documentIntelligence: (equipmentId: string) =>
    request<DocumentIntelligence[]>(`/api/equipment/${equipmentId}/document-intelligence`),
  maintenanceLabels: (equipmentId: string) =>
    request<MaintenanceLabelsResponse>(`/api/equipment/${equipmentId}/maintenance-labels`),
  generateMaintenanceLabels: (equipmentId: string) =>
    request<MaintenanceLabelsResponse>(`/api/equipment/${equipmentId}/maintenance-labels`, {
      method: 'POST',
    }),
  learningSummary: () => request<LearningSummary>('/api/learning/summary'),
  refreshLearningExamples: () =>
    request<LearningExample[]>('/api/learning/examples/refresh', {
      method: 'POST',
    }),
  learningExamples: (approvedOnly?: boolean) => {
    const query = typeof approvedOnly === 'boolean' ? `?approved_only=${approvedOnly ? 'true' : 'false'}` : ''
    return request<LearningExample[]>(`/api/learning/examples${query}`)
  },
  updateLearningExample: (exampleId: string, approved: boolean) =>
    request<LearningExample>(`/api/learning/examples/${exampleId}`, {
      method: 'PATCH',
      body: JSON.stringify({ approved }),
    }),
  createLearningDataset: (payload: { name: string; description?: string; approved_only?: boolean; min_judge_score?: number }) =>
    request<LearningDatasetSnapshot>('/api/learning/datasets', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  learningDatasets: () => request<LearningDatasetSnapshot[]>('/api/learning/datasets'),
  learningDatasetJsonl: (datasetId: string) => textRequest(`/api/learning/datasets/${datasetId}/jsonl`),
  judgeLearningExample: (exampleId: string) =>
    request<LearningExample>(`/api/learning/examples/${exampleId}/judge`, {
      method: 'POST',
    }),
  registerLearningModelVersion: (payload: {
    provider: string
    model_name: string
    base_model?: string
    adapter_path?: string
    status?: string
    notes?: string
  }) =>
    request<LearningModelVersion>('/api/learning/model-versions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  runLearningEvaluation: (payload: {
    dataset_id: string
    model_version_id: string
    prompt_version_id: string
    min_quality_score?: number
    notes?: string
  }) =>
    request<LearningEvaluationRun>('/api/learning/evaluations', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  learningEvaluations: () => request<LearningEvaluationRun[]>('/api/learning/evaluations'),
  learningJobs: () => request<LearningJob[]>('/api/learning/jobs'),
  queueLearningPeftJob: (payload: {
    dataset_id: string
    model_version_id: string
    prompt_version_id: string
    adapter_name?: string
    base_model?: string
    training_config?: Record<string, unknown>
    notes?: string
  }) =>
    request<LearningJob>('/api/learning/jobs/peft', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  workOrders: (equipmentId?: string, followUpOnly = false) => {
    const params = new URLSearchParams()
    if (equipmentId) params.set('equipment_id', equipmentId)
    if (followUpOnly) params.set('follow_up_only', 'true')
    const query = params.toString()
    return request<WorkOrder[]>(`/api/work-orders${query ? `?${query}` : ''}`)
  },
  workOrder: (workOrderId: string) => request<WorkOrder>(`/api/work-orders/${workOrderId}`),
  createWorkOrder: (payload: WorkOrderCreateRequest) =>
    request<WorkOrder>('/api/work-orders', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateWorkOrder: (workOrderId: string, payload: Partial<WorkOrder>) =>
    request<WorkOrder>(`/api/work-orders/${workOrderId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  addWorkOrderLog: (workOrderId: string, payload: { author: string; entry_type: string; content: string }) =>
    request<WorkOrder>(`/api/work-orders/${workOrderId}/logs`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  technicianAssist: (workOrderId: string, observation?: string) =>
    request<TechnicianAssistantResponse>('/api/work-orders/technician-assist', {
      method: 'POST',
      body: JSON.stringify({ work_order_id: workOrderId, observation }),
    }),
  technicianAssistStream: (
    workOrderId: string,
    observation: string | undefined,
    onEvent: (event: AssistantStreamEvent<TechnicianAssistantResponse>) => void,
  ) =>
    streamRequest<AssistantStreamEvent<TechnicianAssistantResponse>>(
      '/api/work-orders/technician-assist/stream',
      {
        method: 'POST',
        body: JSON.stringify({ work_order_id: workOrderId, observation }),
      },
      onEvent,
    ),
  supervisorAssist: (payload: { work_order_id?: string; queue_name?: string; question?: string }) =>
    request<SupervisorAssistantResponse>('/api/work-orders/supervisor-assist', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  supervisorAssistStream: (
    payload: { work_order_id?: string; queue_name?: string; question?: string },
    onEvent: (event: AssistantStreamEvent<SupervisorAssistantResponse>) => void,
  ) =>
    streamRequest<AssistantStreamEvent<SupervisorAssistantResponse>>(
      '/api/work-orders/supervisor-assist/stream',
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
      onEvent,
    ),
  feedback: (
    recommendationId: string,
    status: 'accepted' | 'rejected' | 'corrected',
    equipmentId?: string,
    details?: { actualRootCause?: string; actionTaken?: string; outcome?: string; notes?: string },
  ) =>
    request(`/api/recommendations/${recommendationId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({
        status,
        equipment_id: equipmentId,
        actual_root_cause: details?.actualRootCause,
        action_taken: details?.actionTaken,
        outcome: details?.outcome,
        notes: details?.notes,
      }),
    }),
  reportMarkdown: (equipmentId: string) => textRequest(`/api/reports/${equipmentId}/markdown`),
}

export const fallbackDashboard: DashboardSummary = {
  equipment_count: 5,
  active_alert_count: 5,
  critical_alert_count: 2,
  average_health_score: 20,
  highest_risk_equipment: [
    {
      equipment: {
        id: 'RM-DRIVE-01',
        name: 'Hot Strip Mill Main Drive Motor',
        area: 'Hot Rolling Mill',
        process: 'Finishing stand drive',
        criticality: 5,
        status: 'degraded',
      },
      risk_level: 'critical',
      health_score: 10,
      active_alerts: [
        {
          id: 'ALT-1001',
          equipment_id: 'RM-DRIVE-01',
          timestamp: '2026-06-06T08:15:00+05:30',
          signal: 'drive_end_vibration',
          value: 9.8,
          unit: 'mm/s',
          threshold: 7.1,
          severity: 'critical',
          message: 'Drive end vibration exceeds trip advisory threshold',
        },
      ],
      anomalies: [
        {
          equipment_id: 'RM-DRIVE-01',
          signal: 'drive_end_vibration',
          timestamp: '2026-06-06T08:15:00+05:30',
          value: 9.8,
          unit: 'mm/s',
          baseline_mean: 5.24,
          z_score: 7.2,
          threshold: 7.1,
          threshold_breached: true,
          trend_delta: 4.56,
          risk_level: 'critical',
          explanation: 'drive_end_vibration is critical risk against rolling baseline and threshold.',
        },
      ],
      top_spares_constraints: [
        {
          id: 'SP-001',
          equipment_id: 'RM-DRIVE-01',
          name: 'Drive end spherical roller bearing',
          available_qty: 0,
          lead_time_days: 21,
          criticality: 5,
        },
      ],
      notes: ['Critical vibration alert and unavailable bearing spare require intervention planning.'],
    },
    {
      equipment: {
        id: 'OH-CRANE-05',
        name: 'Melt Shop Overhead Crane',
        area: 'Melt Shop',
        process: 'Ladle handling and maintenance lifting',
        criticality: 5,
        status: 'watch',
      },
      risk_level: 'critical',
      health_score: 0,
      active_alerts: [
        {
          id: 'ALT-4001',
          equipment_id: 'OH-CRANE-05',
          timestamp: '2026-06-06T08:45:00+05:30',
          signal: 'hoist_motor_current',
          value: 188,
          unit: 'A',
          threshold: 180,
          severity: 'critical',
          message: 'Main hoist motor current above safe heavy-lift limit',
        },
      ],
      anomalies: [
        {
          equipment_id: 'OH-CRANE-05',
          signal: 'hoist_motor_current',
          timestamp: '2026-06-06T08:45:00+05:30',
          value: 188,
          unit: 'A',
          baseline_mean: 135.25,
          z_score: 6.32,
          threshold: 180,
          threshold_breached: true,
          trend_delta: 52.75,
          risk_level: 'critical',
          explanation: 'hoist_motor_current is critical risk against rolling baseline and threshold.',
        },
      ],
      top_spares_constraints: [
        {
          id: 'SP-006',
          equipment_id: 'OH-CRANE-05',
          name: 'Main hoist brake shoe set',
          available_qty: 0,
          lead_time_days: 14,
          criticality: 5,
        },
      ],
      notes: ['Critical hoist current and brake spare constraints require lift restriction review.'],
    },
    {
      equipment: {
        id: 'HYD-SYS-04',
        name: 'Hot Rolling Hydraulic System',
        area: 'Hot Rolling Mill',
        process: 'AGC and roll gap hydraulic control',
        criticality: 4,
        status: 'degraded',
      },
      risk_level: 'critical',
      health_score: 0,
      active_alerts: [
        {
          id: 'ALT-3001',
          equipment_id: 'HYD-SYS-04',
          timestamp: '2026-06-06T08:35:00+05:30',
          signal: 'hydraulic_oil_temperature',
          value: 82,
          unit: 'C',
          threshold: 75,
          severity: 'high',
          message: 'Hydraulic oil temperature rising during roll gap correction',
        },
      ],
      anomalies: [
        {
          equipment_id: 'HYD-SYS-04',
          signal: 'hydraulic_oil_temperature',
          timestamp: '2026-06-06T08:35:00+05:30',
          value: 82,
          unit: 'C',
          baseline_mean: 59.2,
          z_score: 4.8,
          threshold: 75,
          threshold_breached: true,
          trend_delta: 22.8,
          risk_level: 'critical',
          explanation: 'hydraulic_oil_temperature is critical risk against rolling baseline and threshold.',
        },
      ],
      top_spares_constraints: [
        {
          id: 'SP-004',
          equipment_id: 'HYD-SYS-04',
          name: 'Hydraulic pump cartridge assembly',
          available_qty: 0,
          lead_time_days: 18,
          criticality: 4,
        },
      ],
      notes: ['Hydraulic oil temperature and unavailable pump cartridge require maintenance planning.'],
    },
    {
      equipment: {
        id: 'BF-BLOWER-02',
        name: 'Blast Furnace Combustion Air Blower',
        area: 'Blast Furnace',
        process: 'Combustion air supply',
        criticality: 5,
        status: 'watch',
      },
      risk_level: 'high',
      health_score: 29,
      active_alerts: [
        {
          id: 'ALT-2001',
          equipment_id: 'BF-BLOWER-02',
          timestamp: '2026-06-06T07:50:00+05:30',
          signal: 'outlet_pressure_variance',
          value: 14.2,
          unit: '%',
          threshold: 10,
          severity: 'high',
          message: 'Combustion blower pressure variance above normal range',
        },
      ],
      anomalies: [],
      top_spares_constraints: [
        {
          id: 'SP-003',
          equipment_id: 'BF-BLOWER-02',
          name: 'Blower inlet guide vane actuator',
          available_qty: 1,
          lead_time_days: 12,
          criticality: 4,
        },
      ],
      notes: ['Blower pressure variance requires maintenance review.'],
    },
    {
      equipment: {
        id: 'CC-PUMP-03',
        name: 'Continuous Caster Cooling Water Pump',
        area: 'Continuous Casting',
        process: 'Secondary cooling',
        criticality: 4,
        status: 'normal',
      },
      risk_level: 'low',
      health_score: 72,
      active_alerts: [],
      anomalies: [],
      top_spares_constraints: [],
      notes: ['No active abnormality detected in sample data.'],
    },
  ],
}
