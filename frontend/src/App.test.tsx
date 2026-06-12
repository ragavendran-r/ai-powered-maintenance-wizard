import { readFileSync } from 'node:fs'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api, type UserRole } from './services/api'

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
    status: 'INPRG',
    priority: 1,
    work_type: 'CM',
    failure_class: 'MECH',
    problem_code: 'BRGVIB',
    classification: 'Bearing vibration',
    assigned_to: 'Maintenance Engineer',
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
    status: 'COMP',
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

async function signIn(email = 'admin@plant.local') {
  if (email !== 'admin@plant.local') {
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } })
  }
  fireEvent.click(await screen.findByRole('button', { name: /sign in/i }))
  await screen.findByText('API connected')
}

beforeEach(() => {
  neoResponseDelayMs = 0
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
      if (url.includes('/api/users/') && url.endsWith('/reset-password')) {
        return Promise.resolve(new Response(JSON.stringify(userFor('operator@plant.local')), { status: 200 }))
      }
      if (url.includes('/api/users/')) {
        return Promise.resolve(new Response(JSON.stringify({ ...userFor('operator@plant.local'), is_active: false }), { status: 200 }))
      }
      if (url.endsWith('/api/dashboard/summary')) {
        return Promise.resolve(new Response(JSON.stringify(dashboard), { status: 200 }))
      }
      if (url.endsWith('/api/neo/chat')) {
        const response = new Response(
          JSON.stringify({
            answer: 'Neo found work orders that need attention. WO-8304 and WO-8297 require follow-up.',
            table: {
              title: 'Work Orders',
              columns: ['Work order', 'Asset', 'Status', 'Priority'],
              rows: [
                { 'Work order': 'WO-8304', Asset: 'RM-DRIVE-01', Status: 'INPRG', Priority: 1 },
                { 'Work order': 'WO-8297', Asset: 'OH-CRANE-05', Status: 'COMP', Priority: 1 },
              ],
            },
            used_live_provider: false,
            provider: 'mock',
          }),
          { status: 200 },
        )
        if (neoResponseDelayMs > 0) {
          return new Promise((resolve) => {
            window.setTimeout(() => resolve(response), neoResponseDelayMs)
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
      if (url.includes('/api/work-orders/supervisor-assist')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              summary: '2 work order(s) reviewed; 2 require follow-up action.',
              follow_up_actions: ['Review WO-8297 brake shoe replacement planning.'],
              risks: ['WO-8304 remains priority 1 and INPRG.'],
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
          return Promise.resolve(new Response(JSON.stringify({ ...workOrders[0], ...body }), { status: 200 }))
        }
        return Promise.resolve(new Response(JSON.stringify(workOrders), { status: 200 }))
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
    expect(screen.getByText('Work Order 8304')).toBeInTheDocument()
    expect(screen.queryByText('Technician AI Assistant')).not.toBeInTheDocument()
    expect(screen.queryByText('Supervisor AI Assistant')).not.toBeInTheDocument()
    expect(screen.getByText('Role-specific AI assistants are available to technician and supervisor accounts.')).toBeInTheDocument()
  })

  it('shows only the technician LLM assistant to technician users', async () => {
    render(<App />)
    await signIn('technician@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Orders' }))[0])
    expect(await screen.findByText('WOs with follow up actions')).toBeInTheDocument()
    expect(screen.getByText('Technician AI Assistant')).toBeInTheDocument()
    expect(screen.getByText('LLM work-order guidance for assigned technicians')).toBeInTheDocument()
    expect(screen.queryByText('Supervisor AI Assistant')).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Technician observation'), {
      target: { value: 'Connections 3 and 5 were loose.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Technician assistant chat')).getByText('Connections 3 and 5 were loose.')).toBeInTheDocument()
    expect(await screen.findByText('Verify torque on bolted connections.')).toBeInTheDocument()
    expect(screen.getByText(/Connections were tightened to spec./)).toBeInTheDocument()
    expect(screen.getByText('LLM fallback · mock')).toBeInTheDocument()
  })

  it('shows only the supervisor LLM assistant to supervisor users', async () => {
    render(<App />)
    await signIn('supervisor@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Orders' }))[0])
    expect(await screen.findByText('WOs with follow up actions')).toBeInTheDocument()
    expect(screen.queryByText('Technician AI Assistant')).not.toBeInTheDocument()
    expect(screen.getByText('Supervisor AI Assistant')).toBeInTheDocument()
    expect(screen.getByText('LLM follow-up review for maintenance supervisors')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Supervisor assistant chat')).getByText('Summarize follow-up actions for completed work orders.')).toBeInTheDocument()
    expect(await screen.findByText('2 work order(s) reviewed; 2 require follow-up action.')).toBeInTheDocument()
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
    fireEvent.click(screen.getByRole('button', { name: /create/i }))

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
