import { AlertTriangle, BookOpenText, ClipboardCheck, Download, FileText, RefreshCw } from 'lucide-react'
import type {
  AbnormalAlertReport,
  DigitalMaintenanceLogEntry,
  MaintenanceDecisionSummary,
  MaintenanceInsightReportSummary,
  StructuredMaintenanceReport,
} from '../services/api'
import { formatDate } from '../appModel'

type ReportSectionLoading = {
  summary: boolean
  structuredReports: boolean
  abnormalAlerts: boolean
  decisionSummaries: boolean
  logEntries: boolean
}

function firstItems(items: string[], count = 3) {
  return items.slice(0, count)
}

function Percent({ value }: { value: number }) {
  return <>{Math.round(value * 100)}%</>
}

function SectionStatus({ loading, label }: { loading: boolean; label: string }) {
  if (!loading) return null
  return (
    <p className="inlineStatus" role="status">
      <span className="loadingSpinner" aria-hidden="true" />
      {label}
    </p>
  )
}

export function ReportsRoute({
  abnormalAlertReports,
  decisionSummaries,
  downloadMaintenanceInsights,
  exportLoading,
  loading,
  logEntries,
  refreshMaintenanceInsights,
  selectedEquipment,
  structuredReports,
  summary,
}: {
  abnormalAlertReports: AbnormalAlertReport[]
  decisionSummaries: MaintenanceDecisionSummary[]
  downloadMaintenanceInsights: (equipmentId?: string) => void
  exportLoading: boolean
  loading: ReportSectionLoading
  logEntries: DigitalMaintenanceLogEntry[]
  refreshMaintenanceInsights: (equipmentId?: string) => void
  selectedEquipment: string
  structuredReports: StructuredMaintenanceReport[]
  summary: MaintenanceInsightReportSummary | null
}) {
  const anyLoading = Object.values(loading).some(Boolean)
  const hasAnyContent = Boolean(
    summary || structuredReports.length || abnormalAlertReports.length || decisionSummaries.length || logEntries.length,
  )
  const exportScope = summary?.scope_equipment_id ?? undefined

  return (
    <section className="reportsRouteStack" aria-label="Structured maintenance insights and reports" aria-busy={anyLoading}>
      <section className="detailPanel pageIntroPanel">
        <div className="sectionHeader">
          <FileText size={20} />
          <div>
            <h2>Structured Maintenance Insights and Reports</h2>
            <small>Structured reports, abnormal alerts, decision summaries, and generated log entries.</small>
          </div>
        </div>
        <p className="emptyState">
          LLM-dependent report content is limited to recommendation Markdown exports that include Morpheus diagnosis,
          root-cause, reasoning, and learning-note fields when those recommendations were generated with a live provider.
          Structured insight reports, abnormal alert reports, decision summaries, and digital log entries are generated
          from deterministic plant data and persisted learning context.
        </p>
        <div className="reportToolbar" aria-label="Report actions">
          <button className="outlineButton" type="button" onClick={() => refreshMaintenanceInsights()}>
            <RefreshCw size={16} />
            Refresh plant
          </button>
          <button className="outlineButton" type="button" onClick={() => refreshMaintenanceInsights(selectedEquipment)}>
            <RefreshCw size={16} />
            Refresh selected asset
          </button>
          <button
            className="textButton"
            type="button"
            disabled={!hasAnyContent || anyLoading || exportLoading}
            onClick={() => downloadMaintenanceInsights(exportScope)}
          >
            <Download size={16} />
            {exportLoading ? 'Exporting...' : 'Export Markdown'}
          </button>
        </div>
        <SectionStatus loading={loading.summary} label="Loading report summary..." />
        {summary && (
          <p className="emptyState">
            Generated {formatDate(summary.generated_at)} for {summary.assets_reviewed} asset{summary.assets_reviewed === 1 ? '' : 's'}.
          </p>
        )}
      </section>

      {!hasAnyContent && (
        <section className="detailPanel">
          <p className="emptyState">{anyLoading ? 'Loading structured maintenance insights...' : 'Open Reports to generate maintenance insights.'}</p>
        </section>
      )}

      {hasAnyContent && (
        <section className="reportKpiBand" aria-label="Report summary counts">
          <div>
            <small>Structured reports</small>
            <strong>{summary?.structured_report_count ?? structuredReports.length}</strong>
          </div>
          <div>
            <small>Abnormal alerts</small>
            <strong>{summary?.abnormal_alert_report_count ?? abnormalAlertReports.length}</strong>
          </div>
          <div>
            <small>Decision summaries</small>
            <strong>{summary?.decision_summary_count ?? decisionSummaries.length}</strong>
          </div>
          <div>
            <small>Generated log entries</small>
            <strong>{summary?.maintenance_log_entry_count ?? logEntries.length}</strong>
          </div>
        </section>
      )}

      <section className="detailPanel">
        <div className="sectionHeader">
          <ClipboardCheck size={18} />
          <h2>Structured Maintenance Reports</h2>
        </div>
        <SectionStatus loading={loading.structuredReports} label="Loading structured maintenance reports..." />
        {structuredReports.length > 0 ? (
          <div className="reportGrid">
            {structuredReports.map((report) => (
              <article className="reportCard" key={report.id}>
                <div className="reportCardHeader">
                  <span>
                    <strong>{report.equipment_name}</strong>
                    <small>{report.equipment_id} · {report.area}</small>
                  </span>
                  <span className={`riskBadge ${report.risk_level}`}>{report.risk_level}</span>
                </div>
                <p>{report.report_summary}</p>
                <dl className="reportFactGrid">
                  <div><dt>Health</dt><dd>{report.health_score}%</dd></div>
                  <div><dt>Failure probability</dt><dd><Percent value={report.failure_probability} /></dd></div>
                  <div><dt>RUL</dt><dd>{report.remaining_useful_life_days} days</dd></div>
                  <div><dt>Owner</dt><dd>{report.recommended_owner}</dd></div>
                </dl>
                <h3>Immediate actions</h3>
                <ul>{firstItems(report.immediate_actions).map((item) => <li key={item}>{item}</li>)}</ul>
                <h3>Evidence</h3>
                <ul>{firstItems(report.evidence).map((item) => <li key={item}>{item}</li>)}</ul>
              </article>
            ))}
          </div>
        ) : (
          !loading.structuredReports && <p className="emptyState">No structured reports are available for the current scope.</p>
        )}
      </section>

      <section className="detailPanel">
        <div className="sectionHeader">
          <AlertTriangle size={18} />
          <h2>Abnormal Alert Reports</h2>
        </div>
        <SectionStatus loading={loading.abnormalAlerts} label="Loading abnormal alert reports..." />
        {abnormalAlertReports.length > 0 ? (
          <div className="abnormalAlertTable" aria-label="Abnormal alert reports table">
            <div className="abnormalAlertHead">
              <span>Alert</span>
              <span>Asset</span>
              <span>Signal</span>
              <span>Delta</span>
              <span>Decision</span>
            </div>
            {abnormalAlertReports.map((report) => (
              <div className="abnormalAlertRow" key={report.alert_id}>
                <span>
                  <strong>{report.alert_id}</strong>
                  <small className={`riskBadge ${report.severity}`}>{report.severity}</small>
                </span>
                <span>{report.equipment_name}</span>
                <span>{report.signal}</span>
                <span>{report.threshold_delta}{report.unit}</span>
                <span>{report.decision}</span>
              </div>
            ))}
          </div>
        ) : (
          !loading.abnormalAlerts && <p className="emptyState">No abnormal alert reports are available for the current scope.</p>
        )}
      </section>

      <section className="reportTwoColumn">
        {loading.decisionSummaries && (
          <section className="detailPanel">
            <SectionStatus loading label="Loading maintenance decision summaries..." />
          </section>
        )}
        {decisionSummaries.map((decisionSummary) => (
          <section className="detailPanel" key={decisionSummary.audience}>
            <div className="sectionHeader">
              <ClipboardCheck size={18} />
              <div>
                <h2>{decisionSummary.title}</h2>
                <small>{decisionSummary.audience}</small>
              </div>
            </div>
            <p>{decisionSummary.summary}</p>
            <h3>Decisions</h3>
            <ul>{decisionSummary.decisions.map((item) => <li key={item}>{item}</li>)}</ul>
            <h3>Next actions</h3>
            <ul>{decisionSummary.next_actions.map((item) => <li key={item}>{item}</li>)}</ul>
          </section>
        ))}
        {!loading.decisionSummaries && decisionSummaries.length === 0 && (
          <section className="detailPanel">
            <p className="emptyState">No maintenance decision summaries are available for the current scope.</p>
          </section>
        )}
      </section>

      <section className="detailPanel">
        <div className="sectionHeader">
          <BookOpenText size={18} />
          <h2>Equipment Digital Maintenance Log Entries</h2>
        </div>
        <SectionStatus loading={loading.logEntries} label="Loading digital maintenance log entries..." />
        {logEntries.length > 0 ? (
          <div className="maintenanceLogList">
            {logEntries.map((entry) => (
              <article key={`${entry.equipment_id}-${entry.timestamp}`}>
                <strong>{entry.equipment_name}</strong>
                <small>{entry.equipment_id} · {formatDate(entry.timestamp)} · {entry.entry_type}</small>
                <p>{entry.content}</p>
              </article>
            ))}
          </div>
        ) : (
          !loading.logEntries && <p className="emptyState">No generated digital log entries are available for the current scope.</p>
        )}
      </section>
    </section>
  )
}
