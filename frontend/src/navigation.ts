import type { AppView } from './appModel'
import type { UserRole } from './services/api'

export type NavigationItemId = Exclude<AppView, 'asset'>

export type NavigationIcon =
  | 'command'
  | 'monitoring'
  | 'assets'
  | 'execution'
  | 'planning'
  | 'reports'
  | 'ml'
  | 'reliability'
  | 'learning'
  | 'admin'

export interface JobNavigationItem {
  id: NavigationItemId
  label: string
  icon: NavigationIcon
  purpose: string
  roles: readonly UserRole[]
  rolePriority: Partial<Record<UserRole, number>>
}

export interface RoleUiProfile {
  homeView: NavigationItemId
  mission: string
  focus: string
}

const allAppRoles: UserRole[] = [
  'admin',
  'maintenance_engineer',
  'maintenance_technician',
  'maintenance_supervisor',
  'reliability_engineer',
  'planner',
  'operator',
]

export const jobNavigationItems: JobNavigationItem[] = [
  {
    id: 'commandCenter',
    label: 'Command Center',
    icon: 'command',
    purpose: 'Plant risk, urgent work, and production impact.',
    roles: allAppRoles,
    rolePriority: {
      operator: 1,
      maintenance_supervisor: 1,
      admin: 4,
      maintenance_engineer: 3,
      reliability_engineer: 3,
      planner: 3,
      maintenance_technician: 4,
    },
  },
  {
    id: 'monitoring',
    label: 'Monitoring',
    icon: 'monitoring',
    purpose: 'Live IoT sensor trends, alert state, and telemetry gaps.',
    roles: allAppRoles,
    rolePriority: {
      operator: 1,
      reliability_engineer: 1,
      maintenance_engineer: 2,
      maintenance_supervisor: 2,
      planner: 3,
      admin: 3,
      maintenance_technician: 3,
    },
  },
  {
    id: 'assets',
    label: 'Assets',
    icon: 'assets',
    purpose: 'Asset hierarchy, health, documents, and history.',
    roles: allAppRoles,
    rolePriority: {
      maintenance_engineer: 1,
      reliability_engineer: 2,
      operator: 2,
      admin: 3,
      maintenance_supervisor: 4,
      planner: 4,
      maintenance_technician: 2,
    },
  },
  {
    id: 'workExecution',
    label: 'Work Execution',
    icon: 'execution',
    purpose: 'Assigned work orders, technician assistant, and completion.',
    roles: ['admin', 'maintenance_technician', 'maintenance_supervisor', 'planner'],
    rolePriority: {
      maintenance_technician: 1,
      maintenance_supervisor: 2,
      planner: 2,
      admin: 2,
    },
  },
  {
    id: 'planning',
    label: 'Planning',
    icon: 'planning',
    purpose: 'Backlog, spares, PMs, outage windows, schedule, and dispatch.',
    roles: ['admin', 'planner', 'maintenance_supervisor'],
    rolePriority: {
      planner: 1,
      maintenance_supervisor: 3,
      admin: 5,
    },
  },
  {
    id: 'reports',
    label: 'Reports',
    icon: 'reports',
    purpose: 'Structured insights, abnormal alerts, decisions, and log entries.',
    roles: ['admin', 'maintenance_engineer', 'maintenance_supervisor', 'reliability_engineer', 'planner'],
    rolePriority: {
      maintenance_engineer: 2,
      maintenance_supervisor: 3,
      reliability_engineer: 3,
      planner: 3,
      admin: 6,
    },
  },
  {
    id: 'mlWorkspace',
    label: 'ML Workspace',
    icon: 'ml',
    purpose: 'Shadow ML comparison for anomalies, failure prediction, RUL, and PM ranking.',
    roles: ['admin', 'maintenance_engineer', 'reliability_engineer'],
    rolePriority: {
      reliability_engineer: 2,
      maintenance_engineer: 3,
      admin: 7,
    },
  },
  {
    id: 'reliability',
    label: 'Reliability',
    icon: 'reliability',
    purpose: 'RCA cases, prediction, anomalies, and reliability evidence.',
    roles: ['admin', 'maintenance_engineer', 'reliability_engineer'],
    rolePriority: {
      reliability_engineer: 1,
      maintenance_engineer: 2,
      admin: 6,
    },
  },
  {
    id: 'learningReview',
    label: 'Learning and Tuning',
    icon: 'learning',
    purpose: 'RAG health, approved examples, PEFT tuning, evaluation, and model promotion.',
    roles: [],
    rolePriority: {},
  },
  {
    id: 'admin',
    label: 'Admin',
    icon: 'admin',
    purpose: 'Users, ingestion, and system status.',
    roles: ['admin'],
    rolePriority: {
      admin: 1,
    },
  },
]

export const roleUiProfiles: Record<UserRole, RoleUiProfile> = {
  admin: {
    homeView: 'admin',
    mission: 'Own users, ingestion, configuration, and cross-role operating views.',
    focus: 'Admin control plane',
  },
  maintenance_engineer: {
    homeView: 'assets',
    mission: 'Diagnose asset health, review evidence, and turn findings into corrective work.',
    focus: 'Asset engineering',
  },
  maintenance_technician: {
    homeView: 'workExecution',
    mission: 'Execute assigned work safely with Neo-guided context and completion support.',
    focus: 'Assigned execution',
  },
  maintenance_supervisor: {
    homeView: 'commandCenter',
    mission: 'Prioritize urgent work, approve scope, and keep execution moving.',
    focus: 'Supervisor control',
  },
  reliability_engineer: {
    homeView: 'reliability',
    mission: 'Improve prediction, anomaly review, RCA quality, and reliability evidence.',
    focus: 'Reliability intelligence',
  },
  planner: {
    homeView: 'planning',
    mission: 'Convert backlog into executable plans with labor, materials, and outage windows aligned.',
    focus: 'Planning and dispatch',
  },
  operator: {
    homeView: 'commandCenter',
    mission: 'Monitor plant risk and production impact with read-only operating context.',
    focus: 'Operations watch',
  },
  iot_service: {
    homeView: 'commandCenter',
    mission: 'API ingestion account without interactive navigation.',
    focus: 'Service ingestion',
  },
}

export function homeViewForRole(role: UserRole): NavigationItemId {
  return roleUiProfiles[role].homeView
}

export function navigationForRole(role: UserRole) {
  return jobNavigationItems
    .filter((item) => item.roles.includes(role))
    .sort((left, right) => {
      const leftPriority = left.rolePriority[role] ?? 99
      const rightPriority = right.rolePriority[role] ?? 99
      if (leftPriority !== rightPriority) return leftPriority - rightPriority
      return left.label.localeCompare(right.label)
    })
}

export function canAccessAppView(role: UserRole, view: AppView) {
  const normalizedView: NavigationItemId = view === 'asset' ? 'assets' : view
  return navigationForRole(role).some((item) => item.id === normalizedView)
}

export function navigationItemForView(view: AppView) {
  const normalizedView: NavigationItemId = view === 'asset' ? 'assets' : view
  return jobNavigationItems.find((item) => item.id === normalizedView) ?? jobNavigationItems[0]
}
