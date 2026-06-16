import type { RefObject } from 'react'
import { Briefcase, CheckCircle2, Download, Sparkles } from 'lucide-react'
import type {
  AssetDetail,
  AssetDetailSection,
  PredictionResponse,
  Recommendation,
  WorkOrder,
} from '../services/api'
import type { AssetTab } from '../appModel'
import {
  diagnosisAssistantName,
  formatDate,
  reliabilityAssistantName,
} from '../appModel'
import { FormattedAssistantContent } from '../assistantContent'
import {
  AssetDocumentList,
  AssetMetricGrid,
  AssetMetricTile,
  AssetProfileFacts,
  AssetSubsystemList,
  KnowledgeEvidenceList,
  MaintenanceEventTable,
  ReliabilityMetricGrid,
  SignalLineChartCard,
  WorkOrderTable,
} from '../sharedComponents'

export function AssetDetailRoute({
  approveWorkOrder,
  assetDetail,
  assetDetailLoading,
  assetLoadedSections,
  assetMessage,
  assetReliabilityLoading,
  assetReliabilityMessage,
  assetReliabilityPrediction,
  assetReliabilityProvider,
  assetReliabilityText,
  assetReliabilityUsedLive,
  assetSectionLoading,
  assetTab,
  assetWorkOrders,
  canApproveWorkOrders,
  canCreateWorkOrders,
  canDecision,
  canFeedback,
  canTechnicianAssistant,
  createWorkOrderFromContext,
  diagnosisLoading,
  diagnosisMessage,
  diagnosisProvider,
  diagnosisStreamText,
  diagnosisStreaming,
  diagnosisUsedLive,
  downloadReport,
  feedbackActionTaken,
  feedbackNotes,
  feedbackOutcome,
  feedbackRootCause,
  morpheusProgressRef,
  onOpenWorkOrder,
  recommendation,
  reliabilityStreamRef,
  runDiagnosis,
  selectedEquipment,
  sendFeedback,
  setAssetTab,
  setFeedbackActionTaken,
  setFeedbackNotes,
  setFeedbackOutcome,
  setFeedbackRootCause,
  startWorkOrder,
}: {
  approveWorkOrder: (workOrderId: string) => void
  assetDetail: AssetDetail | null
  assetDetailLoading: boolean
  assetLoadedSections: AssetDetailSection[]
  assetMessage: string
  assetReliabilityLoading: boolean
  assetReliabilityMessage: string
  assetReliabilityPrediction: PredictionResponse | null
  assetReliabilityProvider: string
  assetReliabilityText: string
  assetReliabilityUsedLive: boolean
  assetSectionLoading: Partial<Record<AssetDetailSection, boolean>>
  assetTab: AssetTab
  assetWorkOrders: WorkOrder[]
  canApproveWorkOrders: boolean
  canCreateWorkOrders: boolean
  canDecision: boolean
  canFeedback: boolean
  canTechnicianAssistant: boolean
  createWorkOrderFromContext: (source?: Recommendation) => void
  diagnosisLoading: boolean
  diagnosisMessage: string
  diagnosisProvider: string
  diagnosisStreamText: string
  diagnosisStreaming: boolean
  diagnosisUsedLive: boolean
  downloadReport: () => void
  feedbackActionTaken: string
  feedbackNotes: string
  feedbackOutcome: string
  feedbackRootCause: string
  morpheusProgressRef: RefObject<HTMLDivElement | null>
  onOpenWorkOrder: (workOrderId: string) => void
  recommendation: Recommendation | null
  reliabilityStreamRef: RefObject<HTMLDivElement | null>
  runDiagnosis: () => void
  selectedEquipment: string
  sendFeedback: (status: 'accepted' | 'rejected' | 'corrected') => void
  setAssetTab: (tab: AssetTab) => void
  setFeedbackActionTaken: (value: string) => void
  setFeedbackNotes: (value: string) => void
  setFeedbackOutcome: (value: string) => void
  setFeedbackRootCause: (value: string) => void
  startWorkOrder: (workOrderId: string) => void
}) {
  const assetMetricByKey = new Map((assetDetail?.metrics ?? []).map((metric) => [metric.metric_key, metric]))
  const assetHealth = assetDetail?.health
  const assetProfile = assetDetail?.profile
  const isAssetSectionPending = (section: AssetDetailSection) =>
    !assetLoadedSections.includes(section) || Boolean(assetSectionLoading[section])
  const assetLoadingPanel = (label: string) => (
    <section className="detailPanel widePanel">
      <p className="emptyState">Loading {label} data...</p>
    </section>
  )

  const recommendationPanel = (
    <RecommendationPanel
      canCreateWorkOrders={canCreateWorkOrders}
      canFeedback={canFeedback}
      createWorkOrderFromContext={createWorkOrderFromContext}
      diagnosisLoading={diagnosisLoading}
      diagnosisMessage={diagnosisMessage}
      diagnosisProvider={diagnosisProvider}
      diagnosisStreamText={diagnosisStreamText}
      diagnosisStreaming={diagnosisStreaming}
      diagnosisUsedLive={diagnosisUsedLive}
      downloadReport={downloadReport}
      feedbackActionTaken={feedbackActionTaken}
      feedbackNotes={feedbackNotes}
      feedbackOutcome={feedbackOutcome}
      feedbackRootCause={feedbackRootCause}
      morpheusProgressRef={morpheusProgressRef}
      recommendation={recommendation}
      sendFeedback={sendFeedback}
      setFeedbackActionTaken={setFeedbackActionTaken}
      setFeedbackNotes={setFeedbackNotes}
      setFeedbackOutcome={setFeedbackOutcome}
      setFeedbackRootCause={setFeedbackRootCause}
    />
  )

  const assetSummaryTab = assetDetail ? (
    <div className="assetSummaryGrid">
      <section className="detailPanel summarySubsystems">
        <h2>Sub-systems</h2>
        <AssetSubsystemList subsystems={assetDetail.subsystems} />
      </section>
      <section className="healthStack summaryHealthStack">
        <AssetMetricTile metric={assetMetricByKey.get('health')} fallbackValue={assetHealth?.health_score} />
        <AssetMetricTile metric={assetMetricByKey.get('efficiency')} />
        <AssetMetricTile metric={assetMetricByKey.get('risk')} />
      </section>
      <section className="detailPanel assetFactsPanel summaryProfile">
        <h2>Asset profile</h2>
        <AssetProfileFacts detail={assetDetail} />
      </section>
      <section className="detailPanel performanceInsights summaryInsight">
        <div className="sectionHeader">
          <Sparkles size={18} />
          <h2>Performance insights</h2>
        </div>
        <div className="insightHero">
          <span>Risk</span>
          <strong>{100 - (assetHealth?.health_score ?? 0)}%</strong>
          <small>Probable cause</small>
          <h2>{assetHealth?.active_alerts[0]?.message ?? assetHealth?.notes[0]}</h2>
        </div>
        <button className="outlineButton" disabled={diagnosisLoading} onClick={runDiagnosis}>
          {diagnosisLoading ? <span className="loadingSpinner" aria-hidden="true" /> : null}
          View data
        </button>
      </section>
      <section className="detailPanel summaryActions">
        <h2>Recommended actions</h2>
        <ol className="actionList">
          {assetDetail.recommendations.slice(0, 3).map((action) => (
            <li key={action.id}>
              <strong>{action.title}</strong>
              <span>{action.description}</span>
            </li>
          ))}
        </ol>
        {canCreateWorkOrders && (
          <button className="outlineButton" onClick={() => createWorkOrderFromContext(recommendation ?? undefined)}>
            Create work order
          </button>
        )}
      </section>
      {canDecision && (
        <section className="detailPanel assetDecisionPanel">
          <div className="sectionHeader">
            <CheckCircle2 size={18} />
            <h2>Diagnosis and recommendation</h2>
          </div>
          <div className="diagnoseActionRow">
            <button className="textButton" disabled={diagnosisLoading} onClick={runDiagnosis}>
              {diagnosisLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <CheckCircle2 size={16} />}
              {diagnosisLoading ? `${diagnosisAssistantName} is diagnosing...` : `Run ${diagnosisAssistantName}`}
            </button>
          </div>
          {recommendationPanel}
        </section>
      )}
    </div>
  ) : null

  const assetTabContent = assetDetail ? (
    <>
      {assetTab === 'summary' && assetSummaryTab}
      {assetTab === 'maintenance' && (isAssetSectionPending('maintenance') ? assetLoadingPanel('maintenance') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Maintenance history</h2>
            <MaintenanceEventTable events={assetDetail.maintenance_events} />
          </section>
          <section className="detailPanel widePanel">
            <h2>Related work orders</h2>
            <WorkOrderTable
              workOrders={assetWorkOrders}
              compact
              canApprove={canApproveWorkOrders}
              canStart={canTechnicianAssistant}
              onApprove={approveWorkOrder}
              onStart={startWorkOrder}
              onOpen={onOpenWorkOrder}
            />
          </section>
        </div>
      ))}
      {assetTab === 'performance' && (isAssetSectionPending('performance') ? assetLoadingPanel('performance') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Performance metrics</h2>
            <AssetMetricGrid metrics={assetDetail.metrics} />
          </section>
          {assetDetail.performance_charts.map((chart) => (
            <SignalLineChartCard chart={chart} key={chart.signal} />
          ))}
        </div>
      ))}
      {assetTab === 'reliability' && (isAssetSectionPending('reliability') ? assetLoadingPanel('reliability') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Reliability metrics</h2>
            <ReliabilityMetricGrid metrics={assetDetail.reliability_metrics} />
          </section>
          <section className="detailPanel widePanel smithPredictionPanel">
            <div className="assistantHeaderCompact">
              <span className="assistantAvatar">S</span>
              <div>
                <h2>{reliabilityAssistantName}</h2>
                <small>Predictive failure assistant</small>
              </div>
            </div>
            <div
              className="reliabilityPredictionStream"
              ref={reliabilityStreamRef}
              aria-label={`${reliabilityAssistantName} failure prediction stream`}
              aria-live="polite"
            >
              {(assetReliabilityProvider || assetReliabilityLoading) && (
                <small className="providerLine">
                  {assetReliabilityLoading && <span className="loadingSpinner" aria-hidden="true" />}
                  {assetReliabilityProvider
                    ? `${assetReliabilityUsedLive ? 'Live LLM' : 'LLM unavailable'} · ${assetReliabilityProvider}`
                    : `${reliabilityAssistantName} is starting the prediction stream`}
                </small>
              )}
              {assetReliabilityText && <FormattedAssistantContent content={assetReliabilityText} />}
              {assetReliabilityMessage && <p className="inlineStatus errorText">{assetReliabilityMessage}</p>}
              {assetReliabilityPrediction ? (
                <>
                  <div className="predictionSummary">
                    <span className={`riskBadge ${assetReliabilityPrediction.risk_level}`}>{assetReliabilityPrediction.risk_level}</span>
                    <strong>{Math.round(assetReliabilityPrediction.failure_probability * 100)}% failure probability</strong>
                    <small>{assetReliabilityPrediction.remaining_useful_life_days} days estimated RUL</small>
                  </div>
                  <PredictionModelAudit prediction={assetReliabilityPrediction} />
                  <ul className="actionList">
                    {assetReliabilityPrediction.drivers.slice(0, 6).map((driver) => <li key={driver}>{driver}</li>)}
                  </ul>
                </>
              ) : !assetReliabilityText && !assetReliabilityMessage && (
                <p className="emptyState">{reliabilityAssistantName} is streaming live LLM failure prediction...</p>
              )}
            </div>
          </section>
        </div>
      ))}
      {assetTab === 'documents' && (isAssetSectionPending('documents') ? assetLoadingPanel('document') : (
        <div className="assetTabGrid">
          <section className="detailPanel widePanel">
            <h2>Knowledge Retrieval</h2>
            <KnowledgeEvidenceList evidence={assetDetail.knowledge} />
          </section>
          <section className="detailPanel widePanel">
            <h2>SOP, manual, log, and history evidence</h2>
            <AssetDocumentList documents={assetDetail.documents} />
          </section>
        </div>
      ))}
      {assetTab === 'workOrders' && (isAssetSectionPending('work_orders') ? assetLoadingPanel('work order') : (
        <section className="detailPanel widePanel">
          <h2>Related work orders</h2>
          <WorkOrderTable
            workOrders={assetWorkOrders}
            canApprove={canApproveWorkOrders}
            canStart={canTechnicianAssistant}
            onApprove={approveWorkOrder}
            onStart={startWorkOrder}
            onOpen={onOpenWorkOrder}
          />
        </section>
      ))}
    </>
  ) : null

  return (
    <section className="assetDetailGrid">
      <div className="pageHeader">
        <p className="breadcrumb">Operational dashboard / Assets /</p>
        <h1>{assetProfile?.name ?? selectedEquipment}</h1>
        <span>{assetProfile ? `Last updated ${formatDate(assetProfile.last_updated)}` : 'Loading live asset data'}</span>
      </div>
      <div className="planningTabsShell assetTabsShell">
        <div className="planningTabRow" role="tablist" aria-label="Asset detail tabs">
        {(['summary', 'maintenance', 'performance', 'reliability', 'documents', 'workOrders'] as AssetTab[]).map((tab) => (
          <button
            aria-controls={`asset-tab-${tab}`}
            aria-selected={assetTab === tab}
            className={assetTab === tab ? 'selected' : ''}
            id={`asset-tab-trigger-${tab}`}
            key={tab}
            onClick={() => setAssetTab(tab)}
            role="tab"
            type="button"
          >
            {tab === 'workOrders' ? 'Work Orders' : tab[0].toUpperCase() + tab.slice(1)}
          </button>
        ))}
        </div>
      </div>
      {assetDetailLoading && <section className="detailPanel widePanel"><p className="emptyState">Loading asset detail data...</p></section>}
      {!assetDetailLoading && assetMessage && <section className="detailPanel widePanel"><p className="inlineStatus errorText">{assetMessage}</p></section>}
      {assetDetail && (
        <div
          aria-labelledby={`asset-tab-trigger-${assetTab}`}
          className="assetTabPanel"
          id={`asset-tab-${assetTab}`}
          role="tabpanel"
        >
          {assetTabContent}
        </div>
      )}
    </section>
  )
}

