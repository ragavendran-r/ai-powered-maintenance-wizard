import { readFileSync } from 'node:fs'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api, type AssistantStreamEvent, type NeoChatResponse, type NeoStreamEvent, type UserRole } from './services/api'

const sampleFiles = [
  {
    sourceType: 'sop',
    equipmentId: 'RM-DRIVE-01',
    assetName: 'Hot Strip Mill Main Drive Motor',
    path: '../assets/ingestion_samples/RM-DRIVE-01_SOP_main_drive_bearing_vibration.md',
    fileName: 'RM-DRIVE-01_SOP_main_drive_bearing_vibration.md',
    mimeType: 'text/markdown',
  },
  {
    sourceType: 'manual',
    equipmentId: 'BF-BLOWER-02',
    assetName: 'Blast Furnace Combustion Air Blower',
    path: '../assets/ingestion_samples/BF-BLOWER-02_MANUAL_inlet_guide_vane_actuator.txt',
    fileName: 'BF-BLOWER-02_MANUAL_inlet_guide_vane_actuator.txt',
    mimeType: 'text/plain',
  },
  {
    sourceType: 'log',
    equipmentId: 'HYD-SYS-04',
    assetName: 'Hot Rolling Hydraulic System',
    path: '../assets/ingestion_samples/HYD-SYS-04_LOG_hydraulic_temperature_pulsation.log',
    fileName: 'HYD-SYS-04_LOG_hydraulic_temperature_pulsation.log',
    mimeType: 'text/plain',
  },
  {
    sourceType: 'alert',
    equipmentId: 'OH-CRANE-05',
    assetName: 'Melt Shop Overhead Crane',
    path: '../assets/ingestion_samples/OH-CRANE-05_ALERT_hoist_current_brake_temperature.json',
    fileName: 'OH-CRANE-05_ALERT_hoist_current_brake_temperature.json',
    mimeType: 'application/json',
  },
  {
    sourceType: 'spares',
    equipmentId: 'CC-PUMP-03',
    assetName: 'Continuous Caster Cooling Water Pump',
    path: '../assets/ingestion_samples/CC-PUMP-03_SPARES_cooling_pump_inventory.csv',
    fileName: 'CC-PUMP-03_SPARES_cooling_pump_inventory.csv',
    mimeType: 'text/csv',
  },
  {
    sourceType: 'history',
    equipmentId: 'RM-DRIVE-01',
    assetName: 'Hot Strip Mill Main Drive Motor',
    path: '../assets/ingestion_samples/RM-DRIVE-01_HISTORY_drive_bearing_maintenance.json',
    fileName: 'RM-DRIVE-01_HISTORY_drive_bearing_maintenance.json',
    mimeType: 'application/json',
  },
]

let neoResponseDelayMs = 0
let assistantResponseDelayMs = 0

