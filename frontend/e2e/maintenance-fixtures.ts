import { expect, type Page, type Route } from '@playwright/test'
import type {
  AssetDetail,
  AssetReliabilityPredictionStreamEvent,
  AssetListItem,
  AuthUser,
  DashboardSummary,
  LearningEmbeddingProfile,
  LearningExample,
  MaintenanceInsightReportBundle,
  LearningSummary,
  PmPlan,
  PmPlanDraftResponse,
  PmPlanDraftStreamEvent,
  PmTemplate,
  RcaCase,
  StreamingStatus,
  TechnicianAssistantResponse,
  UserRole,
  WorkOrder,
} from '../src/services/api'

export type RoleKey = 'operator' | 'technician' | 'supervisor' | 'engineer' | 'reliability' | 'planner' | 'admin'

export const demoPassword = 'DemoPass123!'

export const roleUsers: Record<RoleKey, AuthUser> = {
  operator: {
    id: 'USER-OPERATOR',
    email: 'operator@plant.local',
    display_name: 'Jan',
    role: 'operator',
    is_active: true,
  },
  technician: {
    id: 'USER-TECHNICIAN',
    email: 'technician@plant.local',
    display_name: 'Vinoth',
    role: 'maintenance_technician',
    is_active: true,
  },
  supervisor: {
    id: 'USER-SUPERVISOR',
    email: 'supervisor@plant.local',
    display_name: 'Dhruv',
    role: 'maintenance_supervisor',
    is_active: true,
  },
  engineer: {
    id: 'USER-MAINTENANCE',
    email: 'maintenance@plant.local',
    display_name: 'Lokesh',
    role: 'maintenance_engineer',
    is_active: true,
  },
  reliability: {
    id: 'USER-RELIABILITY',
    email: 'reliability@plant.local',
    display_name: 'Guna',
    role: 'reliability_engineer',
    is_active: true,
  },
  planner: {
    id: 'USER-PLANNER',
    email: 'planner@plant.local',
    display_name: 'Priya',
    role: 'planner',
    is_active: true,
  },
  admin: {
    id: 'USER-ADMIN',
    email: 'admin@plant.local',
    display_name: 'Ragav',
    role: 'admin',
    is_active: true,
  },
}

const usersByEmail = new Map(Object.values(roleUsers).map((user) => [user.email, user]))

const alerts = [
  {
    id: 'ALT-1001',
    equipment_id: 'RM-DRIVE-01',
    timestamp: '2026-06-06T08:15:00+05:30',
    signal: 'drive_end_vibration',
    value: 9.8,
    unit: 'mm/s',
    threshold: 7.1,
    severity: 'critical' as const,
    message: 'Drive end vibration exceeds advisory threshold',
  },
]

const health = {
  equipment: {
    id: 'RM-DRIVE-01',
    name: 'Hot Strip Mill Main Drive Motor',
    area: 'Hot Rolling Mill',
    process: 'Finishing stand drive',
    criticality: 5,
    status: 'degraded',
  },
  risk_level: 'critical' as const,
  health_score: 18,
  active_alerts: alerts,
  anomalies: [
    {
      equipment_id: 'RM-DRIVE-01',
      signal: 'drive_end_vibration',
      timestamp: '2026-06-06T08:15:00+05:30',
      value: 9.8,
      unit: 'mm/s',
      baseline_mean: 5.2,
      z_score: 8.4,
      threshold: 7.1,
      threshold_breached: true,
      trend_delta: 4.6,
      risk_level: 'critical' as const,
      explanation: 'Drive-end vibration is above normal rolling baseline.',
    },
  ],
  top_spares_constraints: [
    {
      id: 'SP-001',
      equipment_id: 'RM-DRIVE-01',
      name: 'Drive-end spherical roller bearing',
      available_qty: 0,
      lead_time_days: 21,
      criticality: 5,
    },
  ],
  notes: ['Key contributors: sensor trends, incomplete maintenance, and health score.'],
}

export const dashboard: DashboardSummary = {
  equipment_count: 1,
  active_alert_count: 1,
  critical_alert_count: 1,
  average_health_score: 18,
  highest_risk_equipment: [health],
}

export const assets: AssetListItem[] = [
  {
    id: 'RM-DRIVE-01',
    name: 'Hot Strip Mill Main Drive Motor',
    asset_type: 'Drive motor',
    area: 'Hot Rolling Mill',
    process: 'Finishing stand drive',
    location_code: 'HRM-FIN-01',
    location_name: 'Finishing Mill',
    criticality: 5,
    status: 'degraded',
    health_score: 18,
    risk_level: 'critical',
    active_alerts: 1,
    open_work_orders: 2,
    supervisor: 'Dhruv',
    last_updated: '2026-06-13T09:00:00+05:30',
  },
]

