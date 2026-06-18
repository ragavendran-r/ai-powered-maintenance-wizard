import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { LearningReviewRoute } from './LearningReview'

const learningExample = {
  id: 'LEX-FEEDBACK-1',
  source_type: 'feedback',
  source_id: 'FB-1',
  equipment_id: 'RM-DRIVE-01',
  work_order_id: null,
  instruction: 'Improve future maintenance recommendations from accepted engineer feedback.',
  input_text: 'Actual root cause: loose foundation bolt resonance.',
  expected_output: 'Root cause: loose foundation bolt resonance. Action: retorqued foundation bolts. Outcome: vibration normalized.',
  metadata: { status: 'accepted' },
  approved: true,
  judge_score: 0.82,
  judge_label: 'training_worthy',
  judge_rationale: 'Specific, outcome-backed feedback is suitable for retrieval reuse and local adapter tuning.',
  judge_provider: 'openai',
  judge_used_live_provider: true,
  judged_at: '2026-06-13T09:00:00+05:30',
  created_at: '2026-06-13T09:00:00+05:30',
}

const learningDataset = {
  id: 'LDS-1',
  name: 'maintenance-wizard-learning-snapshot',
  description: 'Approved examples for local LLM adapter tuning and evaluation.',
  example_count: 1,
  approved_only: true,
  jsonl_content: '{"messages":[]}',
  created_by: 'admin@plant.local',
  created_at: '2026-06-13T09:05:00+05:30',
}

const learningEvaluation = {
  id: 'LEVAL-1',
  dataset_id: 'LDS-1',
  model_version_id: 'model-adapter-candidate',
  prompt_version_id: 'prompt-neo-default',
  metrics: {
    quality_score: 0.81,
    average_judge_score: 0.82,
    source_type_coverage: 1,
    asset_coverage: 1,
  },
  notes: 'Dataset quality evaluation by reliability@plant.local.',
  passed: true,
  created_at: '2026-06-13T09:10:00+05:30',
}

const learningPromotion = {
  id: 'LPROMO-1',
  model_version_id: 'model-adapter-candidate',
  previous_active_model_id: 'model-local-qwen2.5-current',
  evaluation_run_id: 'LEVAL-1',
  dataset_id: 'LDS-1',
  prompt_version_id: 'prompt-neo-default',
  action: 'promote',
  reviewer_email: 'reliability@plant.local',
  notes: 'Promoted after passed evaluation.',
  created_at: '2026-06-13T09:20:00+05:30',
}

const learningJob = {
  id: 'LJOB-1',
  job_type: 'dataset_snapshot',
  subject: 'maintenance.learning.dataset.requested',
  status: 'completed',
  requested_by: 'reliability@plant.local',
  correlation_id: 'LJOB-1',
  input_refs: { approved_only: true },
  output_refs: {
    adapter_output_dir: 'backend/data/learning_adapters/LJOB-1/adapter',
    dataset_id: 'LDS-1',
    example_count: 1,
    registered_model_version_id: 'model-adapter-candidate',
    training_status: 'adapter_candidate_registered',
  },
  error: null,
  retry_count: 0,
  created_at: '2026-06-13T09:06:00+05:30',
  updated_at: '2026-06-13T09:06:00+05:30',
}

const learningArtifact = {
  id: 'LART-1',
  job_id: 'LJOB-1',
  artifact_type: 'peft_training_manifest',
  uri: 'artifact://learning/LJOB-1/training_manifest.json',
  content_hash: 'abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890',
  metadata: { adapter_name: 'maintenance-wizard-qwen-lora' },
  created_at: '2026-06-13T09:11:00+05:30',
}

const learningDeployment = {
  id: 'LDEPLOY-1',
  model_version_id: 'model-adapter-candidate',
  job_id: 'LJOB-DEPLOY-0',
  runtime_provider: 'llama_cpp',
  serving_provider: 'openai',
  served_model_name: 'qwen2.5-7b-instruct-lora-candidate',
  base_url: 'http://127.0.0.1:8080/v1',
  artifact_uri: 'file:///models/qwen2.5-lora',
  artifact_hash: 'abcdef1234567890',
  status: 'verified',
  health_status: 'healthy',
  health_checked_at: '2026-06-13T09:25:00+05:30',
  metadata: { source: 'learning-review' },
  error: null,
  created_at: '2026-06-13T09:22:00+05:30',
  updated_at: '2026-06-13T09:25:00+05:30',
}