function neoStreamResponse(response: NeoChatResponse, tokenChunks: string[] = []) {
  const events: NeoStreamEvent[] = tokenChunks.length
    ? [
        { type: 'meta', provider: response.provider, used_live_provider: response.used_live_provider },
        ...tokenChunks.map((content) => ({ type: 'token' as const, content })),
        { type: 'done', response },
      ]
    : [{ type: 'done', response }]
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function assistantStreamResponse<TResponse extends { provider: string; used_live_provider: boolean }>(
  response: TResponse,
  tokenChunks: string[] = [],
) {
  const events: AssistantStreamEvent<TResponse>[] = tokenChunks.length
    ? [
        { type: 'meta', provider: response.provider, used_live_provider: response.used_live_provider },
        ...tokenChunks.map((content) => ({ type: 'token' as const, content })),
        { type: 'done', response },
      ]
    : [{ type: 'done', response }]
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

const dashboard = {
  equipment_count: 5,
  active_alert_count: 5,
  critical_alert_count: 2,
  average_health_score: 18,
  highest_risk_equipment: [
    {
      equipment: {
        id: 'RM-DRIVE-01',
        name: 'Hot Strip Mill Main Drive Motor',
        area: 'Hot Rolling Mill',
        process: 'Finishing stand drive',
        criticality: 5,
        status: 'degraded',
      },
      risk_level: 'critical',
      health_score: 0,
      active_alerts: [
        {
          id: 'ALT-1001',
          equipment_id: 'RM-DRIVE-01',
          timestamp: '2026-06-06T08:15:00+05:30',
          signal: 'drive_end_vibration',
          value: 9.8,
          unit: 'mm/s',
          threshold: 7.1,
          severity: 'critical',
          message: 'Drive end vibration exceeds trip advisory threshold',
        },
      ],
      anomalies: [
        {
          equipment_id: 'RM-DRIVE-01',
          signal: 'drive_end_vibration',
          timestamp: '2026-06-06T08:15:00+05:30',
          value: 9.8,
          unit: 'mm/s',
          baseline_mean: 5.24,
          z_score: 8.35,
          threshold: 7.1,
          threshold_breached: true,
          trend_delta: 4.56,
          risk_level: 'critical',
          explanation: 'drive_end_vibration is critical risk.',
        },
      ],
      top_spares_constraints: [
        {
          id: 'SP-001',
          equipment_id: 'RM-DRIVE-01',
          name: 'Drive end spherical roller bearing',
          available_qty: 0,
          lead_time_days: 21,
          criticality: 5,
        },
      ],
      notes: ['2 active alert(s) require maintenance review.'],
    },
    {
      equipment: {
        id: 'OH-CRANE-05',
        name: 'Melt Shop Overhead Crane',
        area: 'Melt Shop',
        process: 'Ladle handling and maintenance lifting',
        criticality: 5,
        status: 'watch',
      },
      risk_level: 'critical',
      health_score: 0,
      active_alerts: [],
      anomalies: [],
      top_spares_constraints: [],
      notes: ['Crane hoist current and brake temperature require review.'],
    },
    {
      equipment: {
        id: 'HYD-SYS-04',
        name: 'Hot Rolling Hydraulic System',
        area: 'Hot Rolling Mill',
        process: 'AGC and roll gap hydraulic control',
        criticality: 4,
        status: 'degraded',
      },
      risk_level: 'high',
      health_score: 22,
      active_alerts: [],
      anomalies: [],
      top_spares_constraints: [],
      notes: ['Hydraulic oil temperature and pressure pulsation require review.'],
    },
    {
      equipment: {
        id: 'BF-BLOWER-02',
        name: 'Blast Furnace Combustion Air Blower',
        area: 'Blast Furnace',
        process: 'Combustion air supply',
        criticality: 5,
        status: 'watch',
      },
      risk_level: 'high',
      health_score: 29,
      active_alerts: [],
      anomalies: [],
      top_spares_constraints: [],
      notes: ['Blower pressure variance requires review.'],
    },
    {
      equipment: {
        id: 'CC-PUMP-03',
        name: 'Continuous Caster Cooling Water Pump',
        area: 'Continuous Casting',
        process: 'Secondary cooling',
        criticality: 4,
        status: 'normal',
      },
      risk_level: 'low',
      health_score: 72,
      active_alerts: [],
      anomalies: [],
      top_spares_constraints: [],
      notes: ['No active abnormality detected in sample data.'],
    },
  ],
}

const recommendation = {
  id: 'rec-test',
  equipment_id: 'RM-DRIVE-01',
  diagnosis: 'Hot Strip Mill Main Drive Motor shows symptoms consistent with drive end vibration.',
  probable_root_causes: ['Bearing wear'],
  risk_level: 'critical',
  urgency: 'Immediate engineering review required within the current shift.',
  remaining_useful_life_days: 23,
  confidence: 0.77,
  immediate_actions: ['Reduce load or schedule controlled shutdown.'],
  planned_actions: ['Trend the abnormal signal.'],
  spares_strategy: ['Review Drive end spherical roller bearing: 0 on hand, 21 day lead time.'],
  learning_notes: ['corrected recommendation feedback; actual root cause: Loose foundation bolt resonance'],
  evidence: [
    {
      source_type: 'sop',
      source_id: 'DOC-RM-SOP-01::chunk-000',
      title: 'Hot Strip Mill Main Drive Vibration SOP',
      excerpt: 'Inspect bearing housing temperature and coupling alignment.',
      equipment_id: 'RM-DRIVE-01',
    },
  ],
  used_live_provider: false,
  provider: 'mock',
  report_summary: 'Critical risk with estimated RUL of 23 days.',
}

const workOrders = [
  {
    id: 'WO-8304',
    equipment_id: 'RM-DRIVE-01',
    title: 'Inspect main drive bearing vibration',
    description: 'Inspect bearing housing, coupling alignment, lubrication condition, and foundation bolts.',
    status: 'APPR',
    priority: 1,
    work_type: 'CM',
    failure_class: 'MECH',
    problem_code: 'BRGVIB',
    classification: 'Bearing vibration',
    assigned_to: 'Maintenance Technician',
    supervisor: 'Maintenance Supervisor',
    due_date: '2026-06-12T18:00:00+05:30',
    recommended_action: 'Reduce load if vibration persists and verify coupling alignment.',
    follow_up_required: true,
    ai_summary: 'High-risk drive vibration needs mechanical inspection before restart.',
    completion_summary: null,
    created_at: '2026-06-11T08:00:00+05:30',
    updated_at: '2026-06-11T11:00:00+05:30',
    completed_at: null,
    logs: [],
  },
  {
    id: 'WO-8297',
    equipment_id: 'OH-CRANE-05',
    title: 'Inspect hoist brake temperature and current',
    description: 'Review hoist current and brake temperature after heavy-lift restriction.',
    status: 'WAPPR',
    priority: 1,
    work_type: 'EM',
    failure_class: 'ELEC',
    problem_code: 'HOISTBRK',
    classification: 'Hoist braking',
    assigned_to: 'Crane Technician',
    supervisor: 'Melt Shop Supervisor',
    due_date: '2026-06-11T17:00:00+05:30',
    recommended_action: 'Plan brake shoe replacement follow-up.',
    follow_up_required: true,
    ai_summary: 'Completed inspection still needs supervisor follow-up.',
    completion_summary: 'Brake temperature normalized after lift restriction.',
    created_at: '2026-06-10T09:00:00+05:30',
    updated_at: '2026-06-11T16:35:00+05:30',
    completed_at: '2026-06-11T16:35:00+05:30',
    logs: [],
  },
  {
    id: 'WO-8275',
    equipment_id: 'HYD-SYS-04',
    title: 'Investigate hydraulic oil temperature rise',
    description: 'Inspect cooler fouling, pump cartridge condition, and pressure pulsation.',
    status: 'WMATL',
    priority: 2,
    work_type: 'PM',
    failure_class: 'HYD',
    problem_code: 'OILTEMP',
    classification: 'Hydraulic temperature',
    assigned_to: 'Hydraulic Technician',
    supervisor: 'Rolling Mill Supervisor',
    due_date: '2026-06-14T10:00:00+05:30',
    recommended_action: 'Reserve pump cartridge assembly and inspect cooler differential temperature.',
    follow_up_required: false,
    ai_summary: 'Hydraulic temperature work is waiting for material coordination.',
    completion_summary: null,
    created_at: '2026-06-11T10:00:00+05:30',
    updated_at: '2026-06-11T10:30:00+05:30',
    completed_at: null,
    logs: [],
  },
]

function userFor(email = 'admin@plant.local') {
  const roles: Record<string, UserRole> = {
    'admin@plant.local': 'admin',
    'maintenance@plant.local': 'maintenance_engineer',
    'technician@plant.local': 'maintenance_technician',
    'supervisor@plant.local': 'maintenance_supervisor',
    'reliability@plant.local': 'reliability_engineer',
    'planner@plant.local': 'planner',
    'operator@plant.local': 'operator',
    'iot-service@plant.local': 'iot_service',
  }
  const role = roles[email] ?? 'admin'
  const displayNames: Record<UserRole, string> = {
    admin: 'Plant Admin',
    maintenance_engineer: 'Maintenance Engineer',
    maintenance_technician: 'Maintenance Technician',
    maintenance_supervisor: 'Maintenance Supervisor',
    reliability_engineer: 'Reliability Engineer',
    planner: 'Maintenance Planner',
    operator: 'Shift Operator',
    iot_service: 'IoT Service Account',
  }
  return {
    id: `USER-${role}`,
    email,
    display_name: displayNames[role],
    role,
    is_active: true,
  }
}

function userFromRequest(init?: RequestInit) {
  const headers = (init?.headers ?? {}) as Record<string, string>
  const authorization = headers.Authorization ?? headers.authorization ?? ''
  const email = authorization.startsWith('Bearer token-') ? authorization.replace('Bearer token-', '') : 'admin@plant.local'
  return userFor(email)
}

async function signIn(email = 'admin@plant.local') {
  if (email !== 'admin@plant.local') {
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } })
  }
  fireEvent.click(await screen.findByRole('button', { name: /sign in/i }))
  await screen.findByText('API connected')
}