export const workOrders: WorkOrder[] = [
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
    assigned_to: 'Vinoth',
    supervisor: 'Dhruv',
    due_date: '2026-06-14T18:00:00+05:30',
    planning_status: 'planned',
    planned_start: '2026-06-14T14:00:00+05:30',
    planned_end: '2026-06-14T18:00:00+05:30',
    outage_window: 'Finishing stand load-reduction window',
    material_readiness: 'ready',
    material_blocker_status: 'reserved',
    material_blocker_note: 'Bearing inspection kit is staged for the planned window.',
    dispatch_notes: 'Stage vibration tools and bearing inspection kit.',
    dispatched_at: null,
    recommended_action: 'Reduce load if vibration persists and verify coupling alignment.',
    follow_up_required: true,
    ai_summary: 'High-risk drive vibration needs mechanical inspection before restart.',
    completion_summary: null,
    created_at: '2026-06-13T08:00:00+05:30',
    updated_at: '2026-06-13T11:00:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [
      {
        id: 1,
        work_order_id: 'WO-8304',
        spare_id: 'SP-001',
        spare_name: 'Drive end spherical roller bearing',
        required_qty: 1,
        reserved_qty: 1,
        available_qty: 1,
        reorder_requested: false,
        procurement_status: 'not_requested',
        procurement_lead_time_days: 21,
        expected_available_date: null,
        substitute_spare_id: 'SP-002',
        substitute_name: 'High-temperature coupling grease',
        blocker_status: 'reserved',
        blocker_note: 'Reserved for planned inspection window.',
      },
    ],
  },
  {
    id: 'WO-8311',
    equipment_id: 'RM-DRIVE-01',
    title: 'Verify inlet guide vane actuator response',
    description: 'Check actuator travel, linkage looseness, and position feedback drift.',
    status: 'WAPPR',
    priority: 2,
    work_type: 'CM',
    failure_class: 'CTRL',
    problem_code: 'IGVACT',
    classification: 'Control actuator',
    assigned_to: 'Guna',
    supervisor: 'Dhruv',
    due_date: '2026-06-15T12:00:00+05:30',
    planning_status: 'unscheduled',
    planned_start: null,
    planned_end: null,
    outage_window: null,
    material_readiness: 'unknown',
    material_blocker_status: 'not_required',
    material_blocker_note: null,
    dispatch_notes: null,
    dispatched_at: null,
    recommended_action: 'Stroke-test the guide vane actuator and compare response to pressure variance.',
    follow_up_required: false,
    ai_summary: 'Pressure variance points to actuator or linkage response drift.',
    completion_summary: null,
    created_at: '2026-06-13T09:00:00+05:30',
    updated_at: '2026-06-13T09:30:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [],
  },
]

export const pmTemplates: PmTemplate[] = [
  {
    id: 'PMT-RM-DRIVE-BEARING',
    equipment_id: 'RM-DRIVE-01',
    title: 'Drive bearing and coupling health PM',
    description: 'Recurring vibration, temperature, lubrication, and coupling inspection.',
    cadence_days: 14,
    work_type: 'PM',
    task_list: ['Trend drive-end vibration.', 'Inspect coupling alignment.'],
    thresholds: ['drive_end_vibration >= 7.1 mm/s'],
    source: 'sop',
    created_at: '2026-06-14T09:00:00+05:30',
    updated_at: '2026-06-14T09:00:00+05:30',
  },
]

export const generatedPmPlan: PmPlan = {
  id: 'PM-7001',
  equipment_id: 'RM-DRIVE-01',
  template_id: 'PMT-RM-DRIVE-BEARING',
  title: 'Main drive proactive PM plan',
  status: 'draft',
  cadence_days: 14,
  next_due_date: '2026-06-18T08:00:00+05:30',
  trigger: {
    type: 'risk_prediction',
    metric_key: 'drive_end_vibration',
    operator: '>=',
    threshold: 7.1,
    unit: 'mm/s',
    description: 'Generate planned PM when vibration risk remains high or crosses 7.1 mm/s.',
  },
  thresholds: ['drive_end_vibration >= 7.1 mm/s'],
  tasks: [
    {
      id: 'TASK-1',
      sequence: 1,
      task: 'Inspect drive-end bearing housing and coupling alignment.',
      owner_role: 'Maintenance Technician',
      estimated_minutes: 45,
      safety_note: 'Apply LOTO before inspection.',
    },
  ],
  smith_steps: ['Confirm LOTO and permits.', 'Inspect drive-end bearing housing and coupling alignment.'],
  spares_strategy: ['Check Drive end spherical roller bearing availability.'],
  evidence: [],
  adjustment_notes: ['Adjust cadence using accepted feedback after repeated vibration findings.'],
  source: 'deterministic',
  generated_by: 'morpheus',
  used_live_provider: false,
  provider: 'playwright',
  converted_work_order_id: null,
  created_at: '2026-06-14T09:05:00+05:30',
  updated_at: '2026-06-14T09:05:00+05:30',
}

