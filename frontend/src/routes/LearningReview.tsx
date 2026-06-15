import {
  CheckCircle2,
  Database,
  Download,
  FileJson,
  Sparkles,
  Trash2,
  Upload,
} from 'lucide-react'
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
  learningMessage,
  learningSummary,
  peftAdapterName,
  previewLearningArtifactCleanup,
  previewLearningRagMigration,
  promoteLearningAdapter,
  queuePeftTuningJob,
  ragMigrationPreview,
  ragTargetCollection,
  refreshLearningExamples,
  registerLearningAdapter,
  reindexLearningRag,
  rollbackLearningAdapter,
  runLearningEvaluation,
  runLearningRagMigration,
  selectedEmbeddingProfileId,
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
  learningLoading: boolean
  learningMessage: string
  learningSummary: LearningSummary | null
  peftAdapterName: string
  previewLearningArtifactCleanup: () => void
  previewLearningRagMigration: () => void
  promoteLearningAdapter: (model: LearningModelVersion) => void
  queuePeftTuningJob: () => void
  ragMigrationPreview: LearningRagMigrationPlan | null
  ragTargetCollection: string
  refreshLearningExamples: () => void
  registerLearningAdapter: () => void
  reindexLearningRag: () => void
  rollbackLearningAdapter: (model: LearningModelVersion) => void
  runLearningEvaluation: () => void
  runLearningRagMigration: () => void
  selectedEmbeddingProfileId: string
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
  toggleLearningApproval: (example: LearningExample) => void
}) {
  const learningModels: LearningModelVersion[] = learningSummary?.model_versions ?? []
  const learningPrompts = learningSummary?.prompt_versions ?? []
  const learningEvaluations: LearningEvaluationRun[] = learningSummary?.evaluation_runs ?? []
  const learningJobs: LearningJob[] = learningSummary?.recent_jobs ?? []
  const learningArtifacts: LearningArtifact[] = learningSummary?.recent_artifacts ?? []
  const learningPromotions: LearningModelPromotion[] = learningSummary?.recent_promotions ?? []
  const learningDeploymentRecords = mergeLearningDeployments(learningDeployments, learningSummary?.recent_deployments ?? [])
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

  return (
    <section className="detailPanel learningView">
      <div className="sectionHeader">
        <Sparkles size={18} />
        <h2>Learning and Tuning</h2>
      </div>
      <p className="emptyState">
        Review approved human feedback, maintenance labels, work-order outcomes, ingested documents, and assistant interactions before exporting a local tuning dataset.
      </p>
      <div className="learningToolbar">
        <button className="textButton" onClick={refreshLearningExamples} disabled={learningLoading}>
          {learningLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Sparkles size={16} />}
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
        <button className="textButton" onClick={createLearningSnapshot} disabled={learningLoading}>
          <FileJson size={16} />
          Create JSONL snapshot
        </button>
      </div>
      {learningMessage && <p className="inlineStatus learningToolbarStatus">{learningMessage}</p>}
      {latestDatasetSnapshot && (
        <div className="latestDatasetDownload">
          <span>
            <strong>Latest dataset snapshot</strong>
            <small>{latestDatasetSnapshot.example_count} examples · {formatDate(latestDatasetSnapshot.created_at)}</small>
          </span>
          <button className="iconTextButton" onClick={() => downloadLearningSnapshot(latestDatasetSnapshot)}>
            <Download size={16} />
            Download JSONL
          </button>
        </div>
      )}
      <div className="learningStats">
        {(['interactions', 'examples', 'approved_examples', 'snapshots', 'artifacts', 'promotions', 'deployments'] as const).map((key) => (
          <span className="learningStat" key={key}>
            <small>{key.replace(/_/g, ' ')}</small>
            <strong>{learningSummary?.counts[key] ?? 0}</strong>
          </span>
        ))}
      </div>
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
          <button className="outlineButton" onClick={activateSelectedEmbeddingProfile} disabled={learningLoading || !selectedEmbeddingProfileId || selectedEmbeddingProfileId === activeEmbeddingProfile?.id}>
            Activate profile
          </button>
          <button className="outlineButton" onClick={previewLearningRagMigration} disabled={learningLoading || !selectedEmbeddingProfileId}>
            Preview migration
          </button>
          <button className="textButton" onClick={runLearningRagMigration} disabled={learningLoading || !selectedEmbeddingProfileId}>
            {learningLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Database size={16} />}
            Run Qdrant migration
          </button>
          <button className="subtleButton" onClick={reindexLearningRag} disabled={learningLoading || ragMigrationNeeded}>
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
      <div className="servingModelStatus">
        <span>
          <strong>Serving LLM</strong>
          <small>
            {learningSummary?.serving_model?.source?.replace(/_/g, ' ') ?? 'unknown'} · {learningSummary?.serving_model?.provider ?? 'unknown'}
          </small>
        </span>
        <span>
          <small>Model</small>
          <strong>
            {learningSummary?.serving_model?.provider === 'ollama'
              ? learningSummary?.serving_model?.ollama_model
              : learningSummary?.serving_model?.openai_model}
          </strong>
        </span>
        {learningSummary?.serving_model?.active_model_version_id && (
          <span>
            <small>Active version</small>
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
            <small>Served model</small>
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
        <button className="outlineButton" onClick={previewLearningArtifactCleanup} disabled={learningLoading}>
          {learningLoading ? <span className="loadingSpinner" aria-hidden="true" /> : <Trash2 size={16} />}
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
          <small>Timeout</small>
          <strong>{String(learningSummary?.peft_trainer?.timeout_seconds ?? 'not checked')}s</strong>
        </span>
        <span>
          <small>Output</small>
          <strong>{String(learningSummary?.peft_trainer?.output_dir ?? 'not configured')}</strong>
        </span>
      </div>
      <div className="learningGrid">
        <section className="learningPanel">
          <h3>Approved Controls</h3>
          <div className="learningExamples" aria-label="Learning examples">
            {learningExamples.length ? learningExamples.slice(0, 30).map((example) => (
              <article className={`learningExample ${example.approved ? 'approved' : ''}`} key={example.id}>
                <div>
                  <strong>{example.source_type.replace(/_/g, ' ')}</strong>
                  <small>{example.equipment_id ?? 'company-wide'} · {formatDate(example.created_at)}</small>
                </div>
                <div className="judgeScoreRow">
                  <span className={`judgeBadge ${example.judge_label}`}>
                    {Math.round(example.judge_score * 100)}% · {example.judge_label.replace(/_/g, ' ')}
                  </span>
                  <small>{example.judge_used_live_provider ? 'Live LLM judge' : 'Judge fallback'} · {example.judge_provider}</small>
                </div>
                <p>{example.instruction}</p>
                <blockquote>{clipText(example.expected_output, 220)}</blockquote>
                {example.judge_rationale && <p className="judgeRationale">{clipText(example.judge_rationale, 220)}</p>}
                <div className="learningExampleActions">
                  <button className="outlineButton" onClick={() => judgeLearningExample(example)} disabled={learningJudgingExampleId === example.id}>
                    {learningJudgingExampleId === example.id ? <span className="loadingSpinner" aria-hidden="true" /> : null}
                    {learningJudgingExampleId === example.id ? 'Judging...' : 'Judge'}
                  </button>
                  <button className={example.approved ? 'outlineButton' : 'textButton'} onClick={() => toggleLearningApproval(example)}>
                    {example.approved ? 'Remove approval' : 'Approve'}
                  </button>
                </div>
              </article>
            )) : (
              <p className="emptyState">No learning examples have been generated yet.</p>
            )}
          </div>
        </section>
        <section className="learningPanel">
          <h3>Model and Prompt Versions</h3>
          <div className="versionList">
            {learningModels.map((model) => {
              const promotionEvaluation = passedEvaluationForModel(model.id)
              const latestDeployment = latestDeploymentForModel(model.id)
              const latestVerifiedDeployment = latestVerifiedDeploymentForModel(model.id)
              const canPromoteModel = model.status !== 'active' && Boolean(promotionEvaluation)
              const canRollbackModel = model.status === 'retired' && Boolean(promotionEvaluation)
              const canDeployModel = model.status === 'candidate' && Boolean(model.adapter_path)
              return (
                <div className="versionRow" key={model.id}>
                  <strong>{model.model_name}</strong>
                  <small>{model.provider} · {model.status}</small>
                  {model.adapter_path && <small>Adapter {model.adapter_path}</small>}
                  {latestDeployment && (
                    <small>
                      Latest deployment {latestDeployment.runtime_provider} · {latestDeployment.status} · health{' '}
                      {latestDeployment.health_status ?? 'not checked'}
                    </small>
                  )}
                  {latestVerifiedDeployment ? (
                    <small>
                      Verified deployment {latestVerifiedDeployment.served_model_name} · {latestVerifiedDeployment.serving_provider} ·{' '}
                      {formatDate(deploymentDisplayDate(latestVerifiedDeployment))}
                    </small>
                  ) : (
                    <small>No verified deployment recorded for this model.</small>
                  )}
                  {promotionEvaluation ? (
                    <small>Promotion gate passed by evaluation {promotionEvaluation.id}</small>
                  ) : model.status !== 'active' ? (
                    <small>Promotion gate requires a passing evaluation for this model.</small>
                  ) : null}
                  {model.notes && <p>{model.notes}</p>}
                  {(canPromoteModel || canRollbackModel || canDeployModel) && (
                    <div className="versionActions">
                      {canDeployModel && (
                        <button className="textButton" onClick={() => deployLearningAdapter(model)} disabled={learningLoading}>
                          <Upload size={16} />
                          Deploy adapter
                        </button>
                      )}
                      {canPromoteModel && (
                        <button className="textButton" onClick={() => promoteLearningAdapter(model)} disabled={learningLoading}>
                          <CheckCircle2 size={16} />
                          Promote adapter
                        </button>
                      )}
                      {canRollbackModel && (
                        <button className="outlineButton" onClick={() => rollbackLearningAdapter(model)} disabled={learningLoading}>
                          Roll back to this model
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
            {learningPrompts.map((prompt) => (
              <div className="versionRow" key={prompt.id}>
                <strong>{prompt.assistant} / {prompt.version}</strong>
                <small>{prompt.status}</small>
                {prompt.notes && <p>{prompt.notes}</p>}
              </div>
            ))}
          </div>
          <h3>Promotion Audit</h3>
          <div className="promotionList">
            {learningPromotions.length ? learningPromotions.map((promotion) => (
              <div className={`promotionRow ${promotion.action}`} key={promotion.id}>
                <span>
                  <strong>{promotion.action === 'promote' ? 'Adapter promoted' : 'Rollback completed'}</strong>
                  <small>{promotion.model_version_id} · {formatDate(promotion.created_at)}</small>
                </span>
                <small>Evaluation {promotion.evaluation_run_id} · Dataset {promotion.dataset_id}</small>
                <small>Reviewer {promotion.reviewer_email}</small>
                {promotion.previous_active_model_id && <small>Previous active {promotion.previous_active_model_id}</small>}
                {promotion.notes && <p>{promotion.notes}</p>}
              </div>
            )) : (
              <p className="emptyState">Adapter promotions and rollbacks will appear after a reviewer activates a passed model.</p>
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
            {learningDeploymentRecords.length ? learningDeploymentRecords.map((deployment) => (
              <div className={`deploymentRow ${deploymentStatusClass(deployment.status)} ${deploymentStatusClass(deployment.health_status)}`} key={deployment.id}>
                <span>
                  <strong>{deployment.served_model_name}</strong>
                  <small>{deployment.runtime_provider} · {deployment.serving_provider}</small>
                </span>
                <div className="deploymentBadges">
                  <span className={`deploymentBadge ${deploymentStatusClass(deployment.status)}`}>{deployment.status.replace(/_/g, ' ')}</span>
                  <span className={`deploymentBadge ${deploymentStatusClass(deployment.health_status)}`}>
                    health {deployment.health_status?.replace(/_/g, ' ') ?? 'not checked'}
                  </span>
                </div>
                <small>Model version {deployment.model_version_id} · {formatDate(deploymentDisplayDate(deployment))}</small>
                {deployment.base_url && <small>Base URL {deployment.base_url}</small>}
                {deployment.artifact_uri && <small>Artifact {deployment.artifact_uri}</small>}
                {deployment.error && <p>{deployment.error}</p>}
              </div>
            )) : (
              <p className="emptyState">Adapter runtime deployments will appear after a candidate deployment is queued.</p>
            )}
          </div>
          <h3>Adapter Candidate</h3>
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
            <button className="textButton" onClick={registerLearningAdapter} disabled={learningLoading || !adapterModelName.trim()}>
              <Sparkles size={16} />
              Register adapter
            </button>
          </div>
          <h3>Dataset Snapshots</h3>
          <div className="datasetList">
            {learningDatasets.length ? learningDatasets.map((snapshot) => (
              <div className="datasetRow" key={snapshot.id}>
                <span>
                  <strong>{snapshot.name}</strong>
                  <small>{snapshot.example_count} examples · {formatDate(snapshot.created_at)}</small>
                </span>
                <button className="iconTextButton" onClick={() => downloadLearningSnapshot(snapshot)}>
                  <Download size={16} />
                  JSONL
                </button>
              </div>
            )) : (
              <p className="emptyState">Create a snapshot after approving examples.</p>
            )}
          </div>
          <h3>Evaluation Runs</h3>
          <button className="textButton fullWidthAction" onClick={runLearningEvaluation} disabled={learningLoading}>
            <CheckCircle2 size={16} />
            Run dataset evaluation
          </button>
          <div className="evaluationList">
            {learningEvaluations.length ? learningEvaluations.map((run) => (
              <div className={`evaluationRow ${run.passed ? 'passed' : 'review'}`} key={run.id}>
                <span>
                  <strong>{run.passed ? 'Passed' : 'Needs review'}</strong>
                  <small>{formatDate(run.created_at)}</small>
                </span>
                <div className="evaluationMetrics">
                  <span>Quality <strong>{metricValue(run.metrics.quality_score)}</strong></span>
                  <span>Avg judge <strong>{metricValue(run.metrics.average_judge_score)}</strong></span>
                  <span>Sources <strong>{metricValue(run.metrics.source_type_coverage)}</strong></span>
                  <span>Assets <strong>{metricValue(run.metrics.asset_coverage)}</strong></span>
                </div>
                {run.notes && <p>{run.notes}</p>}
              </div>
            )) : (
              <p className="emptyState">Run an evaluation after creating a dataset snapshot.</p>
            )}
          </div>
          <h3>Async Learning Jobs</h3>
          <div className="learningAdapterGrid">
            <label className="field adapterNotesField">
              <span>PEFT adapter job name</span>
              <input value={peftAdapterName} onChange={(event) => setPeftAdapterName(event.target.value)} />
            </label>
            <button className="textButton fullWidthAction" onClick={queuePeftTuningJob} disabled={learningLoading}>
              <Sparkles size={16} />
              Queue PEFT tuning job
            </button>
          </div>
          <div className="jobList">
            {learningJobs.length ? learningJobs.map((job) => (
              <div className={`jobRow ${job.status}`} key={job.id}>
                <span>
                  <strong>{job.job_type.replace(/_/g, ' ')}</strong>
                  <small>{job.status} · {formatDate(job.updated_at)}</small>
                </span>
                <small>{job.subject}</small>
                {job.error && <p>{job.error}</p>}
                {typeof job.output_refs.dispatch === 'string' && <p>{job.output_refs.dispatch}</p>}
              </div>
            )) : (
              <p className="emptyState">Learning jobs will appear after review, dataset, evaluation, or PEFT queue actions.</p>
            )}
          </div>
          <h3>Learning Artifacts</h3>
          <div className="artifactList">
            {learningArtifacts.length ? learningArtifacts.map((artifact) => (
              <div className="artifactRow" key={artifact.id}>
                <span>
                  <strong>{artifact.artifact_type.replace(/_/g, ' ')}</strong>
                  <small>{artifact.job_id} · {formatDate(artifact.created_at)}</small>
                </span>
                <small>sha256 {artifact.content_hash.slice(0, 12)}</small>
              </div>
            )) : (
              <p className="emptyState">Worker-produced datasets, manifests, and adapter artifacts will appear here.</p>
            )}
          </div>
        </section>
      </div>
    </section>
  )
}
