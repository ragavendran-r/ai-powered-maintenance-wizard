import {
  CheckCircle2,
  Database,
  Download,
  FileJson,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from 'react'
import { api } from '../services/api'
import type {
  LearningArtifactCleanupResult,
  LearningDatasetSnapshot,
  LearningEmbeddingProfile,
  LearningEvaluationRun,
  LearningExample,
  LearningArtifact,
  LearningJob,
  LearningModelDeployment,
  LearningModelPromotion,
  LearningModelVersion,
  LearningRagMigrationPlan,
  LearningSummary,
  PaginatedResponse,
} from '../services/api'
import {
  clipText,
  deploymentDisplayDate,
  deploymentStatusClass,
  formatDate,
  isVerifiedDeployment,
  mergeLearningDeployments,
  metricValue,
} from '../appModel'

type LearningLoadingState = Partial<Record<
  | 'activateEmbeddingProfile'
  | 'createSnapshot'
  | 'deployAdapter'
  | 'previewArtifactCleanup'
  | 'previewRagMigration'
  | 'promoteAdapter'
  | 'queuePeftTuning'
  | 'refreshExamples'
  | 'registerAdapter'
  | 'reindexRag'
  | 'rollbackAdapter'
  | 'runEvaluation'
  | 'runRagMigration',
  boolean
>>

type LearningReviewTab = 'examples' | 'adapter' | 'vector'
type LifecycleTableKey = 'examples' | 'evaluations' | 'jobs' | 'artifacts' | 'deployments' | 'promotions'

const LIFECYCLE_TABLE_PAGE_SIZE = 10

type TablePageState<T> = PaginatedResponse<T> & {
  error?: string
  loading?: boolean
}

export function LearningReviewRoute({
  activateSelectedEmbeddingProfile,
  adapterBaseModel,
  adapterModelName,
  adapterNotes,
  adapterPath,
  adapterProvider,
  artifactCleanupResult,
  createLearningSnapshot,
  deployLearningAdapter,
  deploymentBaseUrl,
  deploymentRuntimeProvider,
  downloadLearningSnapshot,
  judgeLearningExample,
  learningDatasetDescription,
  learningDatasetName,
  learningDatasets,
  learningDeployments,
  learningEmbeddingProfiles,
  learningExamples,
  learningJudgingExampleId,
  learningLoading,
  learningSummary,
  peftAdapterName,
  previewLearningArtifactCleanup,
  previewLearningRagMigration,
  promoteLearningAdapter,
  queuePeftTuningJob,
  ragMigrationPreview,
  ragTargetCollection,
  refreshLearningExamples,
  refreshLearningStatus,
  registerLearningAdapter,
  reindexLearningRag,
  rollbackLearningAdapter,
  runLearningEvaluation,
  runLearningRagMigration,
  selectedEmbeddingProfileId,
  selectedLearningDatasetId,
  selectedLearningModelId,
  selectedLearningPromptId,
  setAdapterBaseModel,
  setAdapterModelName,
  setAdapterNotes,
  setAdapterPath,
  setAdapterProvider,
  setDeploymentBaseUrl,
  setDeploymentRuntimeProvider,
  setLearningDatasetDescription,
  setLearningDatasetName,
  setPeftAdapterName,
  setRagTargetCollection,
  setSelectedEmbeddingProfileId,
  setSelectedLearningDatasetId,
  setSelectedLearningModelId,
  setSelectedLearningPromptId,
  toggleLearningApproval,
}: {
  activateSelectedEmbeddingProfile: () => void
  adapterBaseModel: string
  adapterModelName: string
  adapterNotes: string
  adapterPath: string
  adapterProvider: string
  artifactCleanupResult: LearningArtifactCleanupResult | null
  createLearningSnapshot: () => void
  deployLearningAdapter: (model: LearningModelVersion) => void
  deploymentBaseUrl: string
  deploymentRuntimeProvider: string
  downloadLearningSnapshot: (snapshot: LearningDatasetSnapshot) => void
  judgeLearningExample: (example: LearningExample) => void
  learningDatasetDescription: string
  learningDatasetName: string
  learningDatasets: LearningDatasetSnapshot[]
  learningDeployments: LearningModelDeployment[]
  learningEmbeddingProfiles: LearningEmbeddingProfile[]
  learningExamples: LearningExample[]
  learningJudgingExampleId: string | null
  learningLoading: LearningLoadingState
  learningSummary: LearningSummary | null
  peftAdapterName: string
  previewLearningArtifactCleanup: () => void
  previewLearningRagMigration: () => void
  promoteLearningAdapter: (model: LearningModelVersion) => void
  queuePeftTuningJob: () => void
  ragMigrationPreview: LearningRagMigrationPlan | null
  ragTargetCollection: string
  refreshLearningExamples: () => void
  refreshLearningStatus: () => void
  registerLearningAdapter: () => void
  reindexLearningRag: () => void
  rollbackLearningAdapter: (model: LearningModelVersion) => void
  runLearningEvaluation: () => void
  runLearningRagMigration: () => void
  selectedEmbeddingProfileId: string
  selectedLearningDatasetId: string
  selectedLearningModelId: string
  selectedLearningPromptId: string
  setAdapterBaseModel: (value: string) => void
  setAdapterModelName: (value: string) => void
  setAdapterNotes: (value: string) => void
  setAdapterPath: (value: string) => void
  setAdapterProvider: (value: string) => void
  setDeploymentBaseUrl: (value: string) => void
  setDeploymentRuntimeProvider: (value: string) => void
  setLearningDatasetDescription: (value: string) => void
  setLearningDatasetName: (value: string) => void
  setPeftAdapterName: (value: string) => void
  setRagTargetCollection: (value: string) => void
  setSelectedEmbeddingProfileId: (value: string) => void
  setSelectedLearningDatasetId: (value: string) => void
  setSelectedLearningModelId: (value: string) => void
  setSelectedLearningPromptId: (value: string) => void
  toggleLearningApproval: (example: LearningExample) => void
}) {
  const [learningReviewTab, setLearningReviewTab] = useState<LearningReviewTab>('examples')
  const [selectedLearningExample, setSelectedLearningExample] = useState<LearningExample | null>(null)
  const learningModels: LearningModelVersion[] = learningSummary?.model_versions ?? []
  const adapterModelVersions = learningModels.filter((model) => Boolean(model.adapter_path) || model.status !== 'active')
  const learningPrompts = learningSummary?.prompt_versions ?? []
  const learningEvaluations: LearningEvaluationRun[] = learningSummary?.evaluation_runs ?? []
  const learningJobs: LearningJob[] = learningSummary?.recent_jobs ?? []
  const learningArtifacts: LearningArtifact[] = learningSummary?.recent_artifacts ?? []
  const learningPromotions: LearningModelPromotion[] = learningSummary?.recent_promotions ?? []
  const learningDeploymentRecords = useMemo(
    () => mergeLearningDeployments(learningDeployments, learningSummary?.recent_deployments ?? []),
    [learningDeployments, learningSummary?.recent_deployments],
  )
  const [exampleTablePage, setExampleTablePage] = useState<TablePageState<LearningExample>>({
    items: learningExamples,
    limit: LIFECYCLE_TABLE_PAGE_SIZE,
    offset: 0,
    total: learningSummary?.counts.examples ?? learningExamples.length,
  })
  const [evaluationTablePage, setEvaluationTablePage] = useState<TablePageState<LearningEvaluationRun>>({
    items: learningEvaluations,
    limit: LIFECYCLE_TABLE_PAGE_SIZE,
    offset: 0,
    total: learningSummary?.counts.evaluation_runs ?? learningEvaluations.length,
  })
  const [jobTablePage, setJobTablePage] = useState<TablePageState<LearningJob>>({
    items: learningJobs,
    limit: LIFECYCLE_TABLE_PAGE_SIZE,
    offset: 0,
    total: learningSummary?.counts.jobs ?? learningJobs.length,
  })
  const [artifactTablePage, setArtifactTablePage] = useState<TablePageState<LearningArtifact>>({
    items: learningArtifacts,
    limit: LIFECYCLE_TABLE_PAGE_SIZE,
    offset: 0,
    total: learningSummary?.counts.artifacts ?? learningArtifacts.length,
  })
  const [promotionTablePage, setPromotionTablePage] = useState<TablePageState<LearningModelPromotion>>({
    items: learningPromotions,
    limit: LIFECYCLE_TABLE_PAGE_SIZE,
    offset: 0,
    total: learningSummary?.counts.promotions ?? learningPromotions.length,
  })
  const [deploymentTablePage, setDeploymentTablePage] = useState<TablePageState<LearningModelDeployment>>({
    items: learningDeploymentRecords,
    limit: LIFECYCLE_TABLE_PAGE_SIZE,
    offset: 0,
    total: learningSummary?.counts.deployments ?? learningDeploymentRecords.length,
  })
  const artifactRetention = learningSummary?.artifact_store?.retention ?? {}
  const artifactRetentionState = String(artifactRetention.state ?? 'not configured')
  const artifactRetentionDays = String(artifactRetention.retention_days ?? 'unknown')
  const latestDeploymentForModel = (modelId: string) =>
    learningDeploymentRecords.find((deployment) => deployment.model_version_id === modelId)
  const latestVerifiedDeploymentForModel = (modelId: string) =>
    learningDeploymentRecords.find((deployment) => deployment.model_version_id === modelId && isVerifiedDeployment(deployment))
  const passedEvaluationForModel = (modelId: string) =>
    learningEvaluations.find((run) => run.model_version_id === modelId && run.passed)
  const selectedEmbeddingProfile = learningEmbeddingProfiles.find((profile) => profile.id === selectedEmbeddingProfileId)
  const activeEmbeddingProfile = learningEmbeddingProfiles.find((profile) => profile.status === 'active')
  const vectorStore = learningSummary?.vector_store
  const vectorProfile = vectorStore?.embedding_profile
  const ragMigrationNeeded = Boolean(vectorStore?.migration_required || (selectedEmbeddingProfile && activeEmbeddingProfile && selectedEmbeddingProfile.id !== activeEmbeddingProfile.id))
  const latestDatasetSnapshot = learningDatasets[0] ?? learningSummary?.recent_snapshots?.[0]
  const selectedTrainingDataset = learningDatasets.find((snapshot) => snapshot.id === selectedLearningDatasetId)
    ?? learningSummary?.recent_snapshots?.find((snapshot) => snapshot.id === selectedLearningDatasetId)
    ?? latestDatasetSnapshot
  const selectedTrainingModel = learningModels.find((model) => model.id === selectedLearningModelId)
    ?? learningModels.find((model) => model.status === 'active')
    ?? learningModels[0]
  const selectedTrainingPrompt = learningPrompts.find((prompt) => prompt.id === selectedLearningPromptId)
    ?? learningPrompts.find((prompt) => prompt.assistant === 'neo')
    ?? learningPrompts[0]
  const peftTrainerConfigured = Boolean(learningSummary?.peft_trainer?.configured)
  const peftRunMode = peftTrainerConfigured ? 'Worker will train adapter' : 'Worker will prepare artifacts only'
  const peftActionLabel = peftTrainerConfigured ? 'Queue PEFT training job' : 'Prepare PEFT dataset artifacts'
  const latestPeftJob = learningJobs.find((job) => job.job_type === 'peft_tuning')
  const activePeftJob = learningJobs.find(
    (job) => job.job_type === 'peft_tuning' && ['queued', 'published', 'running'].includes(job.status),
  )
  const currentPeftJob = activePeftJob ?? latestPeftJob
  const currentPeftStatus = currentPeftJob
    ? String(currentPeftJob.output_refs.training_status ?? currentPeftJob.output_refs.dispatch ?? currentPeftJob.status).replace(/_/g, ' ')
    : 'No PEFT job queued'
  const configuredRuntimeModel = learningSummary?.serving_model?.provider === 'ollama'
    ? learningSummary?.serving_model?.ollama_model
    : learningSummary?.serving_model?.openai_model
  const servedAdapterModel = learningSummary?.serving_model?.served_model_name
  const shouldShowConfiguredRuntimeModel = configuredRuntimeModel && configuredRuntimeModel !== servedAdapterModel

  useEffect(() => {
    setExampleTablePage({
      items: learningExamples,
      limit: LIFECYCLE_TABLE_PAGE_SIZE,
      offset: 0,
      total: learningSummary?.counts.examples ?? learningExamples.length,
    })
  }, [learningExamples, learningSummary?.counts.examples])

  useEffect(() => {
    setEvaluationTablePage({
      items: learningEvaluations,
      limit: LIFECYCLE_TABLE_PAGE_SIZE,
      offset: 0,
      total: learningSummary?.counts.evaluation_runs ?? learningEvaluations.length,
    })
  }, [learningEvaluations, learningSummary?.counts.evaluation_runs])

  useEffect(() => {
    setJobTablePage({
      items: learningJobs,
      limit: LIFECYCLE_TABLE_PAGE_SIZE,
      offset: 0,
      total: learningSummary?.counts.jobs ?? learningJobs.length,
    })
  }, [learningJobs, learningSummary?.counts.jobs])

  useEffect(() => {
    setArtifactTablePage({
      items: learningArtifacts,
      limit: LIFECYCLE_TABLE_PAGE_SIZE,
      offset: 0,
      total: learningSummary?.counts.artifacts ?? learningArtifacts.length,
    })
  }, [learningArtifacts, learningSummary?.counts.artifacts])

  useEffect(() => {
    setPromotionTablePage({
      items: learningPromotions,
      limit: LIFECYCLE_TABLE_PAGE_SIZE,
      offset: 0,
      total: learningSummary?.counts.promotions ?? learningPromotions.length,
    })
  }, [learningPromotions, learningSummary?.counts.promotions])

  useEffect(() => {
    setDeploymentTablePage({
      items: learningDeploymentRecords,
      limit: LIFECYCLE_TABLE_PAGE_SIZE,
      offset: 0,
      total: learningSummary?.counts.deployments ?? learningDeploymentRecords.length,
    })
  }, [learningDeploymentRecords, learningSummary?.counts.deployments])

  useEffect(() => {
    const hasActivePeftJob = learningJobs.some(
      (job) => job.job_type === 'peft_tuning' && ['queued', 'published', 'running'].includes(job.status),
    )
    if (learningReviewTab !== 'adapter' || !hasActivePeftJob) return
    const intervalId = window.setInterval(refreshLearningStatus, 4000)
    return () => window.clearInterval(intervalId)
  }, [learningJobs, learningReviewTab, refreshLearningStatus])

  const setTableLoading = (key: LifecycleTableKey, loading: boolean) => {
    const applyLoading = <T,>(setPage: Dispatch<SetStateAction<TablePageState<T>>>) =>
      setPage((page) => ({ ...page, error: undefined, loading }))
    if (key === 'examples') applyLoading(setExampleTablePage)
    if (key === 'evaluations') applyLoading(setEvaluationTablePage)
    if (key === 'jobs') applyLoading(setJobTablePage)
    if (key === 'artifacts') applyLoading(setArtifactTablePage)
    if (key === 'deployments') applyLoading(setDeploymentTablePage)
    if (key === 'promotions') applyLoading(setPromotionTablePage)
  }

  const setTableError = (key: LifecycleTableKey, message: string) => {
    const applyError = <T,>(setPage: Dispatch<SetStateAction<TablePageState<T>>>) =>
      setPage((page) => ({ ...page, error: message, loading: false }))
    if (key === 'examples') applyError(setExampleTablePage)
    if (key === 'evaluations') applyError(setEvaluationTablePage)
    if (key === 'jobs') applyError(setJobTablePage)
    if (key === 'artifacts') applyError(setArtifactTablePage)
    if (key === 'deployments') applyError(setDeploymentTablePage)
    if (key === 'promotions') applyError(setPromotionTablePage)
  }

  const loadTablePage = async (key: LifecycleTableKey, offset: number) => {
    setTableLoading(key, true)
    try {
      if (key === 'examples') setExampleTablePage({ ...(await api.learningExamplesPage({ limit: LIFECYCLE_TABLE_PAGE_SIZE, offset })), loading: false })
      if (key === 'evaluations') setEvaluationTablePage({ ...(await api.learningEvaluationsPage({ limit: LIFECYCLE_TABLE_PAGE_SIZE, offset })), loading: false })
      if (key === 'jobs') setJobTablePage({ ...(await api.learningJobsPage({ limit: LIFECYCLE_TABLE_PAGE_SIZE, offset })), loading: false })
      if (key === 'artifacts') setArtifactTablePage({ ...(await api.learningArtifactsPage({ limit: LIFECYCLE_TABLE_PAGE_SIZE, offset })), loading: false })
      if (key === 'deployments') setDeploymentTablePage({ ...(await api.learningModelDeploymentsPage({ limit: LIFECYCLE_TABLE_PAGE_SIZE, offset })), loading: false })
      if (key === 'promotions') setPromotionTablePage({ ...(await api.learningModelPromotionsPage({ limit: LIFECYCLE_TABLE_PAGE_SIZE, offset })), loading: false })
    } catch {
      setTableError(key, 'Page could not be loaded from the backend.')
    }
  }

  const renderLifecyclePagination = (key: LifecycleTableKey, page: TablePageState<unknown>) => {
    if (page.total <= page.limit) {
      return null
    }
    const pageIndex = Math.floor(page.offset / page.limit)
    const pageCount = Math.ceil(page.total / page.limit)
    return (
      <div className="tablePagination" aria-label={`${key} table pagination`}>
        <span>
          Rows {page.offset + 1}-{Math.min(page.total, page.offset + page.items.length)} of {page.total}
        </span>
        <div>
          <button
            className="outlineButton"
            disabled={page.loading || pageIndex === 0}
            onClick={() => void loadTablePage(key, Math.max(0, page.offset - page.limit))}
            type="button"
          >
            Previous
          </button>
          <button
            className="outlineButton"
            disabled={page.loading || pageIndex >= pageCount - 1}
            onClick={() => void loadTablePage(key, page.offset + page.limit)}
            type="button"
          >
            Next
          </button>
        </div>
      </div>
    )
  }

  return (
    <section className="detailPanel learningView">
      <div className="sectionHeader">
        <Sparkles size={18} />
        <h2>Learning and Tuning</h2>
      </div>
      <p className="emptyState">
        Review approved human feedback, maintenance labels, work-order outcomes, ingested documents, and assistant interactions before exporting a local tuning dataset.
      </p>
      <div className="planningTabRow learningReviewTabs" role="tablist" aria-label="Learning and tuning review tabs">
        {([
          ['examples', 'Examples & judgments'],
          ['adapter', 'Adapter lifecycle'],
          ['vector', 'Qdrant migration'],
        ] as const).map(([tab, label]) => (
          <button
            aria-controls={`learning-review-tab-${tab}`}
            aria-selected={learningReviewTab === tab}
            className={learningReviewTab === tab ? 'selected' : ''}
            id={`learning-review-tab-trigger-${tab}`}
            key={tab}
            onClick={() => setLearningReviewTab(tab)}
            role="tab"
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      <div
        aria-labelledby="learning-review-tab-trigger-examples"
        hidden={learningReviewTab !== 'examples'}
        id="learning-review-tab-examples"
        role="tabpanel"
      >
        <div className="learningSnapshotRow">
          <section className="learningPanel learningSnapshotPanel">
            <h3>Create Snapshot</h3>
            <div className="learningToolbar">
              <button className="textButton" onClick={refreshLearningExamples} disabled={learningLoading.refreshExamples}>
                {learningLoading.refreshExamples ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
                Refresh examples
              </button>
              <label className="field">
                <span>Snapshot name</span>
                <input value={learningDatasetName} onChange={(event) => setLearningDatasetName(event.target.value)} />
              </label>
              <label className="field">
                <span>Description</span>
                <input value={learningDatasetDescription} onChange={(event) => setLearningDatasetDescription(event.target.value)} />
              </label>
              <button className="textButton" onClick={createLearningSnapshot} disabled={learningLoading.createSnapshot}>
                {learningLoading.createSnapshot ? <span className="loadingSpinner" aria-hidden="true" /> : <FileJson size={16} />}
                Create JSONL snapshot
              </button>
            </div>
          </section>
          <section className="learningPanel learningSnapshotPanel">
            <h3>Dataset Snapshots</h3>
            <div className="datasetList">
              {learningDatasets.length ? learningDatasets.map((snapshot) => (
                <div className="datasetRow" key={snapshot.id}>
                  <span>
                    <strong>
                      {snapshot.name}
                      {snapshot.id === latestDatasetSnapshot?.id && <small className="inlineStatusBadge">Latest</small>}
                    </strong>
                    <small>{snapshot.example_count} examples · {formatDate(snapshot.created_at)}</small>
                  </span>
                  <button className="iconTextButton" onClick={() => downloadLearningSnapshot(snapshot)}>
                    <Download size={16} />
                    Download JSONL
                  </button>
                </div>
              )) : (
                <p className="emptyState">Create a snapshot after approving examples.</p>
              )}
            </div>
          </section>
        </div>
        <div className="learningStats">
          {(['interactions', 'examples', 'approved_examples', 'snapshots', 'artifacts', 'promotions', 'deployments'] as const).map((key) => (
            <span className="learningStat" key={key}>
              <small>{key.replace(/_/g, ' ')}</small>
              <strong>{learningSummary?.counts[key] ?? 0}</strong>
            </span>
          ))}
        </div>
        <div className="learningGrid learningGridFull">
          <section className="learningPanel">
            <h3>Approved Controls</h3>
            <div className="learningExamplesTableWrap">
              {exampleTablePage.items.length ? (
                <table className="learningExamplesTable" aria-label="Approved Controls">
                  <thead>
                    <tr>
                      <th>Source</th>
                      <th>Score</th>
                      <th>Judge</th>
                      <th>Status</th>
                      <th>Summary</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exampleTablePage.items.map((example) => (
                      <tr key={example.id}>
                        <td>
                          <strong>{example.source_type.replace(/_/g, ' ')}</strong>
                          <small>{example.equipment_id ?? 'company-wide'} · {formatDate(example.created_at)}</small>
                        </td>
                        <td>
                          <span className={`judgeBadge ${example.judge_label}`}>
                            {Math.round(example.judge_score * 100)}% · {example.judge_label.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td>
                          <strong>{example.judge_used_live_provider ? 'Live LLM' : 'Fallback'}</strong>
                          <small>{example.judge_provider}</small>
                        </td>
                        <td>
                          <span className={`approvalBadge ${example.approved ? 'approved' : 'review'}`}>
                            {example.approved ? 'Approved' : 'Review'}
                          </span>
                        </td>
                        <td className="learningExampleSummaryCell">{clipText(example.expected_output, 110)}</td>
                        <td>
                          <div className="tableActionGroup">
                            <button className="outlineButton" onClick={() => setSelectedLearningExample(example)}>
                              View details
                            </button>
                            <button className="outlineButton" onClick={() => judgeLearningExample(example)} disabled={learningJudgingExampleId === example.id}>
                              {learningJudgingExampleId === example.id ? <span className="loadingSpinner" aria-hidden="true" /> : null}
                              {learningJudgingExampleId === example.id ? 'Judging...' : 'Judge'}
                            </button>
                            <button className={example.approved ? 'outlineButton' : 'textButton'} onClick={() => toggleLearningApproval(example)}>
                              {example.approved ? 'Remove approval' : 'Approve'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="emptyState">No learning examples have been generated yet.</p>
              )}
              {exampleTablePage.error && <p className="emptyState">{exampleTablePage.error}</p>}
              {renderLifecyclePagination('examples', exampleTablePage)}
            </div>
          </section>
        </div>
      </div>
      <div
        aria-labelledby="learning-review-tab-trigger-vector"
        hidden={learningReviewTab !== 'vector'}
        id="learning-review-tab-vector"
        role="tabpanel"
      >
      <p className="emptyState">
        Qdrant migration is only required when the embedding profile, vector dimensions, distance, or target collection changes. Adapter deployment and PEFT promotion do not by themselves require a vector migration.
      </p>
      <div className="vectorStoreStatus">
        <div className="vectorStoreFacts">
          <span>
            <strong>RAG vector DB</strong>
            <small>
              {vectorStore?.store ?? 'unknown'} · {vectorStore?.state ?? 'not checked'}
            </small>
          </span>
          <span>
            <small>Collection</small>
            <strong>{vectorStore?.collection ?? 'local fallback'}</strong>
          </span>
          <span>
            <small>Points</small>
            <strong>{String(vectorStore?.points_count ?? 'not checked')}</strong>
          </span>
          <span>
            <small>Vector shape</small>
            <strong>
              {String(vectorStore?.collection_vector_size ?? 'unknown')} · {String(vectorStore?.collection_distance ?? vectorProfile?.distance ?? 'unknown')}
            </strong>
          </span>
          <span>
            <small>Active embedding</small>
            <strong>
              {String(vectorProfile?.provider ?? 'unknown')} · {String(vectorProfile?.model ?? 'unknown')} · v
              {String(vectorProfile?.version ?? 'unknown')}
            </strong>
          </span>
          <span>
            <small>Profile dimensions</small>
            <strong>{String(vectorProfile?.dimensions ?? 'unknown')}</strong>
          </span>
          <span>
            <small>Migration</small>
            <strong>{ragMigrationNeeded ? 'Required' : 'Current'}</strong>
          </span>
        </div>
        {(vectorProfile?.warning || vectorStore?.error || (vectorStore?.migration_reasons ?? []).length > 0) && (
          <div className="migrationNotice">
            {vectorProfile?.warning && <p>{String(vectorProfile.warning)}</p>}
            {vectorStore?.error && <p>{String(vectorStore.error)}</p>}
            {(vectorStore?.migration_reasons ?? []).map((reason) => (
              <p key={reason}>{reason}</p>
            ))}
          </div>
        )}
        <div className="ragControls">
          <label className="field">
            <span>Embedding profile</span>
            <select value={selectedEmbeddingProfileId} onChange={(event) => setSelectedEmbeddingProfileId(event.target.value)}>
              {learningEmbeddingProfiles.map((profile) => (
                <option value={profile.id} key={profile.id}>
                  {profile.provider} · {profile.model} · v{profile.version} · {profile.dimensions}d {profile.status === 'active' ? '(active)' : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Target collection</span>
            <input value={ragTargetCollection} onChange={(event) => setRagTargetCollection(event.target.value)} />
          </label>
          <button className="outlineButton" onClick={activateSelectedEmbeddingProfile} disabled={learningLoading.activateEmbeddingProfile || !selectedEmbeddingProfileId || selectedEmbeddingProfileId === activeEmbeddingProfile?.id}>
            {learningLoading.activateEmbeddingProfile ? <span className="loadingSpinner" aria-hidden="true" /> : null}
            Activate profile
          </button>
          <button className="outlineButton" onClick={previewLearningRagMigration} disabled={learningLoading.previewRagMigration || !selectedEmbeddingProfileId}>
            {learningLoading.previewRagMigration ? <span className="loadingSpinner" aria-hidden="true" /> : null}
            Preview migration
          </button>
          <button className="textButton" onClick={runLearningRagMigration} disabled={learningLoading.runRagMigration || !selectedEmbeddingProfileId}>
            {learningLoading.runRagMigration ? <span className="loadingSpinner" aria-hidden="true" /> : <Database size={16} />}
            Run Qdrant migration
          </button>
          <button className="subtleButton" onClick={reindexLearningRag} disabled={learningLoading.reindexRag || ragMigrationNeeded}>
            {learningLoading.reindexRag ? <span className="loadingSpinner" aria-hidden="true" /> : null}
            Reindex current profile
          </button>
        </div>
        {ragMigrationPreview && (
          <div className="migrationPreview">
            <span>
              <strong>Migration preview</strong>
              <small>
                {String(ragMigrationPreview.active_profile.model ?? 'active')} → {String(ragMigrationPreview.target_profile.model ?? 'target')}
              </small>
            </span>
            <span>
              <small>Target collection</small>
              <strong>{ragMigrationPreview.target_collection}</strong>
            </span>
            <span>
              <small>Profile activation</small>
              <strong>{ragMigrationPreview.will_activate_profile ? 'Yes' : 'No'}</strong>
            </span>
            <div>
              {ragMigrationPreview.reasons.map((reason) => (
                <p key={reason}>{reason}</p>
              ))}
            </div>
          </div>
        )}
      </div>
      </div>
      <div
        aria-labelledby="learning-review-tab-trigger-adapter"
        hidden={learningReviewTab !== 'adapter'}
        id="learning-review-tab-adapter"
        role="tabpanel"
      >
      <div className="servingModelStatus">
        <span>
          <strong>Serving LLM</strong>
          <small>
            {learningSummary?.serving_model?.source?.replace(/_/g, ' ') ?? 'unknown'} · {learningSummary?.serving_model?.provider ?? 'unknown'}
          </small>
        </span>
        {shouldShowConfiguredRuntimeModel && (
          <span>
            <small>Configured runtime model</small>
            <strong>{configuredRuntimeModel}</strong>
          </span>
        )}
        {learningSummary?.serving_model?.active_model_version_id && (
          <span>
            <small>Active adapter version</small>
            <strong>{learningSummary.serving_model.active_model_version_id}</strong>
          </span>
        )}
        {learningSummary?.serving_model?.adapter_path && (
          <span>
            <small>Adapter</small>
            <strong>{learningSummary.serving_model.adapter_path}</strong>
          </span>
        )}
        {learningSummary?.serving_model?.deployment_id && (
          <span>
            <small>Runtime deployment</small>
            <strong>
              {learningSummary.serving_model.deployment_id} · {learningSummary.serving_model.health_status ?? 'not checked'}
            </strong>
          </span>
        )}
        {learningSummary?.serving_model?.served_model_name && (
          <span>
            <small>Served adapter alias</small>
            <strong>{learningSummary.serving_model.served_model_name}</strong>
          </span>
        )}
        {learningSummary?.serving_model?.warning && (
          <span>
            <small>Status</small>
            <strong>{learningSummary.serving_model.warning}</strong>
          </span>
        )}
      </div>
      <div className="artifactStoreStatus">
        <span>
          <strong>Artifact store</strong>
          <small>
            {String(learningSummary?.artifact_store?.store ?? 'unknown')} · {String(learningSummary?.artifact_store?.state ?? 'not checked')}
          </small>
        </span>
        <span>
          <small>Location</small>
          <strong>
            {String(
              learningSummary?.artifact_store?.store === 's3'
                ? learningSummary?.artifact_store?.bucket ?? 'bucket not configured'
                : learningSummary?.artifact_store?.local_dir ?? 'local dir not configured',
            )}
          </strong>
        </span>
        {Boolean(learningSummary?.artifact_store?.prefix) && (
          <span>
            <small>Prefix</small>
            <strong>{String(learningSummary?.artifact_store?.prefix)}</strong>
          </span>
        )}
        <span>
          <small>Retention</small>
          <strong>{artifactRetentionState} · {artifactRetentionDays} days</strong>
        </span>
        <button className="outlineButton" onClick={previewLearningArtifactCleanup} disabled={learningLoading.previewArtifactCleanup}>
          {learningLoading.previewArtifactCleanup ? <span className="loadingSpinner" aria-hidden="true" /> : <Trash2 size={16} />}
          Preview cleanup
        </button>
      </div>
      {artifactCleanupResult && (
        <div className={`artifactCleanupResult ${artifactCleanupResult.errors.length ? 'warning' : ''}`}>
          <span>
            <strong>Artifact lifecycle preview</strong>
            <small>
              {artifactCleanupResult.store} · {artifactCleanupResult.dry_run ? 'dry run' : 'apply'} ·
              {artifactCleanupResult.cleanup_enabled ? ' cleanup enabled' : ' cleanup disabled'}
            </small>
          </span>
          <div className="artifactCleanupStats">
            <span>
              <small>Eligible</small>
              <strong>{artifactCleanupResult.expired_count}</strong>
            </span>
            <span>
              <small>Protected</small>
              <strong>{artifactCleanupResult.protected_count}</strong>
            </span>
            <span>
              <small>Deleted</small>
              <strong>{artifactCleanupResult.deleted_count}</strong>
            </span>
          </div>
          {artifactCleanupResult.errors.length > 0 && (
            <p>{artifactCleanupResult.errors.join(' ')}</p>
          )}
          {artifactCleanupResult.candidates.length > 0 && (
            <div className="artifactCleanupList">
              <small>Cleanup candidates</small>
              {artifactCleanupResult.candidates.slice(0, 4).map((item) => (
                <span key={String(item.artifact_id ?? item.path ?? JSON.stringify(item))}>
                  <strong>{String(item.artifact_type ?? 'artifact')}</strong>
                  <small>{String(item.path ?? item.uri ?? item.artifact_id ?? 'registered artifact')}</small>
                </span>
              ))}
            </div>
          )}
          {artifactCleanupResult.protected.length > 0 && (
            <div className="artifactCleanupList">
              <small>Protected artifacts</small>
              {artifactCleanupResult.protected.slice(0, 4).map((item) => (
                <span key={String(item.artifact_id ?? item.path ?? JSON.stringify(item))}>
                  <strong>{String(item.artifact_type ?? 'artifact')}</strong>
                  <small>{String(item.protected_reason ?? 'protected by lifecycle policy')}</small>
                </span>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="peftTrainerStatus">
        <span>
          <strong>PEFT trainer</strong>
          <small>
            {String(learningSummary?.peft_trainer?.mode ?? 'unknown')} · {String(learningSummary?.peft_trainer?.configured ? 'configured' : 'not configured')}
          </small>
        </span>
        <span>
          <small>Run mode</small>
          <strong>{peftRunMode}</strong>
        </span>
        {Boolean(learningSummary?.peft_trainer?.model_source) && (
          <span>
            <small>Trainable model source</small>
            <strong>{String(learningSummary?.peft_trainer?.model_source)}</strong>
          </span>
        )}
        {Boolean(learningSummary?.peft_trainer?.quantization) && (
          <span>
            <small>Quantization</small>
            <strong>{String(learningSummary?.peft_trainer?.quantization)}</strong>
          </span>
        )}
        <span>
          <small>Timeout</small>
          <strong>{String(learningSummary?.peft_trainer?.timeout_seconds ?? 'not checked')}s</strong>
        </span>
        <span>
          <small>Output</small>
          <strong>{String(learningSummary?.peft_trainer?.output_dir ?? 'not configured')}</strong>
        </span>
      </div>
      <div className="learningGrid learningGridFull">
        <section className="learningPanel">
          <h3>Dataset Validation</h3>
          <button className="textButton fullWidthAction" onClick={runLearningEvaluation} disabled={learningLoading.runEvaluation}>
            {learningLoading.runEvaluation ? <span className="loadingSpinner" aria-hidden="true" /> : <CheckCircle2 size={16} />}
            Run dataset validation
          </button>
          <div className="evaluationList">
            {evaluationTablePage.items.length ? (
              <>
                <table className="lifecycleTable lifecycleEvaluationTable" aria-label="Dataset validation runs">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Run date</th>
                      <th>Quality</th>
                      <th>Judge avg</th>
                      <th>Coverage</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {evaluationTablePage.items.map((run) => (
                      <tr className={run.passed ? 'passed' : 'review'} key={run.id}>
                        <td><strong>{run.passed ? 'Passed' : 'Needs review'}</strong></td>
                        <td>{formatDate(run.created_at)}</td>
                        <td>{metricValue(run.metrics.quality_score)}</td>
                        <td>{metricValue(run.metrics.average_judge_score)}</td>
                        <td>
                          <small>Sources {metricValue(run.metrics.source_type_coverage)}</small>
                          <small>Assets {metricValue(run.metrics.asset_coverage)}</small>
                        </td>
                        <td>{run.notes || 'No notes recorded'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {renderLifecyclePagination('evaluations', evaluationTablePage)}
              </>
            ) : (
              <p className="emptyState">Run validation after creating a dataset snapshot.</p>
            )}
            {evaluationTablePage.error && <p className="emptyState">{evaluationTablePage.error}</p>}
          </div>
          <h3>PEFT Tuning Job</h3>
          <div className="learningAdapterGrid">
            <label className="field">
              <span>Dataset snapshot</span>
              <select value={selectedTrainingDataset?.id ?? ''} onChange={(event) => setSelectedLearningDatasetId(event.target.value)}>
                {learningDatasets.map((snapshot) => (
                  <option key={snapshot.id} value={snapshot.id}>
                    {snapshot.name} · {snapshot.example_count} examples
                  </option>
                ))}
                {!learningDatasets.length && selectedTrainingDataset && (
                  <option value={selectedTrainingDataset.id}>{selectedTrainingDataset.name}</option>
                )}
              </select>
            </label>
            <label className="field">
              <span>Source model version</span>
              <select value={selectedTrainingModel?.id ?? ''} onChange={(event) => setSelectedLearningModelId(event.target.value)}>
                {learningModels.map((model) => (
                  <option key={model.id} value={model.id}>
                    {model.model_name} · {model.status}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Prompt version</span>
              <select value={selectedTrainingPrompt?.id ?? ''} onChange={(event) => setSelectedLearningPromptId(event.target.value)}>
                {learningPrompts.map((prompt) => (
                  <option key={prompt.id} value={prompt.id}>
                    {prompt.assistant} · {prompt.version}
                  </option>
                ))}
              </select>
            </label>
            <div className="peftTrainingSummary">
              <span>
                <small>Selected dataset</small>
                <strong>{selectedTrainingDataset ? `${selectedTrainingDataset.name} · ${selectedTrainingDataset.example_count} examples` : 'Create a dataset snapshot first'}</strong>
              </span>
              <span>
                <small>Selected model</small>
                <strong>{selectedTrainingModel ? `${selectedTrainingModel.model_name} · ${selectedTrainingModel.status}` : 'Register or keep a model version available'}</strong>
              </span>
              <span>
                <small>Selected prompt</small>
                <strong>{selectedTrainingPrompt ? `${selectedTrainingPrompt.assistant} · ${selectedTrainingPrompt.version}` : 'Keep a prompt version available'}</strong>
              </span>
            </div>
            <label className="field adapterNotesField">
              <span>PEFT adapter job name</span>
              <input value={peftAdapterName} onChange={(event) => setPeftAdapterName(event.target.value)} />
            </label>
            <button className="textButton fullWidthAction" onClick={queuePeftTuningJob} disabled={learningLoading.queuePeftTuning}>
              {learningLoading.queuePeftTuning ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
              {peftActionLabel}
            </button>
          </div>
          <div className={`peftCurrentJob ${currentPeftJob?.status ?? 'idle'}`}>
            <span>
              <small>Current PEFT training</small>
              <strong>{currentPeftJob ? `${currentPeftJob.id} · ${currentPeftJob.status}` : 'No active training job'}</strong>
            </span>
            <span>
              <small>Worker status</small>
              <strong>{currentPeftStatus}</strong>
            </span>
            {typeof currentPeftJob?.output_refs.adapter_output_dir === 'string' && (
              <span>
                <small>Adapter output</small>
                <strong>{currentPeftJob.output_refs.adapter_output_dir}</strong>
              </span>
            )}
            {typeof currentPeftJob?.output_refs.trainer_started_at === 'string' && (
              <span>
                <small>Trainer started</small>
                <strong>{formatDate(currentPeftJob.output_refs.trainer_started_at)}</strong>
              </span>
            )}
            {currentPeftJob?.error && (
              <span>
                <small>Failure</small>
                <strong>{currentPeftJob.error}</strong>
              </span>
            )}
          </div>
          <h3>Learning Job Trail</h3>
          <div className="jobList">
            {jobTablePage.items.length ? (
              <>
                <table className="lifecycleTable lifecycleJobTable" aria-label="Learning job trail">
                  <thead>
                    <tr>
                      <th>Job</th>
                      <th>Status</th>
                      <th>Subject</th>
                      <th>Updated</th>
                      <th>Output</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobTablePage.items.map((job) => (
                      <tr className={job.status} key={job.id}>
                        <td><strong>{job.job_type.replace(/_/g, ' ')}</strong></td>
                        <td>{job.status}</td>
                        <td>{job.subject}</td>
                        <td>{formatDate(job.updated_at)}</td>
                        <td>
                          {typeof job.output_refs.training_status === 'string' && (
                            <small>Training {job.output_refs.training_status.replace(/_/g, ' ')}</small>
                          )}
                          {typeof job.output_refs.registered_model_version_id === 'string' && (
                            <small>Registered model {job.output_refs.registered_model_version_id}</small>
                          )}
                          {typeof job.output_refs.adapter_output_dir === 'string' && (
                            <small>Adapter output {job.output_refs.adapter_output_dir}</small>
                          )}
                          {typeof job.output_refs.dispatch === 'string' && <small>{job.output_refs.dispatch}</small>}
                          {job.error && <small>{job.error}</small>}
                          {!job.error && !job.output_refs.training_status && !job.output_refs.registered_model_version_id && !job.output_refs.adapter_output_dir && !job.output_refs.dispatch && (
                            <small>No output recorded</small>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {renderLifecyclePagination('jobs', jobTablePage)}
              </>
            ) : (
              <p className="emptyState">Learning jobs will appear after review, dataset, evaluation, or PEFT queue actions.</p>
            )}
            {jobTablePage.error && <p className="emptyState">{jobTablePage.error}</p>}
          </div>
          <h3>Learning Artifacts</h3>
          <div className="artifactList">
            {artifactTablePage.items.length ? (
              <>
                <table className="lifecycleTable lifecycleArtifactTable" aria-label="Learning artifacts">
                  <thead>
                    <tr>
                      <th>Artifact</th>
                      <th>Job</th>
                      <th>Created</th>
                      <th>URI</th>
                      <th>Hash</th>
                    </tr>
                  </thead>
                  <tbody>
                    {artifactTablePage.items.map((artifact) => (
                      <tr key={artifact.id}>
                        <td><strong>{artifact.artifact_type.replace(/_/g, ' ')}</strong></td>
                        <td>{artifact.job_id}</td>
                        <td>{formatDate(artifact.created_at)}</td>
                        <td>{artifact.uri}</td>
                        <td>sha256 {artifact.content_hash.slice(0, 12)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {renderLifecyclePagination('artifacts', artifactTablePage)}
              </>
            ) : (
              <p className="emptyState">Worker-produced datasets, manifests, and adapter artifacts will appear here.</p>
            )}
            {artifactTablePage.error && <p className="emptyState">{artifactTablePage.error}</p>}
          </div>
          <h3>Adapter Candidate Versions</h3>
          <div className="versionList">
            {adapterModelVersions.map((model) => {
              const promotionEvaluation = passedEvaluationForModel(model.id)
              const latestDeployment = latestDeploymentForModel(model.id)
              const latestVerifiedDeployment = latestVerifiedDeploymentForModel(model.id)
              const promotionRecord = learningPromotions.find((promotion) => promotion.model_version_id === model.id)
              const canPromoteModel = model.status !== 'active' && Boolean(promotionEvaluation && model.adapter_path)
              const canRollbackModel = model.status === 'retired' && Boolean(promotionEvaluation)
              const canDeployModel = model.status === 'candidate' && Boolean(model.adapter_path)
              return (
                <div className="versionRow" key={model.id}>
                  <strong>{model.model_name}</strong>
                  <small>{model.provider} · {model.status}</small>
                  {model.adapter_path && <small>Adapter {model.adapter_path}</small>}
                  {latestDeployment && (
                    <small>
                      Runtime deployment {latestDeployment.runtime_provider} · {latestDeployment.status} · health{' '}
                      {latestDeployment.health_status ?? 'not checked'}
                    </small>
                  )}
                  {latestVerifiedDeployment && (
                    <small>
                      Runtime-loaded alias {latestVerifiedDeployment.served_model_name} · {latestVerifiedDeployment.serving_provider} ·{' '}
                      {formatDate(deploymentDisplayDate(latestVerifiedDeployment))}
                    </small>
                  )}
                  {!latestVerifiedDeployment && model.status === 'candidate' && (
                    <small>Promotion requires a runtime-loaded adapter deployment for this candidate.</small>
                  )}
                  {promotionEvaluation ? (
                    <small>Evaluation gate passed by {promotionEvaluation.id}</small>
                  ) : model.status !== 'active' ? (
                    <small>Evaluation gate requires a passing evaluation for this model.</small>
                  ) : null}
                  {promotionRecord && <small>Promotion recorded as {promotionRecord.id}</small>}
                  {model.notes && <p>{model.notes}</p>}
                  {(canPromoteModel || canRollbackModel || canDeployModel) && (
                    <div className="versionActions">
                      {canDeployModel && (
                        <button className="textButton" onClick={() => deployLearningAdapter(model)} disabled={learningLoading.deployAdapter}>
                          <Upload size={16} />
                          Deploy adapter to runtime
                        </button>
                      )}
                      {canPromoteModel && (
                        <button className="textButton" onClick={() => promoteLearningAdapter(model)} disabled={learningLoading.promoteAdapter}>
                          <CheckCircle2 size={16} />
                          Promote runtime-loaded adapter
                        </button>
                      )}
                      {canRollbackModel && (
                        <button className="outlineButton" onClick={() => rollbackLearningAdapter(model)} disabled={learningLoading.rollbackAdapter}>
                          Roll back to this model
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            {!adapterModelVersions.length && (
              <p className="emptyState">Adapter candidates will appear here after PEFT training registers a model version with an adapter artifact.</p>
            )}
          </div>
          <h3>Adapter Runtime Deployments</h3>
          <div className="learningAdapterGrid">
            <label className="field">
              <span>Runtime provider</span>
              <input value={deploymentRuntimeProvider} onChange={(event) => setDeploymentRuntimeProvider(event.target.value)} />
            </label>
            <label className="field">
              <span>Runtime base URL</span>
              <input value={deploymentBaseUrl} onChange={(event) => setDeploymentBaseUrl(event.target.value)} placeholder="optional runtime endpoint" />
            </label>
          </div>
          <div className="deploymentList">
            {deploymentTablePage.items.length ? (
              <table className="lifecycleTable lifecycleDeploymentTable" aria-label="Adapter runtime deployments">
                <thead>
                  <tr>
                    <th>Served adapter alias</th>
                    <th>Runtime target</th>
                    <th>Status</th>
                    <th>Health</th>
                    <th>Adapter version</th>
                    <th>Adapter artifact</th>
                  </tr>
                </thead>
                <tbody>
                  {deploymentTablePage.items.map((deployment) => (
                    <tr className={`${deploymentStatusClass(deployment.status)} ${deploymentStatusClass(deployment.health_status)}`} key={deployment.id}>
                      <td><strong>{deployment.served_model_name}</strong></td>
                      <td>
                        <small>{deployment.runtime_provider}</small>
                        <small>{deployment.serving_provider}</small>
                        {deployment.base_url && <small>{deployment.base_url}</small>}
                      </td>
                      <td>{deployment.status.replace(/_/g, ' ')}</td>
                      <td>{deployment.health_status?.replace(/_/g, ' ') ?? 'not checked'}</td>
                      <td>
                        <small>{deployment.model_version_id}</small>
                        <small>{formatDate(deploymentDisplayDate(deployment))}</small>
                      </td>
                      <td>
                        {deployment.artifact_uri && <small>{deployment.artifact_uri}</small>}
                        {deployment.error && <small>{deployment.error}</small>}
                        {!deployment.artifact_uri && !deployment.error && <small>No artifact recorded</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="emptyState">Adapter runtime deployments will appear after a candidate deployment is queued.</p>
            )}
            {renderLifecyclePagination('deployments', deploymentTablePage)}
            {deploymentTablePage.error && <p className="emptyState">{deploymentTablePage.error}</p>}
          </div>
          <h3>Promotion Audit</h3>
          <div className="promotionList">
            {promotionTablePage.items.length ? (
              <table className="lifecycleTable lifecyclePromotionTable" aria-label="Promotion audit">
                <thead>
                  <tr>
                    <th>Action</th>
                    <th>Adapter version</th>
                    <th>Evaluation</th>
                    <th>Reviewer</th>
                    <th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {promotionTablePage.items.map((promotion) => (
                    <tr className={promotion.action} key={promotion.id}>
                      <td><strong>{promotion.action === 'promote' ? 'Adapter promoted' : 'Rollback completed'}</strong></td>
                      <td>
                        <small>{promotion.model_version_id}</small>
                        {promotion.previous_active_model_id && <small>Previous {promotion.previous_active_model_id}</small>}
                      </td>
                      <td>
                        <small>{promotion.evaluation_run_id}</small>
                        <small>Dataset {promotion.dataset_id}</small>
                      </td>
                      <td>{promotion.reviewer_email}</td>
                      <td>
                        <small>{formatDate(promotion.created_at)}</small>
                        {promotion.notes && <small>{promotion.notes}</small>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="emptyState">Adapter promotions and rollbacks will appear after a reviewer activates a passed model.</p>
            )}
            {renderLifecyclePagination('promotions', promotionTablePage)}
            {promotionTablePage.error && <p className="emptyState">{promotionTablePage.error}</p>}
          </div>
          <h3>Local Adapter Candidate</h3>
          <div className="learningAdapterGrid">
            <label className="field">
              <span>Provider</span>
              <input value={adapterProvider} onChange={(event) => setAdapterProvider(event.target.value)} />
            </label>
            <label className="field">
              <span>Model</span>
              <input value={adapterModelName} onChange={(event) => setAdapterModelName(event.target.value)} />
            </label>
            <label className="field">
              <span>Base model</span>
              <input value={adapterBaseModel} onChange={(event) => setAdapterBaseModel(event.target.value)} />
            </label>
            <label className="field">
              <span>Adapter path</span>
              <input value={adapterPath} onChange={(event) => setAdapterPath(event.target.value)} placeholder="adapter registry path or artifact URI" />
            </label>
            <label className="field adapterNotesField">
              <span>Notes</span>
              <textarea value={adapterNotes} onChange={(event) => setAdapterNotes(event.target.value)} />
            </label>
            <button className="textButton" onClick={registerLearningAdapter} disabled={learningLoading.registerAdapter || !adapterModelName.trim() || !adapterPath.trim()}>
              {learningLoading.registerAdapter ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
              Register local adapter candidate
            </button>
          </div>
        </section>
      </div>
      </div>
      {selectedLearningExample && (
        <div className="modalOverlay" role="presentation">
          <section
            aria-labelledby="learning-example-detail-title"
            aria-modal="true"
            className="modalPanel learningExampleDialog"
            role="dialog"
          >
            <div>
              <h3 id="learning-example-detail-title">Learning example details</h3>
              <p className="modalContext">
                <strong>{selectedLearningExample.source_type.replace(/_/g, ' ')}</strong>
                <small>
                  {selectedLearningExample.equipment_id ?? 'company-wide'} · {formatDate(selectedLearningExample.created_at)}
                </small>
              </p>
            </div>
            <div className="learningExampleDetailGrid">
              <span>
                <small>Judge score</small>
                <strong>
                  {Math.round(selectedLearningExample.judge_score * 100)}% · {selectedLearningExample.judge_label.replace(/_/g, ' ')}
                </strong>
              </span>
              <span>
                <small>Judge provider</small>
                <strong>
                  {selectedLearningExample.judge_used_live_provider ? 'Live LLM' : 'Fallback'} · {selectedLearningExample.judge_provider}
                </strong>
              </span>
              <span>
                <small>Status</small>
                <strong>{selectedLearningExample.approved ? 'Approved' : 'Review'}</strong>
              </span>
            </div>
            <div className="learningExampleDetailBlock">
              <h4>Instruction</h4>
              <p>{selectedLearningExample.instruction}</p>
            </div>
            <div className="learningExampleDetailBlock">
              <h4>Expected output</h4>
              <blockquote>{selectedLearningExample.expected_output}</blockquote>
            </div>
            {selectedLearningExample.judge_rationale && (
              <div className="learningExampleDetailBlock">
                <h4>Judge rationale</h4>
                <p>{selectedLearningExample.judge_rationale}</p>
              </div>
            )}
            <div className="modalActions">
              <button className="outlineButton" onClick={() => setSelectedLearningExample(null)}>
                Close
              </button>
              <button
                className="outlineButton"
                disabled={learningJudgingExampleId === selectedLearningExample.id}
                onClick={() => judgeLearningExample(selectedLearningExample)}
              >
                {learningJudgingExampleId === selectedLearningExample.id ? <span className="loadingSpinner" aria-hidden="true" /> : null}
                {learningJudgingExampleId === selectedLearningExample.id ? 'Judging...' : 'Judge'}
              </button>
              <button
                className={selectedLearningExample.approved ? 'outlineButton' : 'textButton'}
                onClick={() => {
                  toggleLearningApproval(selectedLearningExample)
                  setSelectedLearningExample({ ...selectedLearningExample, approved: !selectedLearningExample.approved })
                }}
              >
                {selectedLearningExample.approved ? 'Remove approval' : 'Approve'}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  )
}