export const rcaCases: RcaCase[] = [
  {
    id: 'RCA-9001',
    equipment_id: 'RM-DRIVE-01',
    work_order_id: 'WO-8304',
    title: 'Drive-end vibration root cause review',
    status: 'investigating',
    severity: 'critical',
    problem_statement: 'Drive-end vibration remains elevated after temporary load reduction.',
    symptoms: [
      'Drive-end vibration exceeded advisory threshold during finishing stand operation.',
      'Bearing temperature crossed 85 C during the last rolling campaign.',
    ],
    hypotheses: [
      {
        id: 'HYP-1',
        cause: 'Drive-end bearing wear or coupling looseness under load',
        confidence: 0.82,
        evidence: ['ALT-1001 vibration alert', 'DOC-1 bearing vibration SOP'],
        missing_checks: ['Verify coupling alignment after load reduction'],
        status: 'candidate',
      },
    ],
    why_chain: [
      'Why did vibration rise? Bearing housing vibration increased during operation.',
      'Why did housing vibration increase? Drive-end bearing or coupling looseness is likely.',
      'Why was looseness not detected earlier? Inspection was deferred until a planned window.',
    ],
    fishbone: {
      Machine: ['Drive-end bearing wear', 'Coupling looseness'],
      Method: ['Inspection deferred to planned stoppage'],
      Material: ['Bearing spare readiness must be confirmed'],
      Measurement: ['Trend relies on vibration and temperature signals'],
    },
    evidence_timeline: [
      {
        id: 'EV-1',
        timestamp: '2026-06-13T08:15:00+05:30',
        source_type: 'alert',
        source_id: 'ALT-1001',
        title: 'Drive-end vibration alert',
        summary: 'Vibration exceeded threshold during hot strip finishing operation.',
        relevance: 'primary symptom',
      },
      {
        id: 'EV-2',
        timestamp: '2026-06-13T09:00:00+05:30',
        source_type: 'sop',
        source_id: 'DOC-1',
        title: 'Bearing vibration SOP',
        summary: 'Confirm lubrication, alignment, and bearing housing condition before restart.',
        relevance: 'required checks',
      },
    ],
    corrective_actions: [
      {
        id: 'CA-1',
        action: 'Inspect drive-end bearing housing and verify coupling alignment.',
        owner: 'Vinoth',
        due_date: '2026-06-14T18:00:00+05:30',
        status: 'proposed',
        verification: 'Record vibration before and after load-reduction inspection.',
      },
    ],
    closure_review: null,
    probable_cause: 'Drive-end bearing wear or coupling looseness under load',
    confidence: 0.82,
    missing_checks: ['Confirm spare readiness before intrusive bearing inspection'],
    morpheus_summary: 'Morpheus correlated vibration, temperature, SOP guidance, and work-order history to narrow the RCA candidate.',
    used_live_provider: false,
    provider: 'playwright',
    created_at: '2026-06-13T09:00:00+05:30',
    updated_at: '2026-06-13T10:00:00+05:30',
    closed_at: null,
  },
]

