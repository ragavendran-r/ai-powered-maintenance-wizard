import type { AuthUser, UserRole } from './services/api'

export type Permission =
  | 'adminUsers'
  | 'approveWorkOrders'
  | 'assignWorkOrders'
  | 'createWorkOrders'
  | 'decisionSupport'
  | 'feedback'
  | 'ingestion'
  | 'learningReview'
  | 'streaming'
  | 'supervisorAssistant'
  | 'technicianAssistant'

export const permissionsByRole: Record<UserRole, readonly Permission[]> = {
  admin: [
    'adminUsers',
    'approveWorkOrders',
    'assignWorkOrders',
    'createWorkOrders',
    'decisionSupport',
    'feedback',
    'ingestion',
    'learningReview',
    'streaming',
  ],
  maintenance_engineer: [
    'createWorkOrders',
    'decisionSupport',
    'feedback',
  ],
  maintenance_technician: [
    'createWorkOrders',
    'technicianAssistant',
  ],
  maintenance_supervisor: [
    'approveWorkOrders',
    'assignWorkOrders',
    'createWorkOrders',
    'decisionSupport',
    'supervisorAssistant',
  ],
  reliability_engineer: [
    'createWorkOrders',
    'decisionSupport',
    'feedback',
    'ingestion',
    'streaming',
  ],
  planner: [
    'assignWorkOrders',
    'createWorkOrders',
    'decisionSupport',
  ],
  operator: [],
  iot_service: [],
}

export type UserPermissions = Record<`can${Capitalize<Permission>}`, boolean>

export function hasPermission(user: AuthUser | null | undefined, permission: Permission) {
  return Boolean(user && permissionsByRole[user.role].includes(permission))
}

export function getUserPermissions(user: AuthUser | null | undefined): UserPermissions {
  return {
    canAdminUsers: hasPermission(user, 'adminUsers'),
    canApproveWorkOrders: hasPermission(user, 'approveWorkOrders'),
    canAssignWorkOrders: hasPermission(user, 'assignWorkOrders'),
    canCreateWorkOrders: hasPermission(user, 'createWorkOrders'),
    canDecisionSupport: hasPermission(user, 'decisionSupport'),
    canFeedback: hasPermission(user, 'feedback'),
    canIngestion: hasPermission(user, 'ingestion'),
    canLearningReview: hasPermission(user, 'learningReview'),
    canStreaming: hasPermission(user, 'streaming'),
    canSupervisorAssistant: hasPermission(user, 'supervisorAssistant'),
    canTechnicianAssistant: hasPermission(user, 'technicianAssistant'),
  }
}
