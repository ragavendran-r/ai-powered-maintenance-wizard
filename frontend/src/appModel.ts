import type {
  AssetDetail,
  AssetDetailSection,
  AuthUser,
  LearningModelDeployment,
  UserRole,
  WorkOrder,
} from './services/api'

export const riskRank = { low: 1, medium: 2, high: 3, critical: 4 }

export const applicationTitle = 'Intelligent Maintenance Wizard'

export type AppView = 'commandCenter' | 'assets' | 'asset' | 'workExecution' | 'planning' | 'reliability' | 'admin'
export type AssetTab = 'summary' | 'maintenance' | 'performance' | 'reliability' | 'documents' | 'workOrders'

export const assetSectionsByTab: Record<AssetTab, AssetDetailSection[]> = {
  summary: ['summary'],
  maintenance: ['maintenance'],
  performance: ['performance'],
  reliability: ['reliability'],
  documents: ['documents'],
  workOrders: ['work_orders'],
}

export const roleLabels: Record<UserRole, string> = {
  admin: 'Admin',
  maintenance_engineer: 'Maintenance Engineer',
  maintenance_technician: 'Maintenance Technician',
  maintenance_supervisor: 'Maintenance Supervisor',
  reliability_engineer: 'Reliability Engineer',
  planner: 'Planner',
  operator: 'Operator',
  iot_service: 'IoT Service',
}

export const roleOptions: UserRole[] = [
  'admin',
  'maintenance_engineer',
  'maintenance_technician',
  'maintenance_supervisor',
  'reliability_engineer',
  'planner',
  'operator',
  'iot_service',
]

export const diagnosisAssistantName = 'Morpheus'
export const reliabilityAssistantName = 'Smith'
export const technicianAssistantName = 'Neo'
export const supervisorAssistantName = 'Neo'

export const fallbackWorkOrders: WorkOrder[] = [
  {
    id: 'WO-8304',
    equipment_id: 'RM-DRIVE-01',
    title: 'Inspect main drive bearing vibration',
    description: 'Inspect bearing housing, coupling alignment, lubrication condition, and foundation bolts.',
    status: 'WMATL',
    priority: 1,
    work_type: 'CM',
    failure_class: 'MECH',
    problem_code: 'BRGVIB',
    classification: 'Bearing vibration',
    assigned_to: 'Maintenance Technician',
    supervisor: 'Maintenance Supervisor',
    due_date: '2026-06-12T18:00:00+05:30',
    planning_status: 'planned',
    planned_start: '2026-06-12T14:00:00+05:30',
    planned_end: '2026-06-12T18:00:00+05:30',
    outage_window: 'Finishing stand load-reduction window',
    material_readiness: 'blocked',
    material_blocker_status: 'blocked',
    material_blocker_note: 'Drive end bearing is out of stock; procure replacement or approve limited inspection scope.',
    dispatch_notes: 'Bearing spare availability must be confirmed before intrusive work.',
    dispatched_at: null,
    recommended_action: 'Reduce load if vibration persists and verify coupling alignment.',
    follow_up_required: true,
    ai_summary: 'High-risk drive vibration needs mechanical inspection before restart.',
    completion_summary: null,
    created_at: '2026-06-11T08:00:00+05:30',
    updated_at: '2026-06-11T11:00:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [
      {
        id: 1,
        work_order_id: 'WO-8304',
        spare_id: 'SP-001',
        spare_name: 'Drive end spherical roller bearing',
        required_qty: 1,
        reserved_qty: 0,
        available_qty: 0,
        reorder_requested: true,
        procurement_status: 'requested',
        procurement_lead_time_days: 21,
        expected_available_date: '2026-07-03',
        substitute_spare_id: 'SP-002',
        substitute_name: 'High-temperature coupling grease for non-intrusive lubrication inspection',
        blocker_status: 'blocked',
        blocker_note: 'No bearing is available for replacement; substitute supports inspection only.',
      },
    ],
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
    created_at: '2026-06-11T09:00:00+05:30',
    updated_at: '2026-06-11T09:30:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [
      {
        id: 2,
        work_order_id: 'WO-8311',
        spare_id: 'SP-003',
        spare_name: 'Blower inlet guide vane actuator',
        required_qty: 1,
        reserved_qty: 0,
        available_qty: 1,
        reorder_requested: false,
        procurement_status: 'not_requested',
        procurement_lead_time_days: 12,
        expected_available_date: null,
        substitute_spare_id: null,
        substitute_name: null,
        blocker_status: 'reserved',
        blocker_note: 'One actuator is available if stroke testing confirms replacement need.',
      },
    ],
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
    planning_status: 'dispatched',
    planned_start: '2026-06-11T13:30:00+05:30',
    planned_end: '2026-06-11T16:30:00+05:30',
    outage_window: 'Crane heavy-lift restriction window',
    material_readiness: 'blocked',
    material_blocker_status: 'reorder_requested',
    material_blocker_note: 'Brake shoe replacement follow-up is waiting on procurement confirmation.',
    dispatch_notes: 'Replacement brake shoes require follow-up procurement.',
    dispatched_at: '2026-06-11T12:45:00+05:30',
    recommended_action: 'Plan brake shoe replacement follow-up.',
    follow_up_required: true,
    ai_summary: 'Completed inspection still needs supervisor follow-up.',
    completion_summary: 'Brake temperature normalized after lift restriction.',
    created_at: '2026-06-10T09:00:00+05:30',
    updated_at: '2026-06-11T16:35:00+05:30',
    completed_at: '2026-06-11T16:35:00+05:30',
    logs: [],
    spare_reservations: [
      {
        id: 3,
        work_order_id: 'WO-8297',
        spare_id: 'SP-006',
        spare_name: 'Main hoist brake shoe set',
        required_qty: 1,
        reserved_qty: 0,
        available_qty: 0,
        reorder_requested: true,
        procurement_status: 'requested',
        procurement_lead_time_days: 14,
        expected_available_date: '2026-06-25',
        substitute_spare_id: null,
        substitute_name: null,
        blocker_status: 'reorder_requested',
        blocker_note: 'Procurement request is needed before brake shoe replacement follow-up.',
      },
    ],
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
    planning_status: 'planned',
    planned_start: '2026-06-14T08:00:00+05:30',
    planned_end: '2026-06-14T10:00:00+05:30',
    outage_window: 'Morning roll-gap correction maintenance window',
    material_readiness: 'pending',
    material_blocker_status: 'waiting_procurement',
    material_blocker_note: 'Pump cartridge is on order; seal kit can support limited inspection.',
    dispatch_notes: 'Pump cartridge assembly reservation is pending.',
    dispatched_at: null,
    recommended_action: 'Reserve pump cartridge assembly and inspect cooler differential temperature.',
    follow_up_required: false,
    ai_summary: 'Hydraulic temperature work is waiting for material coordination.',
    completion_summary: null,
    created_at: '2026-06-11T10:00:00+05:30',
    updated_at: '2026-06-11T10:30:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [
      {
        id: 4,
        work_order_id: 'WO-8275',
        spare_id: 'SP-004',
        spare_name: 'Hydraulic pump cartridge assembly',
        required_qty: 1,
        reserved_qty: 0,
        available_qty: 0,
        reorder_requested: true,
        procurement_status: 'ordered',
        procurement_lead_time_days: 18,
        expected_available_date: '2026-07-02',
        substitute_spare_id: 'SP-005',
        substitute_name: 'Servo valve seal kit',
        blocker_status: 'waiting_procurement',
        blocker_note: 'Pump cartridge lead time blocks replacement.',
      },
    ],
  },
]