export const assetDetail: AssetDetail = {
  profile: {
    equipment_id: 'RM-DRIVE-01',
    name: 'Hot Strip Mill Main Drive Motor',
    area: 'Hot Rolling Mill',
    process: 'Finishing stand drive',
    criticality: 5,
    status: 'degraded',
    asset_type: 'Drive motor',
    location_code: 'HRM-FIN-01',
    location_name: 'Finishing Mill',
    parent_system: 'Hot Strip Mill',
    manufacturer: 'Demo Drives',
    model: 'MD-5000',
    serial_number: 'RMD-01',
    installed_at: '2021-02-01',
    owner_team: 'Maintenance',
    supervisor: 'Dhruv',
    description: 'Main drive motor for the hot strip finishing stand.',
    last_updated: '2026-06-13T09:00:00+05:30',
  },
  health,
  metrics: [
    {
      id: 'MET-HEALTH',
      equipment_id: 'RM-DRIVE-01',
      metric_key: 'health',
      label: 'Health',
      value: 18,
      unit: '%',
      target_value: 90,
      status: 'critical',
      trend: 'down',
      detail: 'Health is reduced by vibration and open work.',
      captured_at: '2026-06-13T09:00:00+05:30',
      sort_order: 1,
    },
    {
      id: 'MET-EFF',
      equipment_id: 'RM-DRIVE-01',
      metric_key: 'efficiency',
      label: 'Efficiency',
      value: 82,
      unit: '%',
      target_value: 95,
      status: 'watch',
      trend: 'flat',
      detail: 'Efficiency remains below target.',
      captured_at: '2026-06-13T09:00:00+05:30',
      sort_order: 2,
    },
    {
      id: 'MET-RISK',
      equipment_id: 'RM-DRIVE-01',
      metric_key: 'risk',
      label: 'Risk',
      value: 82,
      unit: '%',
      target_value: 10,
      status: 'critical',
      trend: 'up',
      detail: 'Risk is elevated by vibration.',
      captured_at: '2026-06-13T09:00:00+05:30',
      sort_order: 3,
    },
  ],
  recommendations: [
    {
      id: 'REC-1',
      equipment_id: 'RM-DRIVE-01',
      action_type: 'inspect',
      title: 'Inspect bearing vibration',
      description: 'Inspect the drive-end bearing housing and coupling alignment.',
      priority: 1,
      source: 'playwright fixture',
      created_at: '2026-06-13T09:00:00+05:30',
      sort_order: 1,
    },
  ],
  maintenance_events: [
    {
      id: 'ME-1',
      equipment_id: 'RM-DRIVE-01',
      date: '2026-06-01',
      issue: 'High vibration',
      root_cause: 'Bearing looseness',
      action: 'Retorqued bearing housing',
      downtime_hours: 2,
    },
  ],
  work_orders: workOrders,
  subsystems: [
    {
      id: 'SUB-1',
      equipment_id: 'RM-DRIVE-01',
      name: 'Drive-end bearing',
      component: 'Bearing housing',
      condition: 'watch',
      detail: 'Vibration trend is elevated.',
      sort_order: 1,
    },
  ],
  reliability_metrics: [
    {
      id: 'REL-1',
      equipment_id: 'RM-DRIVE-01',
      metric_name: 'Failure probability',
      value: 76,
      unit: '%',
      target_value: 10,
      status: 'critical',
      trend: 'up',
      detail: 'Recent vibration increases near-term failure probability.',
      sort_order: 1,
    },
  ],
  performance_charts: [
    {
      signal: 'drive_end_vibration',
      title: 'Drive-end vibration',
      unit: 'mm/s',
      points: [
        { timestamp: '2026-06-13T08:00:00+05:30', value: 6.2, threshold: 7.1 },
        { timestamp: '2026-06-13T09:00:00+05:30', value: 9.8, threshold: 7.1 },
      ],
    },
  ],
  documents: [
    {
      id: 'DOC-1',
      source_type: 'sop',
      equipment_id: 'RM-DRIVE-01',
      title: 'Bearing vibration SOP',
      excerpt: 'Confirm lubrication condition and coupling alignment before restart.',
    },
  ],
  knowledge: [
    {
      source_type: 'sop',
      source_id: 'DOC-1',
      title: 'Bearing vibration SOP',
      excerpt: 'Use isolation and PPE before bearing inspection.',
      equipment_id: 'RM-DRIVE-01',
      relevance_reason: 'Matches vibration symptom.',
    },
  ],
  prediction: {
    equipment_id: 'RM-DRIVE-01',
    risk_level: 'critical',
    failure_probability: 0.76,
    remaining_useful_life_days: 18,
    confidence_interval: {
      lower_probability: 0.67,
      upper_probability: 0.84,
      lower_rul_days: 14,
      upper_rul_days: 22,
      confidence_level: 0.8,
      rationale: 'Interval width reflects active alerts, anomaly findings, maintenance events, and feedback records.',
    },
    model_version: {
      id: 'rul-risk-heuristic-v2',
      name: 'Maintenance Wizard RUL Risk Model',
      version: '2.0.0',
      algorithm: 'deterministic weighted risk score with rolling-baseline anomaly features',
      feature_set: ['active alert severity', 'rolling-baseline anomaly severity'],
      trained_on: 'seeded maintenance history, active alerts, sensor readings, and approved feedback labels',
      status: 'active',
    },
    model_evaluation: {
      evaluation_id: 'backtest-2.0.0-RM-DRIVE-01',
      backtest_window_days: 180,
      sample_count: 14,
      precision: 0.74,
      recall: 0.69,
      mean_absolute_rul_error_days: 16,
      calibration_error: 0.14,
      summary: 'Backtest compares historical alert/anomaly windows against recorded maintenance events.',
    },
    prediction_evidence: [
      {
        source_type: 'alert',
        source_id: 'ALT-1001',
        title: 'drive_end_vibration critical alert',
        detail: 'Drive end vibration exceeds trip advisory threshold.',
        contribution: 1,
      },
    ],
    degradation_trend: [
      {
        timestamp: '2026-06-06T08:15:00+05:30',
        signal: 'drive_end_vibration',
        value: 9.8,
        unit: 'mm/s',
        threshold: 7.1,
        normalized_severity: 1,
        estimated_rul_days: 18,
      },
    ],
    drivers: ['Vibration trend', 'Open approved work order'],
    reasoning_explanation: null,
  },
}

const embeddingProfile: LearningEmbeddingProfile = {
  id: 'rag-prof-active',
  provider: 'deterministic_hash',
  model: 'maintenance-hash-v1',
  version: '1',
  dimensions: 64,
  distance: 'Cosine',
  status: 'active',
  notes: 'Default local profile',
  metadata: {},
  created_at: '2026-06-13T09:00:00+05:30',
  updated_at: '2026-06-13T09:00:00+05:30',
}

