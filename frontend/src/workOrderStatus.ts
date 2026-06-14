import type { WorkOrder, WorkOrderStatus } from './services/api'

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

export const workOrderStatusFlow: WorkOrderStatus[] = ['WAPPR', 'APPR', 'WMATL', 'INPRG', 'COMP', 'CLOSE']

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

const materialBlockerStatuses = new Set(['blocked', 'waiting_procurement', 'reorder_requested'])
const materialUnreadyStatuses = new Set(['blocked', 'pending'])

export function hasWorkOrderMaterialBlocker(workOrder: WorkOrder) {
  if (materialUnreadyStatuses.has(workOrder.material_readiness)) return true
  if (materialBlockerStatuses.has(workOrder.material_blocker_status)) return true
  return workOrder.spare_reservations.some((reservation) => {
    if (materialBlockerStatuses.has(reservation.blocker_status)) return true
    return (
      reservation.required_qty > 0 &&
      reservation.reserved_qty < reservation.required_qty &&
      reservation.available_qty < reservation.required_qty
    )
  })
}

export function effectiveWorkOrderStatus(workOrder: WorkOrder): WorkOrderStatus {
  if (
    hasWorkOrderMaterialBlocker(workOrder) &&
    ['APPR', 'WMATL', 'INPRG'].includes(workOrder.status)
  ) {
    return 'WMATL'
  }
  return workOrder.status
}

export function workOrderStartBlockReason(workOrder: WorkOrder) {
  if (!hasWorkOrderMaterialBlocker(workOrder)) return ''
  const blockedSpare = workOrder.spare_reservations.find((reservation) => {
    if (materialBlockerStatuses.has(reservation.blocker_status)) return true
    return (
      reservation.required_qty > 0 &&
      reservation.reserved_qty < reservation.required_qty &&
      reservation.available_qty < reservation.required_qty
    )
  })
  if (blockedSpare) {
    const expectedDate = blockedSpare.expected_available_date || 'not recorded'
    return `${blockedSpare.spare_name} is not ready; expected availability is ${expectedDate}.`
  }
  return workOrder.material_blocker_note || 'Material readiness is blocked or pending.'
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
