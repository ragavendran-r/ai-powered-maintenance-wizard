import { expect, test, type Page, type Route } from '@playwright/test'

const adminUser = {
  id: 'USER-ADMIN',
  email: 'admin@plant.local',
  display_name: 'Plant Admin',
  role: 'admin',
  is_active: true,
}

const embeddingProfile = {
  id: 'rag-prof-active',
  provider: 'deterministic_hash',
  model: 'maintenance-hash-v1',
  version: '1',
  dimensions: 64,
  configured_dimensions: 64,
  distance: 'Cosine',
  status: 'active',
  state: 'ready',
  warning: null,
  notes: 'Default local profile',
  metadata: {},
  created_at: '2026-06-13T09:00:00+05:30',
  updated_at: '2026-06-13T09:00:00+05:30',
}

const learningSummary = {
  counts: {
    interactions: 1,
    examples: 1,
    approved_examples: 1,
    snapshots: 0,
    artifacts: 0,
    promotions: 0,
    deployments: 0,
  },
  recent_examples: [],
  recent_snapshots: [],
  model_versions: [
    {
      id: 'model-local-qwen',
      provider: 'openai',
      model_name: 'qwen2.5-7b-instruct',
      base_model: 'qwen2.5-7b-instruct',
      adapter_path: null,
      status: 'active',
      notes: 'Local model',
      created_at: '2026-06-13T09:00:00+05:30',
    },
  ],
  prompt_versions: [
    {
      id: 'prompt-neo-v1',
      assistant: 'neo',
      version: '1',
      prompt: 'Dashboard assistant',
      status: 'active',
      notes: null,
      created_at: '2026-06-13T09:00:00+05:30',
    },
  ],
  evaluation_runs: [],
  recent_jobs: [],
  recent_artifacts: [],
  recent_promotions: [],
  recent_deployments: [],
  serving_model: {
    provider: 'openai',
    openai_model: 'qwen2.5-7b-instruct',
    ollama_model: 'qwen2.5-7b-instruct',
    openai_base_url: 'http://localhost:1234/v1',
    ollama_base_url: 'http://localhost:11434',
    source: 'learning_active_model',
    active_model_version_id: 'model-local-qwen',
    adapter_path: null,
    base_model: 'qwen2.5-7b-instruct',
  },
  artifact_store: {
    store: 'filesystem',
    local_dir: 'backend/data/learning_artifacts',
    state: 'ready',
    retention: { state: 'disabled', retention_days: 0, cleanup_enabled: false },
  },
  peft_trainer: {
    mode: 'prepared_artifacts',
    configured: false,
    timeout_seconds: 900,
    output_dir: 'backend/data/learning_adapters',
  },
  vector_store: {
    store: 'qdrant',
    enabled: true,
    collection: 'maintenance_wizard_documents',
    collection_alias: null,
    url: 'http://localhost:6333',
    embedding_profile: embeddingProfile,
    points_count: 42,
    collection_vector_size: 64,
    collection_distance: 'Cosine',
    migration_required: false,
    migration_reasons: [],
    state: 'ready',
    error: null,
  },
}

function json(data: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  }
}

async function mockMaintenanceApi(page: Page) {
  await page.route('**/api/**', async (route: Route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname

    if (path === '/api/auth/login') {
      await route.fulfill(json({ access_token: 'pw-token', token_type: 'bearer', expires_in: 28800, user: adminUser }))
      return
    }
    if (path === '/api/auth/me') {
      await route.fulfill(json(adminUser))
      return
    }
    if (path === '/api/dashboard/summary') {
      await route.fulfill(json({ equipment_count: 0, active_alert_count: 0, critical_alert_count: 0, average_health_score: 100, highest_risk_equipment: [] }))
      return
    }
    if (path === '/api/assets' || path === '/api/work-orders' || path === '/api/users/technicians') {
      await route.fulfill(json([]))
      return
    }
    if (path === '/api/streaming/status') {
      await route.fulfill(json({ enabled: false, connected: false, stream: 'MW_IOT' }))
      return
    }
    if (path === '/api/neo/welcome') {
      await route.fulfill(json({ answer: 'I am Neo. No immediate attention items.', table: null, provider: 'mock', used_live_provider: false }))
      return
    }
    if (path === '/api/learning/summary') {
      await route.fulfill(json(learningSummary))
      return
    }
    if (path === '/api/learning/examples') {
      await route.fulfill(json([]))
      return
    }
    if (path === '/api/learning/datasets' || path === '/api/learning/model-deployments') {
      await route.fulfill(json([]))
      return
    }
    if (path === '/api/learning/rag/embedding-profiles') {
      await route.fulfill(json([embeddingProfile]))
      return
    }
    if (path === '/api/learning/rag/reindex') {
      await route.fulfill(
        json({
          id: 'LJOB-RAG-UI',
          job_type: 'rag_reindex',
          subject: 'maintenance.learning.rag.reindex.requested',
          status: 'completed',
          requested_by: 'admin@plant.local',
          correlation_id: 'corr-rag-ui',
          input_refs: {},
          output_refs: {
            document_count: 6,
            chunk_count: 14,
            index_result: {
              store: 'qdrant',
              collection: 'maintenance_wizard_documents',
              indexed: 14,
              state: 'indexed',
            },
            learning_example_count: 1,
            learning_index_result: {
              store: 'qdrant',
              collection: 'maintenance_wizard_documents',
              eligible: 1,
              indexed: 1,
              deleted: 0,
              state: 'synced',
            },
          },
          error: null,
          retry_count: 0,
          created_at: '2026-06-13T09:30:00+05:30',
          updated_at: '2026-06-13T09:30:00+05:30',
        }),
      )
      return
    }

    await route.fulfill(json({ detail: `Unhandled mocked route ${path}` }, 404))
  })
}

test('shows approved learning-example Qdrant sync after Learning Review reindex', async ({ page }) => {
  await mockMaintenanceApi(page)
  await page.goto('/')

  await page.getByRole('button', { name: 'Sign In' }).click()
  await expect(page.getByText('Plant Admin')).toBeVisible()

  await page.getByRole('button', { name: 'Learning' }).click()
  await expect(page.getByRole('heading', { name: 'Learning and Tuning' })).toBeVisible()
  await expect(page.getByText('qdrant · ready')).toBeVisible()

  await page.getByRole('button', { name: 'Reindex current profile' }).click()

  await expect(
    page.getByText('Reindexed 14 RAG chunks and synced 1 approved learning example (synced) with status completed'),
  ).toBeVisible()
})
