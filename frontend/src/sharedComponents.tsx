import { useState } from 'react'
import type { ReactNode } from 'react'
import { ClipboardList } from 'lucide-react'
import type {
  AssetDetail,
  AssetDocument,
  AssetListItem,
  AssetMetricSnapshot,
  AssetPerformanceChart,
  AssetReliabilityMetric,
  AssetSubsystem,
  AuthUser,
  HealthSummary,
  MaintenanceEvent,
  NeoTable,
  TechnicianAssistantResponse,
  UserRole,
  WorkOrder,
  WorkOrderStatus,
} from './services/api'
import { formatDate } from './appModel'
import {
  formatTableCell,
  workOrderStatusDetail,
  workOrderStatusFlow,
} from './workOrderStatus'

export function Metric({ icon, label, value }: { icon: ReactNode; label: string; value: string }) {
  return (
    <div className="metric">
      <span className="metricIcon">{icon}</span>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

export function KpiCard({
  title,
  value,
  unit,
  detail,
  ai,
  className = '',
}: {
  title: string
  value: string
  unit: string
  detail: string
  ai?: string
  className?: string
}) {
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

export function NeoResultTable({ table }: { table: NeoTable }) {
  return (
    <div className="neoResultTable" aria-label={`${table.title} results table`}>
      <div className="neoResultHead" style={{ gridTemplateColumns: `repeat(${table.columns.length}, minmax(120px, 1fr))` }}>
        {table.columns.map((column) => <span key={column}>{column}</span>)}
      </div>
      {table.rows.map((row, index) => (
        <div className="neoResultRow" style={{ gridTemplateColumns: `repeat(${table.columns.length}, minmax(120px, 1fr))` }} key={`${table.title}-${index}`}>
          {table.columns.map((column) => <span key={column}>{formatTableCell(column, row[column])}</span>)}
        </div>
      ))}
    </div>
  )
}

export function AssetsTable({ assets, onOpen }: { assets: AssetListItem[]; onOpen: (assetId: string) => void }) {
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

export function AssetProfileFacts({ detail }: { detail: AssetDetail }) {
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

export function AssetMetricTile({ metric, fallbackValue }: { metric?: AssetMetricSnapshot; fallbackValue?: number }) {
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

export function AssetMetricGrid({ metrics }: { metrics: AssetMetricSnapshot[] }) {
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

export function AssetSubsystemList({ subsystems }: { subsystems: AssetSubsystem[] }) {
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

export function MaintenanceEventTable({ events }: { events: MaintenanceEvent[] }) {
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

export function SignalLineChartCard({ chart }: { chart: AssetPerformanceChart }) {
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

export function ReliabilityMetricGrid({ metrics }: { metrics: AssetReliabilityMetric[] }) {
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

export function AssetDocumentList({ documents }: { documents: AssetDocument[] }) {
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

export function KnowledgeEvidenceList({ evidence }: { evidence: AssetDetail['knowledge'] }) {
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

export function StatusBadge({ status }: { status: WorkOrderStatus }) {
  const detail = workOrderStatusDetail(status)
  return (
    <span className={`workOrderStatusBadge status-${status.toLowerCase()}`} title={`${detail.label}: ${detail.description}`}>
      <strong>{detail.label}</strong>
    </span>
  )
}

export function TechnicianExecutionCard({
  assistant,
  isLoading,
  onComplete,
  onStart,
  workOrder,
}: {
  assistant: TechnicianAssistantResponse | null
  isLoading: boolean
  onComplete: () => void
  onStart: (workOrderId: string) => void
  workOrder: WorkOrder
}) {
  const statusDetail = workOrderStatusDetail(workOrder.status)
  const canStart = ['APPR', 'WMATL'].includes(workOrder.status)
  const canComplete = Boolean(assistant) && !['COMP', 'CLOSE'].includes(workOrder.status)
  const steps = [
    {
      title: 'Confirm readiness',
      detail: `${statusDetail.label}: ${statusDetail.description}`,
      state: ['WAPPR'].includes(workOrder.status) ? 'current' : 'done',
    },
    {
      title: 'Start field execution',
      detail: canStart ? 'Move this approved work order to in progress before executing field work.' : 'Field execution has already moved past the start gate.',
      state: ['APPR', 'WMATL'].includes(workOrder.status) ? 'current' : ['INPRG', 'COMP', 'CLOSE'].includes(workOrder.status) ? 'done' : 'pending',
    },
    {
      title: 'Capture observations',
      detail: assistant ? assistant.next_prompt : 'Use Neo to record abnormal conditions, measurements, and evidence from the asset.',
      state: assistant ? 'done' : ['INPRG'].includes(workOrder.status) ? 'current' : 'pending',
    },
    {
      title: 'Apply guided action',
      detail: assistant?.recommendations[0] ?? workOrder.recommended_action,
      state: assistant ? 'current' : 'pending',
    },
    {
      title: 'Submit completion',
      detail: assistant?.completion_summary ?? 'Completion unlocks after Neo provides the problem code, failure class, and summary.',
      state: ['COMP', 'CLOSE'].includes(workOrder.status) ? 'done' : assistant ? 'current' : 'pending',
    },
  ]

  return (
    <section className="technicianExecutionCard" aria-label="Technician execution workflow">
      <div className="sectionHeader">
        <ClipboardList size={18} />
        <div>
          <h2>Technician Execution</h2>
          <small>{workOrder.id} · {workOrder.title}</small>
        </div>
      </div>
      <div className="executionStatusLine">
        <StatusBadge status={workOrder.status} />
        <span>{statusDetail.description}</span>
      </div>
      <ol className="executionSteps">
        {steps.map((step, index) => (
          <li className={step.state} key={step.title}>
            <span>{index + 1}</span>
            <div>
              <strong>{step.title}</strong>
              <p>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>
      <div className="executionActions">
        <button
          className="outlineButton"
          type="button"
          disabled={!canStart || isLoading}
          onClick={() => onStart(workOrder.id)}
        >
          Start work
        </button>
        <button
          className="textButton"
          type="button"
          disabled={!canComplete || isLoading}
          onClick={onComplete}
        >
          Submit completed work
        </button>
      </div>
    </section>
  )
}

export function WorkOrderTable({
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
              <StatusBadge status={order.status} />
              {!compact && <small>{workOrderStatusDetail(order.status).description}</small>}
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

export function BarChart({ assets }: { assets: HealthSummary[] }) {
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

export function MiniBars({ values }: { values: number[] }) {
  return (
    <div className="miniBars">
      {values.map((value, index) => (
        <span style={{ height: `${value}%` }} key={`${value}-${index}`} />
      ))}
    </div>
  )
}

export function StatusTimeline({ status }: { status: WorkOrderStatus }) {
  const activeIndex = Math.max(0, workOrderStatusFlow.indexOf(status))
  return (
    <div className="statusTimeline" aria-label="Work order status">
      {workOrderStatusFlow.map((item, index) => (
        <span className={index <= activeIndex ? 'active' : ''} key={item}>
          <i />
          <strong>{workOrderStatusDetail(item).label}</strong>
        </span>
      ))}
    </div>
  )
}