export function fallbackWorkOrdersForUser(user?: AuthUser | null) {
  if (user?.role === 'maintenance_technician') {
    return fallbackWorkOrders.filter((order) => order.assigned_to === user.display_name)
  }
  return fallbackWorkOrders
}

export function mergeAssetDetail(
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

export function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  } catch {
    return value
  }
}

export function deploymentDisplayDate(deployment: LearningModelDeployment) {
  return deployment.health_checked_at ?? deployment.updated_at ?? deployment.created_at
}

function deploymentTimestamp(deployment: LearningModelDeployment) {
  const parsed = new Date(deploymentDisplayDate(deployment)).getTime()
  return Number.isFinite(parsed) ? parsed : 0
}

export function mergeLearningDeployments(
  deployments: LearningModelDeployment[],
  summaryDeployments: LearningModelDeployment[],
) {
  const records = new Map<string, LearningModelDeployment>()
  summaryDeployments.forEach((deployment) => records.set(deployment.id, deployment))
  deployments.forEach((deployment) => records.set(deployment.id, deployment))
  return [...records.values()].sort((left, right) => deploymentTimestamp(right) - deploymentTimestamp(left))
}

export function isVerifiedDeployment(deployment: LearningModelDeployment) {
  const status = deployment.status.toLowerCase()
  const healthStatus = (deployment.health_status ?? '').toLowerCase()
  return ['healthy', 'ok', 'ready', 'verified'].includes(healthStatus) || ['healthy', 'verified'].includes(status)
}

export function deploymentStatusClass(value?: string | null) {
  return (value?.trim() || 'unknown').toLowerCase().replace(/[^a-z0-9_-]+/g, '-')
}

export function metricValue(value: unknown) {
  if (typeof value === 'number') {
    return Number.isInteger(value) ? `${value}` : value.toFixed(3).replace(/0+$/, '').replace(/\.$/, '')
  }
  if (typeof value === 'string' && value.trim()) return value
  if (typeof value === 'boolean') return value ? 'yes' : 'no'
  return '0'
}

export function clipText(value: string, limit: number) {
  const compact = value.replace(/\s+/g, ' ').trim()
  if (compact.length <= limit) return compact
  return `${compact.slice(0, limit - 1).trim()}…`
}