const learningEmbeddingProfile = {
  id: 'emb-maintenance-hash-v1-64',
  provider: 'deterministic_hash',
  model: 'maintenance-hash-v1',
  version: '1',
  dimensions: 64,
  distance: 'Cosine',
  status: 'active',
  notes: 'Default local deterministic embedding profile.',
  metadata: {},
  created_at: '2026-06-13T09:00:00+05:30',
  updated_at: '2026-06-13T09:00:00+05:30',
}

const learningArtifactCleanupResult = {
  dry_run: true,
  cleanup_enabled: false,
  deletion_allowed: false,
  store: 'filesystem',
  retention: { state: 'disabled', retention_days: 7, cleanup_enabled: false },
  expired_count: 1,
  protected_count: 1,
  deleted_count: 0,
  candidates: [
    {
      artifact_id: 'artifact-expired',
      artifact_type: 'dataset_snapshot',
      path: 'LJOB-OLD/dataset.jsonl',
      age_days: 14,
    },
  ],
  protected: [
    {
      artifact_id: 'artifact-1',
      artifact_type: 'peft_training_manifest',
      path: 'LJOB-PEFT-1/training-manifest.json',
      protected_reason: 'active/candidate/promoted model reference',
    },
  ],
  deleted_paths: [],
  errors: [],
}

function learningSummaryPayload(
  examples = [learningExample],
  datasets = [learningDataset],
  evaluations = [learningEvaluation],
  jobs = [learningJob],
  artifacts = [learningArtifact],
  promotions = [learningPromotion],
  deployments = [learningDeployment],
) {
  return {
    counts: {
      interactions: 3,
      examples: examples.length,
      approved_examples: examples.filter((example) => example.approved).length,
      snapshots: datasets.length,
      model_versions: 1,
      prompt_versions: 1,
      evaluation_runs: evaluations.length,
      jobs: jobs.length,
      queued_jobs: jobs.filter((job) => ['queued', 'published', 'running'].includes(job.status)).length,
      artifacts: artifacts.length,
      promotions: promotions.length,
      deployments: deployments.length,
    },
    recent_examples: examples,
    recent_snapshots: datasets,
    model_versions: [
      {
        id: 'model-adapter-candidate',
        provider: 'openai',
        model_name: 'qwen2.5-7b-instruct-lora-candidate',
        base_model: 'qwen2.5-7b-instruct',
        adapter_path: 'file:///models/qwen2.5-lora',
        status: 'candidate',
        notes: 'Offline PEFT adapter candidate trained from approved judge-qualified examples.',
        created_at: '2026-06-13T09:12:00+05:30',
      },
      {
        id: 'model-local-qwen2.5-current',
        provider: 'openai',
        model_name: 'qwen2.5-7b-instruct',
        base_model: 'Qwen2.5',
        adapter_path: null,
        status: 'active',
        notes: 'Local OpenAI-compatible runtime used by Neo, Morpheus, and Smith.',
        created_at: '2026-06-13T09:00:00+05:30',
      },
    ],
    prompt_versions: [
      {
        id: 'prompt-neo-default',
        assistant: 'neo',
        version: 'default',
        prompt: 'Role-safe maintenance assistant.',
        status: 'active',
        notes: 'Shared dashboard assistant prompt.',
        created_at: '2026-06-13T09:00:00+05:30',
      },
    ],
    evaluation_runs: evaluations,
    recent_jobs: jobs,
    recent_artifacts: artifacts,
    recent_promotions: promotions,
    recent_deployments: deployments,
    serving_model: {
      provider: 'openai',
      openai_model: 'qwen2.5-7b-instruct',
      ollama_model: 'llama3.1',
      openai_base_url: 'http://127.0.0.1:8080/v1',
      ollama_base_url: 'http://localhost:11434',
      source: 'learning_active_model',
      active_model_version_id: 'model-local-qwen2.5-current',
      adapter_path: null,
      base_model: 'Qwen2.5',
      status: 'active',
      warning: null,
    },
    artifact_store: {
      store: 'filesystem',
      local_dir: 'backend/data/learning_artifacts',
      state: 'ready',
      retention: { state: 'disabled', retention_days: 7, cleanup_enabled: false },
    },
    peft_trainer: {
      mode: 'external_command',
      configured: true,
      timeout_seconds: 7200,
      output_dir: 'backend/data/learning_adapters',
      model_source: 'Qwen/Qwen2.5-7B-Instruct',
      quantization: 'none',
    },
    vector_store: {
      store: 'qdrant',
      enabled: true,
      collection: 'maintenance_wizard_documents',
      collection_alias: null,
      url: 'http://localhost:6333',
      embedding_profile: {
        ...learningEmbeddingProfile,
        configured_dimensions: 64,
        state: 'ready',
        warning: null,
      },
      points_count: 42,
      collection_vector_size: 64,
      collection_distance: 'Cosine',
      migration_required: false,
      migration_reasons: [],
      state: 'ready',
      error: null,
    },
  }
}

