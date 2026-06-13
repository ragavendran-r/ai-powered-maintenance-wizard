import type { WorkOrderStatus } from './services/api'

export const workOrderStatusDetails: Record<WorkOrderStatus, { label: string; description: string }> = {
  WAPPR: {
    label: 'Waiting for approval',
    description: 'Supervisor approval is required before field work can start.',
  },
  APPR: {
    label: 'Approved',
    description: 'The work order is approved and ready for technician execution.',
  },
  INPRG: {
    label: 'In progress',
    description: 'The assigned technician has started field execution.',
  },
  WMATL: {
    label: 'Waiting for material',
    description: 'Execution is blocked until required parts or consumables are available.',
  },
  COMP: {
    label: 'Completed',
    description: 'Technician work is complete and ready for closeout review.',
  },
  CLOSE: {
    label: 'Closed',
    description: 'The work order has been reviewed and closed.',
  },
}

export const workOrderStatusFlow: WorkOrderStatus[] = ['WAPPR', 'APPR', 'INPRG', 'WMATL', 'COMP', 'CLOSE']

export function workOrderStatusDetail(status: WorkOrderStatus) {
  return workOrderStatusDetails[status]
}

const workOrderStatusPattern = new RegExp(`\\b(${workOrderStatusFlow.join('|')})\\b`, 'g')

export function isWorkOrderStatus(value: string): value is WorkOrderStatus {
  return Object.prototype.hasOwnProperty.call(workOrderStatusDetails, value)
}

export function workOrderStatusLabel(status: WorkOrderStatus) {
  return workOrderStatusDetail(status).label
}

export function formatWorkOrderStatusText(text: string) {
  return text.replace(workOrderStatusPattern, (status) => workOrderStatusLabel(status as WorkOrderStatus))
}

export function formatTableCell(column: string, value: unknown) {
  const text = String(value ?? '')
  if (column.trim().toLowerCase() === 'status' && isWorkOrderStatus(text)) {
    return workOrderStatusLabel(text)
  }
  return text
}
