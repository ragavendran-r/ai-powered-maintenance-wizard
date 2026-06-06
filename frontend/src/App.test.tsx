import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api, type UserRole } from './services/api'

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
  report_summary: 'Critical risk with estimated RUL of 23 days.',
}

function userFor(email = 'admin@plant.local') {
  const roles: Record<string, UserRole> = {
    'admin@plant.local': 'admin',
    'maintenance@plant.local': 'maintenance_engineer',
    'reliability@plant.local': 'reliability_engineer',
    'planner@plant.local': 'planner',
    'operator@plant.local': 'operator',
    'iot-service@plant.local': 'iot_service',
  }
  const role = roles[email] ?? 'admin'
  return {
    id: `USER-${role}`,
    email,
    display_name: role === 'operator' ? 'Shift Operator' : 'Plant Admin',
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
    expect(screen.getByRole('heading', { name: 'Hot Strip Mill Main Drive Motor' })).toBeInTheDocument()
    expect(screen.getByText('Priority Assets (5)')).toBeInTheDocument()
    expect(screen.getByText('Melt Shop Overhead Crane')).toBeInTheDocument()
    expect(screen.getByText('Hot Rolling Hydraulic System')).toBeInTheDocument()
    expect(screen.getByText('Sensor Anomalies')).toBeInTheDocument()
    expect(screen.getByText('drive end vibration')).toBeInTheDocument()
    expect(screen.getByText('z 8.35 · baseline 5.24 mm/s')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ingestion' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Users' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Ingestion file')).not.toBeInTheDocument()
  })

  it('runs diagnosis and exposes report export action', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByText('Diagnose'))

    await waitFor(() => {
      expect(screen.getByText('Reduce load or schedule controlled shutdown.')).toBeInTheDocument()
    })
    expect(screen.getByText('Bearing wear')).toBeInTheDocument()
    expect(screen.getByText('Trend the abnormal signal.')).toBeInTheDocument()
    expect(screen.getByText('Review Drive end spherical roller bearing: 0 on hand, 21 day lead time.')).toBeInTheDocument()
    expect(screen.getByText('23 days')).toBeInTheDocument()
    expect(screen.getByText('77%')).toBeInTheDocument()
    expect(screen.getByText('corrected recommendation feedback; actual root cause: Loose foundation bolt resonance')).toBeInTheDocument()
    expect(screen.getByText('Hot Strip Mill Main Drive Vibration SOP')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export report/i })).toBeInTheDocument()
  })

  it('stores detailed engineer feedback for learning', async () => {
    render(<App />)
    await signIn()

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
      expect(screen.getByText('Stored 1 document')).toBeInTheDocument()
    })
    expect(fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/ingest/document-file',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
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
      expect(screen.getByText('Stored 1 document')).toBeInTheDocument()
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
})