function renderMockedLearningReview(overrides: Record<string, unknown> = {}) {
  const noop = vi.fn()
  const props = {
    activateSelectedEmbeddingProfile: noop,
    adapterBaseModel: 'Qwen/Qwen2.5-7B-Instruct',
    adapterModelName: 'qwen2.5-7b-instruct-lora-candidate',
    adapterNotes: 'Local adapter candidate',
    adapterPath: 'file:///models/qwen2.5-lora',
    adapterProvider: 'openai',
    artifactCleanupResult: null,
    createLearningSnapshot: noop,
    deployLearningAdapter: noop,
    deploymentBaseUrl: 'http://localhost:8001/v1',
    deploymentRuntimeProvider: 'llama_cpp',
    downloadLearningSnapshot: noop,
    judgeLearningExample: noop,
    learningDatasetDescription: 'Approved examples for local LLM adapter tuning and evaluation.',
    learningDatasetName: 'maintenance-wizard-learning-snapshot',
    learningDatasets: [learningDataset],
    learningDeployments: [learningDeployment],
    learningEmbeddingProfiles: [learningEmbeddingProfile],
    learningExamples: [learningExample],
    learningJudgingExampleId: null,
    learningLoading: {},
    learningSummary: learningSummaryPayload(),
    peftAdapterName: 'maintenance-wizard-qwen-lora',
    previewLearningArtifactCleanup: noop,
    previewLearningRagMigration: noop,
    promoteLearningAdapter: noop,
    queuePeftTuningJob: noop,
    ragMigrationPreview: null,
    ragTargetCollection: 'maintenance_wizard_documents_v1',
    refreshLearningExamples: noop,
    refreshLearningStatus: noop,
    registerLearningAdapter: noop,
    reindexLearningRag: noop,
    rollbackLearningAdapter: noop,
    runLearningEvaluation: noop,
    runLearningRagMigration: noop,
    selectedEmbeddingProfileId: learningEmbeddingProfile.id,
    selectedLearningDatasetId: learningDataset.id,
    selectedLearningModelId: 'model-adapter-candidate',
    selectedLearningPromptId: 'prompt-neo-default',
    setAdapterBaseModel: noop,
    setAdapterModelName: noop,
    setAdapterNotes: noop,
    setAdapterPath: noop,
    setAdapterProvider: noop,
    setDeploymentBaseUrl: noop,
    setDeploymentRuntimeProvider: noop,
    setLearningDatasetDescription: noop,
    setLearningDatasetName: noop,
    setPeftAdapterName: noop,
    setRagTargetCollection: noop,
    setSelectedEmbeddingProfileId: noop,
    setSelectedLearningDatasetId: noop,
    setSelectedLearningModelId: noop,
    setSelectedLearningPromptId: noop,
    toggleLearningApproval: noop,
    ...overrides,
  }
  render(<LearningReviewRoute {...props} />)
  return props
}

function openAdapterLifecycle() {
  fireEvent.click(screen.getByRole('tab', { name: 'Adapter lifecycle' }))
  expect(screen.getByRole('tab', { name: 'Adapter lifecycle' })).toHaveAttribute('aria-selected', 'true')
}