function pmDraftStreamBody(response: PmPlanDraftResponse): string {
  const events: PmPlanDraftStreamEvent[] = [
    { type: 'meta', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### PM Plan\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: 'Main drive proactive PM plan\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### Monitoring Thresholds\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- drive_end_vibration >= 7.1 mm/s\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### Generated Task List\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- Inspect bearing condition and coupling alignment.\n', provider: 'openai', used_live_provider: true },
    { type: 'done', response },
  ]
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
}

function reliabilityPredictionStreamBody(): string {
  const answer = [
    '### Failure Prediction',
    '- RM-DRIVE-01 has a critical failure risk at 76% with 18 days estimated RUL and a 67-84% probability interval.',
    '### Model Confidence',
    '- Maintenance Wizard RUL Risk Model 2.0.0 backtested at 74% precision and 69% recall.',
    '### Trend Evidence',
    '- Drive-end vibration remains above threshold and supports accelerated inspection.',
  ].join('\n')
  const events: AssetReliabilityPredictionStreamEvent[] = [
    { type: 'meta', provider: 'openai', used_live_provider: true },
    { type: 'token', content: answer },
    { type: 'done', answer, prediction: assetDetail.prediction!, provider: 'openai', used_live_provider: true },
  ]
  return events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join('')
}

const learningSummary: LearningSummary = {
  counts: {
    interactions: 1,
    examples: 1,
    approved_examples: 1,
    snapshots: 0,
    artifacts: 0,
    promotions: 0,
    deployments: 0,
  },
  recent_examples: [],
  recent_snapshots: [],
  model_versions: [
    {
      id: 'model-local-qwen',
      provider: 'openai',
      model_name: 'qwen2.5-7b-instruct',
      base_model: 'qwen2.5-7b-instruct',
      adapter_path: null,
      status: 'active',
      notes: 'Local model',
      created_at: '2026-06-13T09:00:00+05:30',
    },
  ],
  prompt_versions: [
    {
      id: 'prompt-neo-v1',
      assistant: 'neo',
      version: '1',
      prompt: 'Dashboard assistant',
      status: 'active',
      notes: null,
      created_at: '2026-06-13T09:00:00+05:30',
    },
  ],
  evaluation_runs: [],
  recent_jobs: [],
  recent_artifacts: [],
  recent_promotions: [],
  recent_deployments: [],
  serving_model: {
    provider: 'openai',
    openai_model: 'qwen2.5-7b-instruct',
    ollama_model: 'qwen2.5-7b-instruct',
    openai_base_url: 'http://127.0.0.1:8080/v1',
    ollama_base_url: 'http://localhost:11434',
    source: 'learning_active_model',
    active_model_version_id: 'model-local-qwen',
    adapter_path: null,
    base_model: 'qwen2.5-7b-instruct',
    status: 'ready',
    warning: null,
  },
  artifact_store: {
    store: 'filesystem',
    local_dir: 'backend/data/learning_artifacts',
    state: 'ready',
    retention: { state: 'disabled', retention_days: 0, cleanup_enabled: false },
  },
  peft_trainer: {
    mode: 'prepared_artifacts',
    configured: false,
    timeout_seconds: 900,
  },
  vector_store: {
    store: 'qdrant',
    enabled: true,
    collection: 'maintenance_wizard_documents',
    collection_alias: null,
    url: 'http://localhost:6333',
    embedding_profile: {
      ...embeddingProfile,
      state: 'ready',
      configured_dimensions: 64,
      warning: undefined,
    },
    points_count: 42,
    collection_vector_size: 64,
    collection_distance: 'Cosine',
    migration_required: false,
    migration_reasons: [],
    state: 'ready',
    error: null,
  },
}

const learningExamples: LearningExample[] = [
  {
    id: 'learn-maintenance-label-long',
    source_id: 'LABEL-CC-PUMP-03',
    source_type: 'maintenance_label',
    equipment_id: 'CC-PUMP-03',
    instruction: 'Map maintenance evidence to failure mode, component, root cause, action class, and outcome.',
    input_text: 'Seal flush strainer restriction reduced pump margin with standby auto-start and increased shift checks.',
    expected_output:
      'Root cause: Seal flush strainer restriction reduced pump margin Action class: Cleaned seal flush strainer, verified standby pump auto-start, and increased shift flow checks Outcome: Resolved with partial downtime',
    metadata: {},
    judge_score: 0.86,
    judge_label: 'training_worthy',
    judge_rationale:
      'Deterministic judge fallback used because OpenAI call failed or returned invalid JSON. Source=maintenance_label; score reflects specificity, outcome evidence, and safety context.',
    judge_used_live_provider: false,
    judge_provider: 'openai',
    approved: true,
    created_at: '2026-06-15T05:18:00+00:00',
  },
]

const streamingStatus: StreamingStatus = {
  enabled: true,
  state: 'connected',
  broker: 'nats',
  stream: 'MW_IOT',
  consumer: 'maintenance-wizard-ingestor',
  subjects: ['maintenance.iot.readings'],
  processed_count: 24,
  failed_count: 0,
  last_message_timestamp: '2026-06-13T09:00:00+05:30',
}

const maintenanceInsights: MaintenanceInsightReportBundle = {
  generated_at: '2026-06-14T12:00:00+00:00',
  scope_equipment_id: null,
  assets_reviewed: 1,
  structured_reports: [
    {
      id: 'MR-RM-DRIVE-01',
      equipment_id: 'RM-DRIVE-01',
      equipment_name: 'Hot Strip Mill Main Drive Motor',
      area: 'Hot Rolling Mill',
      risk_level: 'critical',
      health_score: 18,
      failure_probability: 0.76,
      remaining_useful_life_days: 18,
      confidence_band: '14-22 days',
      active_alert_count: 1,
      open_work_order_count: 2,
      report_summary: 'Hot Strip Mill Main Drive Motor is at critical risk with 18% health and active vibration alerts.',
      probable_causes: ['Drive-end vibration abnormality linked to bearing looseness.'],
      immediate_actions: ['Confirm current readings against thresholds.', 'Resolve any material blocker before intrusive work.'],
      planned_actions: ['Plan corrective work inside the RUL confidence window.'],
      spares_strategy: ['Check Drive-end spherical roller bearing availability.'],
      evidence: ['ALT-1001: Drive end vibration exceeds advisory threshold', 'WO-8304: Inspect main drive bearing vibration (APPR)'],
      recommended_owner: 'Maintenance Supervisor',
    },
  ],
  abnormal_alert_reports: [
    {
      alert_id: 'ALT-1001',
      equipment_id: 'RM-DRIVE-01',
      equipment_name: 'Hot Strip Mill Main Drive Motor',
      timestamp: '2026-06-06T08:15:00+05:30',
      signal: 'drive_end_vibration',
      severity: 'critical',
      value: 9.8,
      unit: 'mm/s',
      threshold: 7.1,
      threshold_delta: 2.7,
      abnormality: 'drive_end_vibration is 2.7mm/s above threshold.',
      decision: 'Escalate for same-shift maintenance review.',
      recommended_actions: ['Verify the live reading.', 'Inspect the related component.'],
      evidence: ['Drive end vibration exceeds advisory threshold'],
    },
  ],
  decision_summaries: [
    {
      audience: 'engineer',
      title: 'Engineer Maintenance Decision Summary',
      summary: 'One asset needs engineering review.',
      decisions: ['Prioritize Hot Strip Mill Main Drive Motor.'],
      risks: ['RM-DRIVE-01 has active vibration risk.'],
      next_actions: ['Validate probable causes against field readings.'],
      referenced_equipment: ['RM-DRIVE-01'],
      referenced_alerts: ['ALT-1001'],
      referenced_work_orders: [],
    },
    {
      audience: 'supervisor',
      title: 'Supervisor Maintenance Decision Summary',
      summary: 'One high-risk asset has open execution work.',
      decisions: ['Confirm owner and execution window for WO-8304.'],
      risks: ['Open vibration work remains high priority.'],
      next_actions: ['Approve or unblock waiting work orders.'],
      referenced_equipment: ['RM-DRIVE-01'],
      referenced_alerts: ['ALT-1001'],
      referenced_work_orders: ['WO-8304'],
    },
  ],
  maintenance_log_entries: [
    {
      equipment_id: 'RM-DRIVE-01',
      equipment_name: 'Hot Strip Mill Main Drive Motor',
      timestamp: '2026-06-14T12:00:00+00:00',
      entry_type: 'generated_insight',
      content: 'Generated maintenance insight for Hot Strip Mill Main Drive Motor.',
      source_ids: ['MR-RM-DRIVE-01', 'ALT-1001'],
    },
  ],
}

function json(data: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  }
}

