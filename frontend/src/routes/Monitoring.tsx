import { Activity, AlertTriangle, RadioTower } from 'lucide-react'
import { formatDate } from '../appModel'
import type { MonitoringAsset, MonitoringDashboard, MonitoringSensorSeries, RiskLevel } from '../services/api'

export function MonitoringRoute({
  monitoring,
  onOpenAsset,
}: {
  monitoring: MonitoringDashboard | null
  onOpenAsset: (assetId: string) => void
}) {
  if (!monitoring) {
    return (
      <section className="detailPanel">
        <div className="sectionHeader">
          <RadioTower size={18} />
          <h2>Continuous Monitoring</h2>
        </div>
        <p className="emptyState">Loading live telemetry...</p>
      </section>
    )
  }

  const totalSensors = monitoring.assets.reduce((total, asset) => total + asset.active_sensor_count, 0)
  const staleAssets = monitoring.assets.filter((asset) => asset.stale).length
  const alertingAssets = monitoring.assets.filter((asset) => asset.active_alert_count > 0).length

  return (
    <section className="monitoringView">
      <div className="dashboardKpiBand" aria-label="Continuous monitoring KPI summary">
        <section className="kpiCard kpiRisk">
          <div className="kpiHeader">
            <h2>Live Sensors</h2>
          </div>
          <p><strong>{totalSensors}</strong> channels</p>
          <small>Recent readings grouped by asset and signal.</small>
        </section>
        <section className="kpiCard kpiEmergency">
          <div className="kpiHeader">
            <h2>Alerting Assets</h2>
          </div>
          <p><strong>{alertingAssets}</strong> assets</p>
          <small>Assets with active registered alerts.</small>
        </section>
        <section className="kpiCard kpiPerformance">
          <div className="kpiHeader">
            <h2>Telemetry Gaps</h2>
          </div>
          <p><strong>{staleAssets}</strong> assets</p>
          <small>Stale after {monitoring.stale_after_seconds} seconds without new readings.</small>
        </section>
      </div>

      <div className="monitoringGrid">
        {monitoring.assets.map((asset) => (
          <MonitoringAssetPanel asset={asset} key={asset.equipment.id} onOpenAsset={onOpenAsset} />
        ))}
      </div>
    </section>
  )
}

function MonitoringAssetPanel({
  asset,
  onOpenAsset,
}: {
  asset: MonitoringAsset
  onOpenAsset: (assetId: string) => void
}) {
  return (
    <article className={`monitoringAssetPanel ${asset.stale ? 'stale' : ''}`}>
      <header className="monitoringAssetHeader">
        <button type="button" className="workOrderCellButton" onClick={() => onOpenAsset(asset.equipment.id)}>
          <strong>{asset.equipment.name}</strong>
          <small>{asset.equipment.id}</small>
        </button>
        <span className={`riskBadge ${asset.highest_severity}`}>{asset.highest_severity}</span>
      </header>
      <div className="monitoringFacts">
        <span>
          <Activity size={15} />
          {asset.active_sensor_count} sensors
        </span>
        <span>
          <AlertTriangle size={15} />
          {asset.active_alert_count} alerts
        </span>
        <span>
          <RadioTower size={15} />
          {asset.latest_reading_timestamp ? formatDate(asset.latest_reading_timestamp) : 'No readings'}
        </span>
      </div>
      {asset.series.length ? (
        <div className="sensorChartGrid">
          {asset.series.map((series) => (
            <SensorChart series={series} key={series.signal} />
          ))}
        </div>
      ) : (
        <p className="emptyState">No sensor readings are available for this asset.</p>
      )}
    </article>
  )
}

function SensorChart({ series }: { series: MonitoringSensorSeries }) {
  const width = 260
  const height = 96
  const padding = 10
  const values = series.points.map((point) => point.value)
  const minValue = Math.min(...values, series.threshold)
  const maxValue = Math.max(...values, series.threshold)
  const valueRange = maxValue - minValue || 1
  const xStep = series.points.length > 1 ? (width - padding * 2) / (series.points.length - 1) : 0
  const pointCoordinates = series.points.map((point, index) => {
    const x = padding + index * xStep
    const y = height - padding - ((point.value - minValue) / valueRange) * (height - padding * 2)
    return `${x},${y}`
  })
  const thresholdY = height - padding - ((series.threshold - minValue) / valueRange) * (height - padding * 2)

  return (
    <section className={`sensorChart ${series.stale ? 'stale' : ''}`}>
      <div className="sensorChartHeader">
        <h3>{series.signal.replace(/_/g, ' ')}</h3>
        <span className={`riskBadge ${series.risk_level}`}>{riskLabel(series.risk_level)}</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${series.signal} sensor trend`}>
        <line className="thresholdLine" x1={padding} x2={width - padding} y1={thresholdY} y2={thresholdY} />
        {pointCoordinates.length > 1 && <polyline className="sensorLine" points={pointCoordinates.join(' ')} />}
        {series.points.map((point, index) => {
          const [cx, cy] = pointCoordinates[index].split(',').map(Number)
          return <circle className={point.value >= point.threshold ? 'anomalyPoint' : 'sensorPoint'} cx={cx} cy={cy} r={3} key={point.id} />
        })}
      </svg>
      <footer>
        <strong>{series.latest_value.toFixed(1)} {series.unit}</strong>
        <small>Threshold {series.threshold.toFixed(1)} {series.unit}</small>
      </footer>
    </section>
  )
}

function riskLabel(risk: RiskLevel) {
  return risk === 'low' ? 'normal' : risk
}