function expectAdapterLifecycleSectionsInOrder() {
  const lifecycleHeadings = [
    'Dataset Validation',
    'PEFT Tuning Job',
    'Learning Job Trail',
    'Learning Artifacts',
    'Adapter Candidate Versions',
    'Adapter Runtime Deployments',
    'Promotion Audit',
    'Local Adapter Candidate',
  ].map((name) => screen.getByRole('heading', { name }))
  lifecycleHeadings.slice(0, -1).forEach((heading, index) => {
    expect(Boolean(heading.compareDocumentPosition(lifecycleHeadings[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
  })
}

afterEach(() => cleanup())

it('shows adapter lifecycle baseline state without starting training polling', () => {
  renderMockedLearningReview()
  openAdapterLifecycle()
  const adapterPanel = screen.getByRole('tabpanel', { name: 'Adapter lifecycle' })
  const adapterText = adapterPanel.textContent ?? ''
  expect(adapterText).toContain('Serving LLM')
  expect(adapterText).toMatch(/learning active model/i)
  expect(adapterText).toContain('model-local-qwen2.5-current')
  expect(adapterText).toContain('Artifact store')
  expect(adapterText).toMatch(/filesystem/i)
  expect(adapterText).toMatch(/disabled\s*·\s*7 days/i)
  expect(adapterText).toContain('PEFT trainer')
  expect(adapterText).toMatch(/external_command/i)
  expect(adapterText).toContain('Worker will train adapter')
  expect(adapterText).toContain('Qwen/Qwen2.5-7B-Instruct')
  expect(adapterText).toContain('Passed')
  expect(adapterText).toContain('Quality')
  expectAdapterLifecycleSectionsInOrder()
  const validationButton = within(adapterPanel).getByRole('button', { name: 'Run dataset validation' })
  const peftQueueButton = within(adapterPanel).getByRole('button', { name: 'Queue PEFT training job' })
  expect(Boolean(validationButton.compareDocumentPosition(peftQueueButton) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
  expect(within(adapterPanel).getByLabelText('Dataset snapshot')).toBeInTheDocument()
  expect(within(adapterPanel).getByLabelText('Source model version')).toBeInTheDocument()
  expect(within(adapterPanel).getByLabelText('Prompt version')).toBeInTheDocument()
  expect(adapterText).toContain('Current PEFT training')
  const initialJobTrailTable = within(adapterPanel).getByRole('table', { name: 'Learning job trail' })
  expect(within(initialJobTrailTable).getByText('completed')).toBeInTheDocument()
  expect(within(initialJobTrailTable).getByText('Training adapter candidate registered')).toBeInTheDocument()
  expect(within(initialJobTrailTable).getByText('Registered model model-adapter-candidate')).toBeInTheDocument()
  expect(within(initialJobTrailTable).getByText(/Adapter output .*learning_adapters.*adapter/)).toBeInTheDocument()
  expect(within(adapterPanel).getByRole('table', { name: 'Dataset validation runs' })).toBeInTheDocument()
  expect(within(adapterPanel).getByRole('table', { name: 'Learning artifacts' })).toBeInTheDocument()
  expect(within(adapterPanel).getByRole('table', { name: 'Adapter runtime deployments' })).toBeInTheDocument()
  expect(within(adapterPanel).getByRole('table', { name: 'Promotion audit' })).toBeInTheDocument()
  expect(adapterText).not.toContain('neo / default')
  expect(adapterText).not.toContain('morpheus / default')
  expect(adapterText).not.toContain('smith / default')
  expect(adapterText).toContain('peft training manifest')
  expect(adapterText).toContain('artifact://learning/LJOB-1/training_manifest.json')
  expect(adapterText).toMatch(/sha256 abcdef123456/)
  expect(adapterText).toContain('Promotion Audit')
  expect(adapterText).toContain('Adapter promoted')
  expect(adapterText).toMatch(/Evaluation gate passed by LEVAL-1/)
  expect(adapterText).toMatch(/Promotion recorded as LPROMO-1/)
  expect(adapterText).toMatch(/Runtime-loaded alias qwen2\.5-7b-instruct-lora-candidate/)
  const initialDeploymentTable = within(adapterPanel).getByRole('table', { name: 'Adapter runtime deployments' })
  expect(within(initialDeploymentTable).getByText('verified')).toBeInTheDocument()
  expect(within(initialDeploymentTable).getByText('healthy')).toBeInTheDocument()
})

it('renders when optional summary lifecycle arrays are absent without recursive updates', () => {
  const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)
  const partialSummary = {
    ...learningSummaryPayload(),
    evaluation_runs: undefined,
    recent_artifacts: undefined,
    recent_jobs: undefined,
    recent_promotions: undefined,
  }

  renderMockedLearningReview({
    learningSummary: partialSummary,
  })
  openAdapterLifecycle()

  expect(screen.getByRole('tabpanel', { name: 'Adapter lifecycle' })).toBeInTheDocument()
  expect(
    consoleError.mock.calls.some(([message]) => String(message).includes('Maximum update depth exceeded')),
  ).toBe(false)
  consoleError.mockRestore()
})

it('handles adapter lifecycle actions without relying on one end-to-end script', () => {
  const registerLearningAdapter = vi.fn()
  const runLearningEvaluation = vi.fn()
  const queuePeftTuningJob = vi.fn()
  renderMockedLearningReview({
    learningSummary: learningSummaryPayload(
      [learningExample],
      [learningDataset],
      [learningEvaluation],
      [
        {
          ...learningJob,
          id: 'LJOB-PEFT-1',
          job_type: 'peft_tuning',
          subject: 'maintenance.learning.peft.requested',
          status: 'queued',
          output_refs: { dispatch: 'disabled' },
        },
        learningJob,
      ],
    ),
    queuePeftTuningJob,
    registerLearningAdapter,
    runLearningEvaluation,
  })

  openAdapterLifecycle()
  const adapterPanel = screen.getByRole('tabpanel', { name: 'Adapter lifecycle' })
  const validationButton = within(adapterPanel).getByRole('button', { name: 'Run dataset validation' })
  const peftQueueButton = within(adapterPanel).getByRole('button', { name: 'Queue PEFT training job' })
  fireEvent.change(within(adapterPanel).getByLabelText('Adapter path'), { target: { value: 'file:///models/qwen2.5-lora' } })
  fireEvent.click(within(adapterPanel).getByRole('button', { name: 'Register local adapter candidate' }))
  expect(registerLearningAdapter).toHaveBeenCalled()

  fireEvent.click(validationButton)
  expect(runLearningEvaluation).toHaveBeenCalled()

  fireEvent.click(peftQueueButton)
  expect(queuePeftTuningJob).toHaveBeenCalled()
  expect(adapterPanel.textContent ?? '').toContain('LJOB-PEFT-1')
  expect(adapterPanel.textContent ?? '').toContain('queued')
  expect(screen.getByRole('tabpanel', { name: 'Adapter lifecycle' }).textContent ?? '').toContain('disabled')
  fireEvent.click(screen.getByRole('tab', { name: 'Examples & judgments' }))
})

it('handles adapter cleanup and runtime deployment actions separately from training polling', () => {
  const previewLearningArtifactCleanup = vi.fn()
  const deployLearningAdapter = vi.fn()
  const promoteLearningAdapter = vi.fn()
  renderMockedLearningReview({
    artifactCleanupResult: learningArtifactCleanupResult,
    deployLearningAdapter,
    previewLearningArtifactCleanup,
    promoteLearningAdapter,
  })

  openAdapterLifecycle()
  const adapterPanel = screen.getByRole('tabpanel', { name: 'Adapter lifecycle' })
  fireEvent.click(within(adapterPanel).getByRole('button', { name: 'Preview cleanup' }))
  expect(previewLearningArtifactCleanup).toHaveBeenCalled()
  expect(screen.getByText('Artifact lifecycle preview')).toBeInTheDocument()
  expect(screen.getByText('LJOB-OLD/dataset.jsonl')).toBeInTheDocument()
  expect(screen.getByText('active/candidate/promoted model reference')).toBeInTheDocument()

  fireEvent.change(within(adapterPanel).getByLabelText('Runtime provider'), { target: { value: 'vllm' } })
  fireEvent.change(within(adapterPanel).getByLabelText('Runtime base URL'), { target: { value: 'http://localhost:8001/v1' } })
  fireEvent.click(within(adapterPanel).getByRole('button', { name: 'Deploy adapter to runtime' }))
  expect(deployLearningAdapter).toHaveBeenCalledWith(expect.objectContaining({ id: 'model-adapter-candidate' }))

  fireEvent.click(within(adapterPanel).getByRole('button', { name: 'Promote runtime-loaded adapter' }))
  expect(promoteLearningAdapter).toHaveBeenCalledWith(expect.objectContaining({ id: 'model-adapter-candidate' }))
})

it('previews and reindexes Qdrant learning RAG independently from adapter lifecycle', () => {
  const previewLearningRagMigration = vi.fn()
  const reindexLearningRag = vi.fn()
  renderMockedLearningReview({
    previewLearningRagMigration,
    ragMigrationPreview: {
      dry_run: true,
      store: 'qdrant',
      source_collection: 'maintenance_wizard_documents',
      target_collection: 'maintenance_wizard_documents_v1',
      active_profile: learningEmbeddingProfile,
      target_profile: learningEmbeddingProfile,
      migration_required: false,
      will_activate_profile: false,
      will_recreate_collection: false,
      reasons: ['Existing collection matches the selected embedding profile.'],
      status: learningSummaryPayload().vector_store,
    },
    reindexLearningRag,
  })
  fireEvent.click(screen.getByRole('tab', { name: 'Qdrant migration' }))
  const vectorPanel = screen.getByRole('tabpanel', { name: 'Qdrant migration' })
  const vectorText = vectorPanel.textContent ?? ''
  expect(screen.getByRole('tab', { name: 'Qdrant migration' })).toHaveAttribute('aria-selected', 'true')
  expect(vectorText).toMatch(/Qdrant migration is only required when the embedding profile/)
  expect(vectorText).toContain('RAG vector DB')
  expect(vectorText).toMatch(/qdrant/i)
  expect(vectorText).toContain('Active embedding')
  expect(vectorText).toMatch(/deterministic_hash.*maintenance-hash-v1.*v1/)
  expect(vectorText).toContain('Embedding profile')
  expect(within(vectorPanel).getByRole('button', { name: 'Preview migration' })).toBeInTheDocument()
  expect(within(vectorPanel).getByRole('button', { name: 'Run Qdrant migration' })).toBeInTheDocument()
  expect(vectorText).toContain('Migration')
  expect(vectorText).toContain('Current')
  expect(vectorText).toContain('Migration preview')

  fireEvent.click(within(vectorPanel).getByRole('button', { name: 'Preview migration' }))
  expect(previewLearningRagMigration).toHaveBeenCalled()

  fireEvent.click(within(vectorPanel).getByRole('button', { name: 'Reindex current profile' }))
  expect(reindexLearningRag).toHaveBeenCalled()
})

it('keeps Qdrant migration controls independent while learning examples refresh', () => {
  renderMockedLearningReview({
    learningLoading: { refreshExamples: true },
  })

  const examplesPanel = screen.getByRole('tabpanel', { name: 'Examples & judgments' })
  const refreshButton = within(examplesPanel).getByRole('button', { name: 'Refresh examples' })
  expect(refreshButton).toBeDisabled()

  fireEvent.click(screen.getByRole('tab', { name: 'Qdrant migration' }))
  const vectorPanel = screen.getByRole('tabpanel', { name: 'Qdrant migration' })
  const migrationButton = within(vectorPanel).getByRole('button', { name: 'Run Qdrant migration' })
  expect(migrationButton).toBeEnabled()
  expect(migrationButton.querySelector('.loadingSpinner')).toBeNull()
})

it('shows judging progress for only the selected learning example', () => {
  const judgeLearningExample = vi.fn()
  renderMockedLearningReview({
    judgeLearningExample,
    learningJudgingExampleId: learningExample.id,
  })

  const reviewControlsTable = screen.getByRole('table', { name: 'Approved Controls' })
  const judgingButton = within(reviewControlsTable).getByRole('button', { name: 'Judging...' })
  expect(judgingButton).toBeDisabled()
  expect(judgingButton.querySelector('.loadingSpinner')).toBeInTheDocument()
  expect(within(reviewControlsTable).queryByRole('button', { name: 'Judge' })).not.toBeInTheDocument()
})