beforeEach(() => {
  neoResponseDelayMs = 0
  assistantResponseDelayMs = 0
  window.sessionStorage.clear()
  api.setSession(null)
  api.onUnauthorized(null)
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = input.toString()
      if (url.endsWith('/api/auth/login')) {
        const body = JSON.parse((init?.body as string) ?? '{}')
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: `token-${body.email ?? 'admin'}`,
              token_type: 'bearer',
              expires_in: 28800,
              user: userFor(body.email),
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/auth/me')) {
        return Promise.resolve(new Response(JSON.stringify(userFor()), { status: 200 }))
      }
      if (url.endsWith('/api/auth/logout')) {
        return Promise.resolve(new Response(JSON.stringify({ status: 'logged_out' }), { status: 200 }))
      }
      if (url.endsWith('/api/users')) {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}')
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: 'USER-NEW',
                email: body.email,
                display_name: body.display_name,
                role: body.role,
                is_active: true,
              }),
              { status: 201 },
            ),
          )
        }
        return Promise.resolve(new Response(JSON.stringify([userFor(), userFor('operator@plant.local')]), { status: 200 }))
      }
      if (url.endsWith('/api/users/technicians')) {
        return Promise.resolve(new Response(JSON.stringify([userFor('technician@plant.local')]), { status: 200 }))
      }
      if (url.includes('/api/users/') && url.endsWith('/reset-password')) {
        return Promise.resolve(new Response(JSON.stringify(userFor('operator@plant.local')), { status: 200 }))
      }
      if (url.includes('/api/users/')) {
        return Promise.resolve(new Response(JSON.stringify({ ...userFor('operator@plant.local'), is_active: false }), { status: 200 }))
      }
      if (url.endsWith('/api/dashboard/summary')) {
        return Promise.resolve(new Response(JSON.stringify(dashboard), { status: 200 }))
      }
      if (url.endsWith('/api/neo/chat/stream')) {
        const body = JSON.parse((init?.body as string) ?? '{}')
        if (body.message === 'Format markdown response') {
          const response = {
            answer:
              'To inspect BF-BLOWER-02, follow these steps: ### Safety Checks: 1. **Lockout/Tagout**: Isolate and tag all power sources. 2. **Ventilation**: Confirm safe airflow before access. ### Inspection Steps: - Inspect inlet guide vane response. - Verify actuator calibration.',
            table: null,
            used_live_provider: true,
            provider: 'openai',
          }
          return Promise.resolve(
            neoStreamResponse(response, [
              'To inspect BF-BLOWER-02, follow these steps: ### Safety Checks: 1. **Lockout/Tagout**: Isolate and tag all power sources. ',
              '2. **Ventilation**: Confirm safe airflow before access. ### Inspection Steps: - Inspect inlet guide vane response. - Verify actuator calibration.',
            ]),
          )
        }
        const response = neoStreamResponse({
          answer: 'Neo found work orders that need attention. WO-8304 and WO-8297 require follow-up.',
          table: {
            title: 'Work Orders',
            columns: ['Work order', 'Asset', 'Status', 'Priority'],
            rows: [
              { 'Work order': 'WO-8304', Asset: 'RM-DRIVE-01', Status: 'APPR', Priority: 1 },
              { 'Work order': 'WO-8297', Asset: 'OH-CRANE-05', Status: 'COMP', Priority: 1 },
            ],
          },
          used_live_provider: false,
          provider: 'mock',
        })
        if (neoResponseDelayMs > 0) {
          return new Promise((resolve) => {
            window.setTimeout(() => resolve(response), neoResponseDelayMs)
          })
        }
        return Promise.resolve(response)
      }
      if (url.includes('/api/work-orders/technician-assist/stream')) {
        const response = assistantStreamResponse(
          {
            work_order_id: 'WO-8304',
            next_prompt: 'Smith recommends verifying torque and documenting completion.',
            live_directions: ['Verify torque on bolted connections.', 'Record before and after vibration readings.'],
            recommendations: ['Set problem code LWTQCONNECT.'],
            safety_reminders: ['Apply lockout/tagout.'],
            suggested_problem_code: 'LWTQCONNECT',
            suggested_failure_class: 'MECH',
            completion_summary: 'Connections were tightened to spec.',
            evidence: recommendation.evidence,
            used_live_provider: false,
            provider: 'mock',
          },
          ['Smith recommends verifying torque ', 'and documenting completion.'],
        )
        if (assistantResponseDelayMs > 0) {
          return new Promise((resolve) => {
            window.setTimeout(() => resolve(response), assistantResponseDelayMs)
          })
        }
        return Promise.resolve(response)
      }
      if (url.includes('/api/work-orders/technician-assist')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              work_order_id: 'WO-8304',
              next_prompt: 'Do you observe looseness or damaged insulation?',
              live_directions: ['Verify torque on bolted connections.', 'Record before and after vibration readings.'],
              recommendations: ['Set problem code LWTQCONNECT.'],
              safety_reminders: ['Apply lockout/tagout.'],
              suggested_problem_code: 'LWTQCONNECT',
              suggested_failure_class: 'MECH',
              completion_summary: 'Connections were tightened to spec.',
              evidence: recommendation.evidence,
              used_live_provider: false,
              provider: 'mock',
            }),
            { status: 200 },
          ),
        )
      }
      if (url.includes('/api/work-orders/supervisor-assist/stream')) {
        const response = assistantStreamResponse(
          {
            summary: 'Trinity reviewed 2 work orders and found 2 follow-ups.',
            follow_up_actions: ['Review WO-8297 brake shoe replacement planning.'],
            risks: ['WO-8304 remains priority 1 and APPR.'],
            draft_work_order: null,
            referenced_work_orders: ['WO-8304', 'WO-8297'],
            used_live_provider: false,
            provider: 'mock',
          },
          ['Trinity reviewed 2 work orders ', 'and found 2 follow-ups.'],
        )
        if (assistantResponseDelayMs > 0) {
          return new Promise((resolve) => {
            window.setTimeout(() => resolve(response), assistantResponseDelayMs)
          })
        }
        return Promise.resolve(response)
      }
      if (url.includes('/api/work-orders/supervisor-assist')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              summary: '2 work order(s) reviewed; 2 require follow-up action.',
              follow_up_actions: ['Review WO-8297 brake shoe replacement planning.'],
              risks: ['WO-8304 remains priority 1 and APPR.'],
              draft_work_order: null,
              referenced_work_orders: ['WO-8304', 'WO-8297'],
              used_live_provider: false,
              provider: 'mock',
            }),
            { status: 200 },
          ),
        )
      }
      if (url.includes('/api/work-orders')) {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}')
          return Promise.resolve(
            new Response(JSON.stringify({ ...workOrders[0], ...body, id: 'WO-9001', status: 'WAPPR' }), { status: 201 }),
          )
        }
        if (init?.method === 'PATCH') {
          const body = JSON.parse((init.body as string) ?? '{}')
          const workOrderId = url.match(/\/api\/work-orders\/([^/?]+)/)?.[1]
          const original = workOrders.find((item) => item.id === workOrderId) ?? workOrders[0]
          return Promise.resolve(new Response(JSON.stringify({ ...original, ...body }), { status: 200 }))
        }
        const requestUser = userFromRequest(init)
        const rows = requestUser.role === 'maintenance_technician'
          ? workOrders.filter((order) => order.assigned_to === requestUser.display_name)
          : workOrders
        return Promise.resolve(new Response(JSON.stringify(rows), { status: 200 }))
      }
      if (url.endsWith('/api/streaming/status')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              enabled: false,
              state: 'disabled',
              broker: 'nats',
              stream: 'MW_IOT',
              consumer: 'maintenance-wizard-ingestor',
              subjects: ['steelplant.iot.sensor_readings'],
              processed_count: 0,
              failed_count: 0,
              last_message_timestamp: null,
              last_error: null,
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/diagnose')) {
        return Promise.resolve(new Response(JSON.stringify(recommendation), { status: 200 }))
      }
      if (url.endsWith('/api/ingest/document-file')) {
        return Promise.resolve(new Response(JSON.stringify({ status: 'stored', documents: 1 }), { status: 200 }))
      }
      if (url.endsWith('/api/ingest/documents')) {
        return Promise.resolve(new Response(JSON.stringify({ status: 'stored', documents: 1 }), { status: 200 }))
      }
      if (url.endsWith('/api/ingest/records')) {
        return Promise.resolve(
          new Response(JSON.stringify({ status: 'stored', counts: { alerts: 1, equipment: 0 } }), { status: 200 }),
        )
      }
      if (url.endsWith('/feedback')) {
        return Promise.resolve(new Response(JSON.stringify({ stored: true }), { status: 200 }))
      }
      if (url.endsWith('/api/reports/RM-DRIVE-01/markdown')) {
        return Promise.resolve(new Response('# Maintenance Decision Report: RM-DRIVE-01', { status: 200 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    }),
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
  api.setSession(null)
  api.onUnauthorized(null)
})

