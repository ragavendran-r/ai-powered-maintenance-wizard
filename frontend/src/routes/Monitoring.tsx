import { useEffect, useRef, useState } from 'react'
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
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [measuredWidth, setMeasuredWidth] = useState(640)
  const width = Math.max(320, measuredWidth)
  const height = 170
  const paddingLeft = 46
  const paddingRight = 18
  const paddingTop = 12
  const paddingBottom = 34
  const plotWidth = width - paddingLeft - paddingRight
  const plotHeight = height - paddingTop - paddingBottom
  const values = series.points.map((point) => point.value)
  const minValue = Math.min(...values, series.threshold)
  const maxValue = Math.max(...values, series.threshold)
  const valueRange = maxValue - minValue || 1
  const xStep = series.points.length > 1 ? plotWidth / (series.points.length - 1) : 0
  const pointCoordinates = series.points.map((point, index) => {
    const x = paddingLeft + index * xStep
    const y = paddingTop + plotHeight - ((point.value - minValue) / valueRange) * plotHeight
    return `${x},${y}`
  })
  const thresholdY = paddingTop + plotHeight - ((series.threshold - minValue) / valueRange) * plotHeight
  const formattedSignal = series.signal.replace(/_/g, ' ')
  const xAxisLabel = 'Time'
  const yAxisLabel = `${formattedSignal} (${series.unit})`

  useEffect(() => {
    const element = svgRef.current
    if (!element) return undefined
    const updateWidth = () => {
      const nextWidth = Math.round(element.getBoundingClientRect().width)
      if (nextWidth > 0) setMeasuredWidth(nextWidth)
    }
    updateWidth()
    if (typeof ResizeObserver === 'undefined') return undefined
    const observer = new ResizeObserver(updateWidth)
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return (
    <section className={`sensorChart ${series.stale ? 'stale' : ''}`}>
      <div className="sensorChartHeader">
        <h3>{formattedSignal}</h3>
        <span className={`riskBadge ${series.risk_level}`}>{riskLabel(series.risk_level)}</span>
      </div>
      <svg ref={svgRef} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${series.signal} sensor trend with ${xAxisLabel} x-axis and ${yAxisLabel} y-axis`}>
        <line className="sensorAxis" x1={paddingLeft} x2={width - paddingRight} y1={paddingTop + plotHeight} y2={paddingTop + plotHeight} />
        <line className="sensorAxis" x1={paddingLeft} x2={paddingLeft} y1={paddingTop} y2={paddingTop + plotHeight} />
        <text className="sensorAxisLabel sensorAxisLabelX" x={paddingLeft + plotWidth / 2} y={height - 8}>{xAxisLabel}</text>
        <text className="sensorAxisLabel sensorAxisLabelY" x={-(paddingTop + plotHeight / 2)} y={14} transform="rotate(-90)">{yAxisLabel}</text>
        <line className="thresholdLine" x1={paddingLeft} x2={width - paddingRight} y1={thresholdY} y2={thresholdY} />
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