function sse(event: unknown) {
  return `data: ${JSON.stringify(event)}\n\n`
}

function workOrdersFor(user: AuthUser) {
  if (user.role === 'maintenance_technician') {
    return workOrders.filter((order) => order.assigned_to === user.display_name)
  }
  return workOrders
}

export async function installMaintenanceApi(page: Page, initialUser: AuthUser = roleUsers.admin) {
  let currentUser = initialUser
  let pmPlans: PmPlan[] = []

  await page.route('**/api/**', async (route: Route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname

    if (path === '/api/auth/login') {
      const payload = JSON.parse(request.postData() || '{}') as { email?: string }
      currentUser = usersByEmail.get(payload.email ?? '') ?? initialUser
      await route.fulfill(json({ access_token: `pw-${currentUser.id}`, token_type: 'bearer', expires_in: 28800, user: currentUser }))
      return
    }
    if (path === '/api/auth/me') {
      await route.fulfill(json(currentUser))
      return
    }
    if (path === '/api/auth/logout') {
      await route.fulfill(json({ status: 'ok' }))
      return
    }
    if (path === '/api/dashboard/summary') {
      await route.fulfill(json(dashboard))
      return
    }
    if (path === '/api/assets') {
      await route.fulfill(json(assets))
      return
    }
    if (path.endsWith('/reliability/stream')) {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: reliabilityPredictionStreamBody(),
      })
      return
    }
    if (path.startsWith('/api/assets/') && !path.endsWith('/reliability/stream')) {
      await route.fulfill(json(assetDetail))
      return
    }
    if (path === '/api/work-orders') {
      await route.fulfill(json(workOrdersFor(currentUser)))
      return
    }
    if (path === '/api/rca-cases') {
      await route.fulfill(json(rcaCases))
      return
    }
    if (path === '/api/pm-templates') {
      await route.fulfill(json(pmTemplates))
      return
    }
    if (path === '/api/pm-plans/morpheus-draft/stream') {
      pmPlans = [generatedPmPlan, ...pmPlans.filter((plan) => plan.id !== generatedPmPlan.id)]
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream' },
        body: pmDraftStreamBody({
          plan: generatedPmPlan,
          templates: pmTemplates,
          message: 'Morpheus drafted PM plan PM-7001 and Smith generated technician-ready steps.',
        }),
      })
      return
    }
    if (path === '/api/pm-plans/morpheus-draft') {
      pmPlans = [generatedPmPlan, ...pmPlans.filter((plan) => plan.id !== generatedPmPlan.id)]
      await route.fulfill(
        json({
          plan: generatedPmPlan,
          templates: pmTemplates,
          message: 'Morpheus drafted PM plan PM-7001 and Smith generated technician-ready steps.',
        }),
      )
      return
    }
    if (path.startsWith('/api/pm-plans/') && path.endsWith('/convert-work-order')) {
      const planId = path.split('/').at(-2) ?? 'PM-7001'
      const created: WorkOrder = {
        ...workOrders[0],
        id: 'WO-9100',
        title: 'PM: Main drive proactive PM plan',
        work_type: 'PM',
        planning_status: 'planned',
        recommended_action: generatedPmPlan.tasks[0].task,
        ai_summary: `Generated from PM plan ${planId}.`,
      }
      pmPlans = pmPlans.map((plan) => (
        plan.id === planId ? { ...plan, status: 'converted', converted_work_order_id: created.id } : plan
      ))
      await route.fulfill(json(created))
      return
    }
    if (path === '/api/pm-plans') {
      await route.fulfill(json(pmPlans))
      return
    }
    if (path.startsWith('/api/work-orders/') && request.method() === 'PATCH') {
      const workOrderId = path.split('/').at(-1)
      const body = JSON.parse(request.postData() || '{}')
      const updated = workOrders.find((order) => order.id === workOrderId) ?? workOrders[0]
      await route.fulfill(
        json({
          ...updated,
          ...body,
          dispatched_at: body.planning_status === 'dispatched' ? '2026-06-14T13:50:00+05:30' : updated.dispatched_at,
        }),
      )
      return
    }
    if (path === '/api/work-orders/technician-assist/stream') {
      const response: TechnicianAssistantResponse = {
        work_order_id: 'WO-8304',
        next_prompt: 'Record vibration before and after load reduction.',
        live_directions: ['Confirm isolation and inspect the drive-end bearing housing.'],
        recommendations: ['Reduce load if vibration persists and capture alignment readings.'],
        safety_reminders: ['Use lockout and hot-work controls before inspection.'],
        suggested_problem_code: 'BRGVIB',
        suggested_failure_class: 'MECH',
        completion_summary: 'Technician captured vibration and bearing findings.',
        evidence: [],
        used_live_provider: false,
        provider: 'playwright',
      }
      await route.fulfill({
        contentType: 'text/event-stream',
        body: [
          sse({ type: 'meta', provider: 'playwright', used_live_provider: false }),
          sse({ type: 'token', content: 'Inspect the drive-end bearing housing before completion.' }),
          sse({ type: 'done', response }),
        ].join(''),
      })
      return
    }
    if (path === '/api/work-orders/supervisor-assist/stream') {
      await route.fulfill({
        contentType: 'text/event-stream',
        body: [
          sse({ type: 'meta', provider: 'playwright', used_live_provider: false }),
          sse({ type: 'token', content: 'Review completed work and assign any follow-up.' }),
          sse({
            type: 'done',
            response: {
              summary: 'One completed work order needs supervisor follow-up.',
              follow_up_actions: ['Assign follow-up inspection to the technician.'],
              risks: ['Open vibration work remains high priority.'],
              draft_work_order: null,
              referenced_work_orders: ['WO-8304'],
              used_live_provider: false,
              provider: 'playwright',
            },
          }),
        ].join(''),
      })
      return
    }
    if (path === '/api/users') {
      await route.fulfill(json(Object.values(roleUsers)))
      return
    }
    if (path === '/api/users/technicians') {
      await route.fulfill(json([roleUsers.technician]))
      return
    }
    if (path === '/api/neo/welcome') {
      await route.fulfill(
        json({
          answer: `I am Neo. ${currentUser.display_name} can review role-specific maintenance attention items.`,
          table: null,
          used_live_provider: false,
          provider: 'playwright',
        }),
      )
      return
    }
    if (path === '/api/streaming/status') {
      await route.fulfill(json(streamingStatus))
      return
    }
    if (path.startsWith('/api/reports/maintenance-insights')) {
      const scopedEquipmentId = url.searchParams.get('equipment_id')
      const scopedStructuredReports = scopedEquipmentId
        ? maintenanceInsights.structured_reports.filter((report) => report.equipment_id === scopedEquipmentId)
        : maintenanceInsights.structured_reports
      const scopedAbnormalReports = scopedEquipmentId
        ? maintenanceInsights.abnormal_alert_reports.filter((report) => report.equipment_id === scopedEquipmentId)
        : maintenanceInsights.abnormal_alert_reports
      const scopedLogEntries = scopedEquipmentId
        ? maintenanceInsights.maintenance_log_entries.filter((entry) => entry.equipment_id === scopedEquipmentId)
        : maintenanceInsights.maintenance_log_entries

      if (path === '/api/reports/maintenance-insights/markdown') {
        await route.fulfill({
          status: 200,
          contentType: 'text/markdown',
          body: '# Structured Maintenance Insights',
        })
        return
      }
      if (path === '/api/reports/maintenance-insights/summary') {
        await route.fulfill(
          json({
            generated_at: maintenanceInsights.generated_at,
            scope_equipment_id: scopedEquipmentId,
            assets_reviewed: scopedEquipmentId ? 1 : maintenanceInsights.assets_reviewed,
            structured_report_count: scopedStructuredReports.length,
            abnormal_alert_report_count: scopedAbnormalReports.length,
            decision_summary_count: maintenanceInsights.decision_summaries.length,
            maintenance_log_entry_count: scopedLogEntries.length,
          }),
        )
        return
      }
      if (path === '/api/reports/maintenance-insights/structured-reports') {
        await route.fulfill(json(scopedStructuredReports))
        return
      }
      if (path === '/api/reports/maintenance-insights/abnormal-alerts') {
        await route.fulfill(json(scopedAbnormalReports))
        return
      }
      if (path === '/api/reports/maintenance-insights/decision-summaries') {
        await route.fulfill(json(maintenanceInsights.decision_summaries))
        return
      }
      if (path === '/api/reports/maintenance-insights/maintenance-log-entries') {
        await route.fulfill(json(scopedLogEntries))
        return
      }
      await route.fulfill(
        json({
          ...maintenanceInsights,
          scope_equipment_id: scopedEquipmentId,
          assets_reviewed: scopedEquipmentId ? 1 : maintenanceInsights.assets_reviewed,
          structured_reports: scopedStructuredReports,
          abnormal_alert_reports: scopedAbnormalReports,
          maintenance_log_entries: scopedLogEntries,
        }),
      )
      return
    }
    if (path === '/api/learning/summary') {
      await route.fulfill(json(learningSummary))
      return
    }
    if (path === '/api/learning/examples') {
      await route.fulfill(json(learningExamples))
      return
    }
    if (path === '/api/learning/datasets' || path === '/api/learning/model-deployments') {
      await route.fulfill(json([]))
      return
    }
    if (path === '/api/learning/rag/embedding-profiles') {
      await route.fulfill(json([embeddingProfile]))
      return
    }

    await route.fulfill(json({ detail: `Unhandled mocked route ${path}` }, 404))
  })
}

export async function signInAs(page: Page, role: RoleKey) {
  const user = roleUsers[role]
  await installMaintenanceApi(page, user)
  await page.goto('/')
  await page.getByLabel('Email').fill(user.email)
  await page.getByLabel('Password').fill(demoPassword)
  await page.getByRole('button', { name: 'Sign In' }).click()
  await expect(page.getByRole('heading', { name: /Maintenance Wizard/ })).toBeVisible()
  await expect(page.locator('.userPill strong', { hasText: user.display_name })).toBeVisible()
}

export function primaryNavButton(page: Page, name: string) {
  return page.locator('nav[aria-label="Primary navigation"]').getByRole('button', { name })
}

export async function openAssetDetail(page: Page) {
  await primaryNavButton(page, 'Assets').click()
  await page.getByRole('button', { name: /Hot Strip Mill Main Drive Motor/ }).first().click()
  await expect(page.getByRole('heading', { name: 'Asset profile' })).toBeVisible()
}

export async function expectNoDocumentHorizontalOverflow(page: Page) {
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const root = document.documentElement
          const body = document.body
          return Math.max(root.scrollWidth, body.scrollWidth) - window.innerWidth
        }),
      { timeout: 4_000 },
    )
    .toBeLessThanOrEqual(2)
}