describe('Maintenance Wizard dashboard', () => {
  it('renders dashboard metrics, anomalies, and selected asset details', async () => {
    render(<App />)
    await signIn()

    expect(await screen.findByText('API connected')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Assets at risk' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Work queues' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Equipment efficiency' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Neo' })).toBeInTheDocument()
    expect(screen.getByText('Dashboard AI assistant')).toBeInTheDocument()
    expect(screen.getByText('Priority Assets (5)')).toBeInTheDocument()
    const navigation = screen.getByLabelText('Maintenance navigation')
    const quickActions = within(navigation).getByLabelText('Quick actions')
    expect(within(quickActions).getByRole('heading', { name: 'Quick actions' })).toBeInTheDocument()
    expect(within(quickActions).getByRole('button', { name: /create work order/i })).toBeInTheDocument()
    expect(screen.getByText('Melt Shop Overhead Crane')).toBeInTheDocument()
    expect(screen.getByText('Hot Rolling Hydraulic System')).toBeInTheDocument()
    const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText('Hot Strip Mill Main Drive Motor').closest('button')
    if (!assetButton) throw new Error('Missing asset button')
    fireEvent.click(assetButton)
    expect(screen.getByRole('heading', { name: 'Hot Strip Mill Main Drive Motor' })).toBeInTheDocument()
    expect(screen.getByText('Performance insights')).toBeInTheDocument()
    expect(screen.getByText('Maintenance history')).toBeInTheDocument()
    expect(screen.getByText('Primary signal trend')).toBeInTheDocument()
    const diagnoseButton = screen.getByRole('button', { name: 'Diagnose' })
    const engineerQueryHeading = screen.getByRole('heading', { name: 'Engineer Query' })
    const engineerQuestion = screen.getByRole('textbox', { name: 'Engineer question' })
    expect(Boolean(diagnoseButton.compareDocumentPosition(engineerQueryHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(engineerQuestion).toHaveAttribute('rows', '3')
    expect(screen.getByRole('button', { name: 'Ingestion' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Users' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Ingestion file')).not.toBeInTheDocument()
  })

  it('lets Neo update the dashboard center table for read-only users', async () => {
    neoResponseDelayMs = 500
    render(<App />)
    await signIn('operator@plant.local')

    expect(await screen.findByRole('heading', { name: 'Neo' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Ask Neo'), { target: { value: 'Show work orders needing follow-up' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText(/Thinking/)).toBeInTheDocument()
    expect(await screen.findByText('I found 2 rows for Work Orders. The table is updated in the dashboard.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Work Orders' })).toBeInTheDocument()
    const neoResultTable = screen.getByLabelText('Work Orders results table')
    expect(within(neoResultTable).getByText('WO-8304')).toBeInTheDocument()
    expect(within(neoResultTable).getByText('OH-CRANE-05')).toBeInTheDocument()
    const transcript = screen.getByLabelText('Neo chat transcript')
    expect(within(transcript).queryByText('Neo found work orders that need attention. WO-8304 and WO-8297 require follow-up.')).not.toBeInTheDocument()
  })

  it('formats Markdown-like Neo responses into readable sections', async () => {
    render(<App />)
    await signIn()

    fireEvent.change(screen.getByLabelText('Ask Neo'), { target: { value: 'Format markdown response' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    const transcript = screen.getByLabelText('Neo chat transcript')
    expect(await within(transcript).findByRole('heading', { name: 'Safety Checks:' })).toBeInTheDocument()
    expect(within(transcript).getByRole('heading', { name: 'Inspection Steps:' })).toBeInTheDocument()
    expect(within(transcript).getByText('Lockout/Tagout')).toBeInTheDocument()
    expect(within(transcript).getByText(/Isolate and tag all power sources/)).toBeInTheDocument()
    expect(within(transcript).getByText(/Inspect inlet guide vane response/)).toBeInTheDocument()
    expect(transcript.textContent).not.toContain('###')
    expect(transcript.textContent).not.toContain('**')
  })

  it('runs diagnosis and exposes report export action', async () => {
    render(<App />)
    await signIn()

    const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText('Hot Strip Mill Main Drive Motor').closest('button')
    if (!assetButton) throw new Error('Missing asset button')
    fireEvent.click(assetButton)
    fireEvent.click(await screen.findByText('Diagnose'))

    await waitFor(() => {
      expect(screen.getAllByText('Reduce load or schedule controlled shutdown.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Trend the abnormal signal.')).toBeInTheDocument()
    expect(screen.getByText('23 days')).toBeInTheDocument()
    expect(screen.getByText('77%')).toBeInTheDocument()
    expect(screen.getByText('Hot Strip Mill Main Drive Vibration SOP')).toBeInTheDocument()
    const recommendationHeading = screen.getByRole('heading', { name: 'Recommendation' })
    const engineerQueryHeading = screen.getByRole('heading', { name: 'Engineer Query' })
    expect(Boolean(engineerQueryHeading.compareDocumentPosition(recommendationHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(screen.getByRole('button', { name: /export report/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /create work order/i }).length).toBeGreaterThan(0)
  })

  it('stores detailed engineer feedback for learning', async () => {
    render(<App />)
    await signIn()

    const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText('Hot Strip Mill Main Drive Motor').closest('button')
    if (!assetButton) throw new Error('Missing asset button')
    fireEvent.click(assetButton)
    fireEvent.click(await screen.findByText('Diagnose'))
    await screen.findByText('Actual Root Cause')
    fireEvent.change(screen.getByLabelText('Actual Root Cause'), { target: { value: 'Loose foundation bolt resonance' } })
    fireEvent.change(screen.getByLabelText('Action Taken'), { target: { value: 'Retorqued foundation bolts' } })
    fireEvent.change(screen.getByLabelText('Outcome'), { target: { value: 'Vibration normalized' } })
    fireEvent.click(screen.getByText('Correct'))

    await waitFor(() => {
      expect(screen.getByText('corrected feedback stored')).toBeInTheDocument()
    })
    const feedbackCall = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => url.toString().endsWith('/feedback'))
    expect(JSON.parse((feedbackCall?.[1] as RequestInit).body as string)).toMatchObject({
      equipment_id: 'RM-DRIVE-01',
      status: 'corrected',
      actual_root_cause: 'Loose foundation bolt resonance',
      action_taken: 'Retorqued foundation bolts',
      outcome: 'Vibration normalized',
    })
  })

  it('hides role-specific work order assistants from admin users', async () => {
    render(<App />)
    await signIn()

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Orders' }))[0])
    expect(await screen.findByText('WOs with follow up actions')).toBeInTheDocument()
    const centerPane = screen.getByLabelText('Work order center pane')
    const rightPane = screen.getByLabelText('Work order right pane')
    expect(screen.getByText('Work Order 8304')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Smith' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Trinity' })).not.toBeInTheDocument()
    const assistantUnavailable = within(centerPane).getByText('Smith and Trinity are available to technician and supervisor accounts.')
    const workOrdersHeading = screen.getByRole('heading', { name: 'WOs with follow up actions' })
    expect(assistantUnavailable).toBeInTheDocument()
    expect(Boolean(assistantUnavailable.compareDocumentPosition(workOrdersHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(within(rightPane).queryByText('Smith and Trinity are available to technician and supervisor accounts.')).not.toBeInTheDocument()

    expect(screen.getByRole('button', { name: 'Approve WO-8297' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve WO-8275' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve WO-8297' }))
    await screen.findByText('WO-8297 approved')
    const approveCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => url.toString().includes('/api/work-orders/WO-8297') && init?.method === 'PATCH')
    expect(JSON.parse((approveCall?.[1] as RequestInit).body as string)).toEqual({ status: 'APPR' })

    fireEvent.change(screen.getByLabelText('Assign WO-8297'), { target: { value: 'Maintenance Technician' } })
    await screen.findByText('WO-8297 assigned to Maintenance Technician')
    const assignCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => {
        if (!url.toString().includes('/api/work-orders/WO-8297') || init?.method !== 'PATCH') return false
        return JSON.parse((init.body as string) ?? '{}').assigned_to === 'Maintenance Technician'
      })
    expect(JSON.parse((assignCall?.[1] as RequestInit).body as string)).toEqual({ assigned_to: 'Maintenance Technician' })
  })

  it('shows only the technician LLM assistant to technician users', async () => {
    assistantResponseDelayMs = 300
    render(<App />)
    await signIn('technician@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Orders' }))[0])
    expect(await screen.findByText('WOs with follow up actions')).toBeInTheDocument()
    const centerPane = screen.getByLabelText('Work order center pane')
    const rightPane = screen.getByLabelText('Work order right pane')
    const smithHeading = within(centerPane).getByRole('heading', { name: 'Smith' })
    const workOrdersHeading = screen.getByRole('heading', { name: 'WOs with follow up actions' })
    expect(smithHeading).toBeInTheDocument()
    expect(Boolean(smithHeading.compareDocumentPosition(workOrdersHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(within(centerPane).getByText('Technician AI assistant with shared LLM configuration')).toBeInTheDocument()
    expect(within(rightPane).queryByRole('heading', { name: 'Smith' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Trinity' })).not.toBeInTheDocument()
    expect(within(centerPane).getByRole('button', { name: 'WO-8304' })).toBeInTheDocument()
    expect(within(centerPane).queryByRole('button', { name: 'WO-8297' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start WO-8304' }))
    await screen.findByText('WO-8304 started')
    const startCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => url.toString().includes('/api/work-orders/WO-8304') && init?.method === 'PATCH')
    expect(JSON.parse((startCall?.[1] as RequestInit).body as string)).toEqual({ status: 'INPRG' })

    fireEvent.change(screen.getByLabelText('Technician observation'), {
      target: { value: 'Connections 3 and 5 were loose.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Smith technician chat')).getByText('Connections 3 and 5 were loose.')).toBeInTheDocument()
    expect(await within(screen.getByLabelText('Smith technician chat')).findByText(/Thinking/)).toBeInTheDocument()
    expect(await screen.findByText(/Smith recommends verifying torque/)).toBeInTheDocument()
    expect(await screen.findByText('Verify torque on bolted connections.')).toBeInTheDocument()
    expect(screen.getByText(/Connections were tightened to spec./)).toBeInTheDocument()
    expect(screen.getByText('LLM fallback · mock')).toBeInTheDocument()
    const submitCompleted = screen.getByRole('button', { name: 'Submit completed work' })
    const workOrderButton = within(centerPane).getByRole('button', { name: 'WO-8304' })
    expect(Boolean(workOrderButton.compareDocumentPosition(submitCompleted) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
  })

  it('shows only the supervisor LLM assistant to supervisor users', async () => {
    assistantResponseDelayMs = 300
    render(<App />)
    await signIn('supervisor@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Orders' }))[0])
    expect(await screen.findByText('WOs with follow up actions')).toBeInTheDocument()
    const centerPane = screen.getByLabelText('Work order center pane')
    const rightPane = screen.getByLabelText('Work order right pane')
    expect(screen.queryByRole('heading', { name: 'Smith' })).not.toBeInTheDocument()
    const trinityHeading = within(centerPane).getByRole('heading', { name: 'Trinity' })
    const workOrdersHeading = screen.getByRole('heading', { name: 'WOs with follow up actions' })
    expect(trinityHeading).toBeInTheDocument()
    expect(Boolean(trinityHeading.compareDocumentPosition(workOrdersHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(within(centerPane).getByText('Supervisor AI assistant with shared LLM configuration')).toBeInTheDocument()
    expect(within(rightPane).queryByRole('heading', { name: 'Trinity' })).not.toBeInTheDocument()
    expect(screen.getByLabelText('Assign WO-8304')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve WO-8297' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve WO-8275' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Trinity supervisor chat')).getByText('Summarize follow-up actions for completed work orders.')).toBeInTheDocument()
    expect(await within(screen.getByLabelText('Trinity supervisor chat')).findByText(/Thinking/)).toBeInTheDocument()
    expect(await screen.findByText(/Trinity reviewed 2 work orders/)).toBeInTheDocument()
    expect(screen.getByText('Review WO-8297 brake shoe replacement planning.')).toBeInTheDocument()
    expect(screen.getByText('LLM fallback · mock')).toBeInTheDocument()
  })

  it('uploads document files from the ingestion panel', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Ingestion' }))
    expect(await screen.findByText('IoT Stream')).toBeInTheDocument()
    expect(screen.getByText('MW_IOT')).toBeInTheDocument()
    const file = new File(['Inspect bearing housing when vibration increases.'], 'uploaded_sop.txt', { type: 'text/plain' })
    fireEvent.change(await screen.findByLabelText('Ingestion file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /upload/i }))

    await waitFor(() => {
      expect(screen.getByText(/Stored 1 document and extracted/)).toBeInTheDocument()
    })
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/ingest/document-file',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
  })

  it('uploads every bundled ingestion sample file with the intended source type and asset', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Ingestion' }))
    expect(await screen.findByText('IoT Stream')).toBeInTheDocument()

    for (const sample of sampleFiles) {
      const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText(sample.assetName).closest('button')
      if (!assetButton) {
        throw new Error(`Missing asset button for ${sample.assetName}`)
      }
      fireEvent.click(assetButton)
      fireEvent.click(screen.getByRole('button', { name: 'Ingestion' }))
      fireEvent.change(screen.getByLabelText('Source'), { target: { value: sample.sourceType } })
      const content = readFileSync(sample.path, 'utf8')
      const file = new File([content], sample.fileName, { type: sample.mimeType })
      fireEvent.change(screen.getByLabelText('Ingestion file'), { target: { files: [file] } })
      fireEvent.click(screen.getByRole('button', { name: /upload/i }))

      await waitFor(() => {
        expect(screen.getByText(/Stored 1 document and extracted/)).toBeInTheDocument()
      })

      const uploadCall = [...vi.mocked(fetch).mock.calls]
        .reverse()
        .find(([url]) => url.toString().endsWith('/api/ingest/document-file'))
      const body = uploadCall?.[1]?.body as FormData
      expect(body.get('source_type')).toBe(sample.sourceType)
      expect(body.get('equipment_id')).toBe(sample.equipmentId)
      expect((body.get('file') as File).name).toBe(sample.fileName)
    }
  })

  it('imports document JSON from the ingestion panel', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Ingestion' }))
    fireEvent.change(await screen.findByLabelText('Ingestion JSON'), {
      target: {
        value:
          '{"documents":[{"id":"DOC-UI","source_type":"sop","equipment_id":"RM-DRIVE-01","title":"UI SOP","content":"Check vibration."}]}',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /import json/i }))

    await waitFor(() => {
      expect(screen.getByText(/Stored 1 document and extracted/)).toBeInTheDocument()
    })
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/ingest/documents',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('hides restricted actions for operators', async () => {
    render(<App />)
    await signIn('operator@plant.local')

    expect(screen.getByText('Shift Operator')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Ingestion' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Users' })).not.toBeInTheDocument()
    expect(screen.queryByText('Diagnose')).not.toBeInTheDocument()
    expect(screen.queryByText('Engineer Query')).not.toBeInTheDocument()
  })

  it('lets admins open the users view and create a user', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Users' }))
    expect(await screen.findByText('Shift Operator')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'new.operator@plant.local' } })
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'New Operator' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'NewOperator123!' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.getByText('User created')).toBeInTheDocument()
    })
  })

  it('opens password reset in a dialog instead of inline user rows', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Users' }))
    expect(await screen.findByText('Shift Operator')).toBeInTheDocument()

    expect(screen.queryByLabelText('New Password')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Reset' })[0])

    expect(await screen.findByRole('dialog', { name: 'Reset Password' })).toBeInTheDocument()
    expect(screen.getByLabelText('New Password')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog', { name: 'Reset Password' })).not.toBeInTheDocument()
  })
})