function PredictionModelAudit({ prediction }: { prediction: PredictionResponse }) {
  const interval = prediction.confidence_interval
  const model = prediction.model_version
  const evaluation = prediction.model_evaluation
  const evidence = prediction.prediction_evidence ?? []
  const trend = prediction.degradation_trend ?? []

  return (
    <div className="predictionModelAudit" aria-label="Prediction model evidence">
      <div className="predictionAuditGrid">
        <div>
          <span>Model version</span>
          <strong>{model ? `${model.name} ${model.version}` : 'Unavailable'}</strong>
          {model && <small>{model.algorithm}</small>}
        </div>
        <div>
          <span>Backtest</span>
          <strong>{evaluation ? `${Math.round(evaluation.precision * 100)}% precision / ${Math.round(evaluation.recall * 100)}% recall` : 'Unavailable'}</strong>
          {evaluation && <small>{evaluation.sample_count} samples · {evaluation.mean_absolute_rul_error_days} day RUL MAE</small>}
        </div>
        <div>
          <span>Confidence interval</span>
          <strong>
            {interval
              ? `${Math.round(interval.lower_probability * 100)}-${Math.round(interval.upper_probability * 100)}% probability`
              : 'Unavailable'}
          </strong>
          {interval && <small>{interval.lower_rul_days}-{interval.upper_rul_days} RUL days</small>}
        </div>
      </div>
      {interval && <p className="predictionAuditNote">{interval.rationale}</p>}
      {evidence.length > 0 && (
        <div>
          <h3>Prediction Evidence</h3>
          <ul className="predictionEvidenceList">
            {evidence.slice(0, 5).map((item) => (
              <li key={`${item.source_type}-${item.source_id}-${item.title}`}>
                <strong>{item.title}</strong>
                <span>{item.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {trend.length > 0 && (
        <div>
          <h3>Degradation Trend History</h3>
          <div className="degradationTrendList">
            {trend.slice(-6).map((point) => (
              <div key={`${point.signal}-${point.timestamp}`}>
                <span>{formatDate(point.timestamp)}</span>
                <strong>{point.signal.replace(/_/g, ' ')}</strong>
                <small>
                  {point.value}{point.unit} vs {point.threshold}{point.unit} · {Math.round(point.normalized_severity * 100)}% severity · {point.estimated_rul_days}d trend RUL
                </small>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function RecommendationPanel({
  canCreateWorkOrders,
  canFeedback,
  createWorkOrderFromContext,
  diagnosisLoading,
  diagnosisMessage,
  diagnosisProvider,
  diagnosisStreamText,
  diagnosisStreaming,
  diagnosisUsedLive,
  downloadReport,
  feedbackActionTaken,
  feedbackNotes,
  feedbackOutcome,
  feedbackRootCause,
  morpheusProgressRef,
  recommendation,
  sendFeedback,
  setFeedbackActionTaken,
  setFeedbackNotes,
  setFeedbackOutcome,
  setFeedbackRootCause,
}: {
  canCreateWorkOrders: boolean
  canFeedback: boolean
  createWorkOrderFromContext: (source?: Recommendation) => void
  diagnosisLoading: boolean
  diagnosisMessage: string
  diagnosisProvider: string
  diagnosisStreamText: string
  diagnosisStreaming: boolean
  diagnosisUsedLive: boolean
  downloadReport: () => void
  feedbackActionTaken: string
  feedbackNotes: string
  feedbackOutcome: string
  feedbackRootCause: string
  morpheusProgressRef: RefObject<HTMLDivElement | null>
  recommendation: Recommendation | null
  sendFeedback: (status: 'accepted' | 'rejected' | 'corrected') => void
  setFeedbackActionTaken: (value: string) => void
  setFeedbackNotes: (value: string) => void
  setFeedbackOutcome: (value: string) => void
  setFeedbackRootCause: (value: string) => void
}) {
  return (
    <div className="recommendationSection morpheusPanel">
      <div className="assistantHeaderCompact">
        <span className="assistantAvatar">M</span>
        <div>
          <h2>{diagnosisAssistantName}</h2>
          <small>Diagnosis assistant</small>
        </div>
      </div>
      {(diagnosisProvider || diagnosisLoading) && (
        <small className="providerLine">
          {diagnosisLoading && <span className="loadingSpinner" aria-hidden="true" />}
          {diagnosisProvider
            ? `${diagnosisUsedLive ? 'Live LLM' : 'LLM fallback'} · ${diagnosisProvider}`
            : 'Starting diagnosis stream'}
        </small>
      )}
      {diagnosisStreamText && (
        <div className="morpheusProgress" ref={morpheusProgressRef} aria-live="polite">
          <FormattedAssistantContent content={diagnosisStreamText} />
        </div>
      )}
      {diagnosisMessage && <p className="inlineStatus errorText">{diagnosisMessage}</p>}
      {recommendation ? (
        <>
          <div className="sectionHeader recommendationTitle">
            <CheckCircle2 size={18} />
            <h3>Recommendation</h3>
          </div>
          <p className="diagnosis">{recommendation.diagnosis}</p>
          <div className="recommendationBadges">
            <span className={`riskBadge ${recommendation.risk_level}`}>{recommendation.risk_level}</span>
            <span className="rolePill">
              {recommendation.used_live_provider ? 'Live LLM' : 'LLM fallback'} · {recommendation.provider}
            </span>
          </div>
          <div className="recommendationFacts">
            <span>
              <small>Urgency</small>
              <strong>{recommendation.urgency}</strong>
            </span>
            <span>
              <small>RUL</small>
              <strong>{recommendation.remaining_useful_life_days ?? 'n/a'} days</strong>
            </span>
            <span>
              <small>Confidence</small>
              <strong>{Math.round(recommendation.confidence * 100)}%</strong>
            </span>
          </div>
          <h3>Immediate Actions</h3>
          <ul>{recommendation.immediate_actions.map((action) => <li key={action}>{action}</li>)}</ul>
          <h3>Planned Actions</h3>
          <ul>{recommendation.planned_actions.map((action) => <li key={action}>{action}</li>)}</ul>
          <h3>Evidence</h3>
          {recommendation.evidence.slice(0, 3).map((evidence) => (
            <p className="evidence" key={evidence.source_id}>
              <strong>{evidence.title}</strong>
              {evidence.excerpt}
              {evidence.relevance_reason && <small>{evidence.relevance_reason}</small>}
            </p>
          ))}
          {canFeedback && (
            <>
              <div className="feedbackDetails">
                <label className="field">
                  <span>Actual Root Cause</span>
                  <input value={feedbackRootCause} onChange={(event) => setFeedbackRootCause(event.target.value)} />
                </label>
                <label className="field">
                  <span>Action Taken</span>
                  <input value={feedbackActionTaken} onChange={(event) => setFeedbackActionTaken(event.target.value)} />
                </label>
                <label className="field">
                  <span>Outcome</span>
                  <input value={feedbackOutcome} onChange={(event) => setFeedbackOutcome(event.target.value)} />
                </label>
                <label className="field">
                  <span>Notes</span>
                  <input value={feedbackNotes} onChange={(event) => setFeedbackNotes(event.target.value)} />
                </label>
              </div>
              <div className="feedbackRow">
                <button onClick={() => sendFeedback('accepted')}>Accept</button>
                <button onClick={() => sendFeedback('corrected')}>Correct</button>
                <button onClick={() => sendFeedback('rejected')}>Reject</button>
              </div>
            </>
          )}
          <div className="buttonRow">
            <button className="downloadReport" onClick={downloadReport}>
              <Download size={16} />
              Export Report
            </button>
            {canCreateWorkOrders && (
              <button className="textButton" onClick={() => createWorkOrderFromContext(recommendation)}>
                <Briefcase size={16} />
                Create Work Order
              </button>
            )}
          </div>
        </>
      ) : (
        <p className="emptyState">
          {diagnosisLoading || diagnosisStreaming
            ? `${diagnosisAssistantName} is preparing the diagnosis...`
            : `Run ${diagnosisAssistantName} to generate cited maintenance actions.`}
        </p>
      )}
    </div>
  )
}
