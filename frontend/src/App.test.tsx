import { readFileSync } from 'node:fs'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { api, type AssistantStreamEvent, type AssetReliabilityPredictionStreamEvent, type DiagnosisStreamEvent, type NeoChatResponse, type NeoStreamEvent, type PmPlan, type PmPlanDraftResponse, type PmPlanDraftStreamEvent, type PmTemplate, type PredictionResponse, type RcaMorpheusDraftResponse, type RcaMorpheusDraftStreamEvent, type Recommendation, type UserRole, type WorkOrder } from './services/api'
import { StatusTimeline, TechnicianExecutionCard } from './sharedComponents'

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
let logoutResponseDelayMs = 0
let maintenanceInsightsDelayMs = 0
let ingestionResponseDelayMs = 0
let learningJudgeDelayMs = 0
let supervisorAssistantRequests: Array<{ work_order_id?: string; queue_name?: string; question?: string }> = []

it('shows waiting for material before in progress in the work order workflow', () => {
  render(<StatusTimeline status="WMATL" />)

  const timeline = screen.getByLabelText('Work order status')
  const approved = within(timeline).getByText('Approved')
  const material = within(timeline).getByText('Material')
  const inProgress = within(timeline).getByText('Progress')
  const completed = within(timeline).getByText('Complete')

  expect(Boolean(approved.compareDocumentPosition(material) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
  expect(Boolean(material.compareDocumentPosition(inProgress) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
  expect(Boolean(inProgress.compareDocumentPosition(completed) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
})

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

function delayedResponse(response: Response, init: RequestInit | undefined, delayMs: number) {
  const signal = init?.signal
  return new Promise<Response>((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException('Aborted', 'AbortError'))
      return
    }
    const timeoutId = window.setTimeout(() => {
      signal?.removeEventListener('abort', onAbort)
      resolve(response)
    }, delayMs)
    function onAbort() {
      window.clearTimeout(timeoutId)
      signal?.removeEventListener('abort', onAbort)
      reject(new DOMException('Aborted', 'AbortError'))
    }
    signal?.addEventListener('abort', onAbort, { once: true })
  })
}

function reliabilityPredictionStreamResponse(prediction: PredictionResponse) {
  const answer = '### Failure Prediction\n- RM-DRIVE-01 has a high failure risk at 77% with 23 days estimated RUL.\n### Next Actions\n- Inspect drive-end bearing housing and lubrication.'
  const events: AssetReliabilityPredictionStreamEvent[] = [
    { type: 'meta', provider: 'openai', used_live_provider: true },
    { type: 'token', content: answer },
    { type: 'done', answer, prediction, provider: 'openai', used_live_provider: true },
  ]
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function diagnosisStreamResponse(nextRecommendation: Recommendation) {
  const events: DiagnosisStreamEvent[] = [
    { type: 'meta', provider: 'openai', used_live_provider: true },
    { type: 'token', content: 'Morpheus is retrieving recent evidence and asset health context.' },
    { type: 'token', content: 'Morpheus is checking predictive risk and retrieved maintenance knowledge.' },
    { type: 'done', recommendation: nextRecommendation },
  ]
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function rcaDraftStreamResponse(response: RcaMorpheusDraftResponse) {
  const events: RcaMorpheusDraftStreamEvent[] = [
    { type: 'meta', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### Probable Cause\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- Drive-end bearing looseness remains the leading candidate.\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### Fishbone\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- Contaminants/Buildup:\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- Seal flush strainer restriction (Primary cause)\n', provider: 'openai', used_live_provider: true },
    { type: 'done', response },
  ]
  return new Response(events.map((event) => `data: ${JSON.stringify(event)}\n\n`).join(''), {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  })
}

function pmDraftStreamResponse(response: PmPlanDraftResponse) {
  const events: PmPlanDraftStreamEvent[] = [
    { type: 'meta', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### PM Plan\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: 'Main drive proactive PM plan\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### Monitoring Thresholds\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- drive_end_vibration >= 7.1 mm/s\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '### Generated Task List\n', provider: 'openai', used_live_provider: true },
    { type: 'token', content: '- Inspect bearing condition and coupling alignment.\n', provider: 'openai', used_live_provider: true },
    { type: 'done', response },
  ]
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

const maintenanceInsights = {
  generated_at: '2026-06-14T12:00:00+00:00',
  scope_equipment_id: null,
  assets_reviewed: 2,
  structured_reports: [
    {
      id: 'MR-RM-DRIVE-01',
      equipment_id: 'RM-DRIVE-01',
      equipment_name: 'Hot Strip Mill Main Drive Motor',
      area: 'Hot Rolling Mill',
      risk_level: 'critical',
      health_score: 10,
      failure_probability: 0.77,
      remaining_useful_life_days: 23,
      confidence_band: '12-34 days',
      active_alert_count: 1,
      open_work_order_count: 1,
      report_summary: 'Hot Strip Mill Main Drive Motor is at critical risk with 10% health.',
      probable_causes: ['Drive end vibration abnormality linked to bearing wear.'],
      immediate_actions: ['Resolve material blocker before intrusive execution.', 'Confirm current readings against thresholds.'],
      planned_actions: ['Plan corrective work within the RUL confidence window.'],
      spares_strategy: ['Check Drive end spherical roller bearing availability.'],
      evidence: ['ALT-1001: Drive end vibration exceeds trip advisory threshold', 'WO-8304: Inspect main drive bearing vibration (APPR)'],
      recommended_owner: 'Maintenance Supervisor',
    },
    {
      id: 'MR-BF-BLOWER-02',
      equipment_id: 'BF-BLOWER-02',
      equipment_name: 'Blast Furnace Combustion Air Blower',
      area: 'Blast Furnace',
      risk_level: 'high',
      health_score: 35,
      failure_probability: 0.61,
      remaining_useful_life_days: 38,
      confidence_band: '20-55 days',
      active_alert_count: 1,
      open_work_order_count: 1,
      report_summary: 'Blast Furnace Combustion Air Blower has pressure variance risk.',
      probable_causes: ['Inlet guide vane actuator response drift.'],
      immediate_actions: ['Stroke-test the inlet guide vane actuator.'],
      planned_actions: ['Schedule actuator follow-up if response remains slow.'],
      spares_strategy: ['Check inlet guide vane actuator availability.'],
      evidence: ['ALT-2001: outlet pressure variance breached baseline'],
      recommended_owner: 'Maintenance Supervisor',
    },
  ],
  abnormal_alert_reports: [
    {
      alert_id: 'ALT-1001',
      equipment_id: 'RM-DRIVE-01',
      equipment_name: 'Hot Strip Mill Main Drive Motor',
      timestamp: '2026-06-06T08:15:00+05:30',
      signal: 'drive_end_vibration',
      severity: 'critical',
      value: 9.8,
      unit: 'mm/s',
      threshold: 7.1,
      threshold_delta: 2.7,
      abnormality: 'drive_end_vibration is 2.7mm/s above threshold.',
      decision: 'Escalate for same-shift maintenance review.',
      recommended_actions: ['Verify the live reading.', 'Inspect the related component.'],
      evidence: ['Drive end vibration exceeds trip advisory threshold'],
    },
  ],
  decision_summaries: [
    {
      audience: 'engineer',
      title: 'Engineer Maintenance Decision Summary',
      summary: '2 asset(s) need engineering review.',
      decisions: ['Prioritize Hot Strip Mill Main Drive Motor.'],
      risks: ['RM-DRIVE-01: RUL 23 days.'],
      next_actions: ['Validate top probable causes against field readings.'],
      referenced_equipment: ['RM-DRIVE-01'],
      referenced_alerts: ['ALT-1001'],
      referenced_work_orders: [],
    },
    {
      audience: 'supervisor',
      title: 'Supervisor Maintenance Decision Summary',
      summary: '1 high-risk asset has open work.',
      decisions: ['Confirm owner and execution window for Hot Strip Mill Main Drive Motor.'],
      risks: ['RM-DRIVE-01 has active abnormal alerts.'],
      next_actions: ['Approve or unblock waiting work orders.'],
      referenced_equipment: ['RM-DRIVE-01'],
      referenced_alerts: ['ALT-1001'],
      referenced_work_orders: ['WO-8304'],
    },
  ],
  maintenance_log_entries: [
    {
      equipment_id: 'RM-DRIVE-01',
      equipment_name: 'Hot Strip Mill Main Drive Motor',
      timestamp: '2026-06-14T12:00:00+00:00',
      entry_type: 'generated_insight',
      content: 'Generated maintenance insight for Hot Strip Mill Main Drive Motor.',
      source_ids: ['MR-RM-DRIVE-01', 'ALT-1001'],
    },
  ],
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
    assigned_to: 'Vinoth',
    supervisor: 'Dhruv',
    due_date: '2026-06-12T18:00:00+05:30',
    planning_status: 'planned',
    planned_start: '2026-06-12T14:00:00+05:30',
    planned_end: '2026-06-12T18:00:00+05:30',
    outage_window: 'Finishing stand load-reduction window',
    material_readiness: 'ready',
    material_blocker_status: 'reserved',
    material_blocker_note: 'Bearing inspection kit is staged for the planned window.',
    dispatch_notes: 'Stage vibration tools and confirm bearing spare status.',
    dispatched_at: null,
    recommended_action: 'Reduce load if vibration persists and verify coupling alignment.',
    follow_up_required: true,
    ai_summary: 'High-risk drive vibration needs mechanical inspection before restart.',
    completion_summary: null,
    created_at: '2026-06-11T08:00:00+05:30',
    updated_at: '2026-06-11T11:00:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [
      {
        id: 1,
        work_order_id: 'WO-8304',
        spare_id: 'SP-001',
        spare_name: 'Drive end spherical roller bearing',
        required_qty: 1,
        reserved_qty: 1,
        available_qty: 1,
        reorder_requested: false,
        procurement_status: 'not_requested',
        procurement_lead_time_days: 21,
        expected_available_date: null,
        substitute_spare_id: 'SP-002',
        substitute_name: 'High-temperature coupling grease',
        blocker_status: 'reserved',
        blocker_note: 'Reserved for planned inspection window.',
      },
    ],
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
    planning_status: 'unscheduled',
    planned_start: null,
    planned_end: null,
    outage_window: null,
    material_readiness: 'unknown',
    material_blocker_status: 'not_required',
    material_blocker_note: null,
    dispatch_notes: null,
    dispatched_at: null,
    recommended_action: 'Plan brake shoe replacement follow-up.',
    follow_up_required: true,
    ai_summary: 'Completed inspection still needs supervisor follow-up.',
    completion_summary: 'Brake temperature normalized after lift restriction.',
    created_at: '2026-06-10T09:00:00+05:30',
    updated_at: '2026-06-11T16:35:00+05:30',
    completed_at: '2026-06-11T16:35:00+05:30',
    logs: [],
    spare_reservations: [],
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
    planning_status: 'planned',
    planned_start: '2026-06-14T08:00:00+05:30',
    planned_end: '2026-06-14T10:00:00+05:30',
    outage_window: 'Morning roll-gap correction maintenance window',
    material_readiness: 'pending',
    material_blocker_status: 'waiting_procurement',
    material_blocker_note: 'Pump cartridge is on order; seal kit can support limited inspection.',
    dispatch_notes: 'Pump cartridge assembly reservation is pending.',
    dispatched_at: null,
    recommended_action: 'Reserve pump cartridge assembly and inspect cooler differential temperature.',
    follow_up_required: false,
    ai_summary: 'Hydraulic temperature work is waiting for material coordination.',
    completion_summary: null,
    created_at: '2026-06-11T10:00:00+05:30',
    updated_at: '2026-06-11T10:30:00+05:30',
    completed_at: null,
    logs: [],
    spare_reservations: [
      {
        id: 2,
        work_order_id: 'WO-8275',
        spare_id: 'SP-004',
        spare_name: 'Hydraulic pump cartridge assembly',
        required_qty: 1,
        reserved_qty: 0,
        available_qty: 0,
        reorder_requested: true,
        procurement_status: 'ordered',
        procurement_lead_time_days: 18,
        expected_available_date: '2026-07-02',
        substitute_spare_id: 'SP-005',
        substitute_name: 'Servo valve seal kit',
        blocker_status: 'waiting_procurement',
        blocker_note: 'Procurement lead time blocks pump replacement.',
      },
    ],
  },
]

let apiWorkOrders: WorkOrder[] = workOrders as WorkOrder[]

const pmTemplates: PmTemplate[] = [
  {
    id: 'PMT-RM-DRIVE-BEARING',
    equipment_id: 'RM-DRIVE-01',
    title: 'Drive bearing and coupling health PM',
    description: 'Recurring vibration, temperature, lubrication, and coupling inspection.',
    cadence_days: 14,
    work_type: 'PM',
    task_list: ['Trend drive-end vibration.', 'Inspect coupling alignment.'],
    thresholds: ['drive_end_vibration >= 7.1 mm/s'],
    source: 'sop',
    created_at: '2026-06-14T09:00:00+05:30',
    updated_at: '2026-06-14T09:00:00+05:30',
  },
]

const generatedPmPlan: PmPlan = {
  id: 'PM-7001',
  equipment_id: 'RM-DRIVE-01',
  template_id: 'PMT-RM-DRIVE-BEARING',
  title: 'Main drive proactive PM plan',
  status: 'draft',
  cadence_days: 14,
  next_due_date: '2026-06-18T08:00:00+05:30',
  trigger: {
    type: 'risk_prediction',
    metric_key: 'drive_end_vibration',
    operator: '>=',
    threshold: 7.1,
    unit: 'mm/s',
    description: 'Generate planned PM when vibration risk remains high or crosses 7.1 mm/s.',
  },
  thresholds: ['drive_end_vibration >= 7.1 mm/s'],
  tasks: [
    {
      id: 'TASK-1',
      sequence: 1,
      task: 'Inspect drive-end bearing housing and coupling alignment.',
      owner_role: 'Maintenance Technician',
      estimated_minutes: 45,
      safety_note: 'Apply LOTO before inspection.',
    },
  ],
  smith_steps: ['Confirm LOTO and permits.', 'Inspect drive-end bearing housing and coupling alignment.'],
  spares_strategy: ['Check Drive end spherical roller bearing availability.'],
  evidence: recommendation.evidence,
  adjustment_notes: ['Adjust cadence using accepted feedback after repeated vibration findings.'],
  source: 'deterministic',
  generated_by: 'morpheus',
  used_live_provider: false,
  provider: 'mock',
  converted_work_order_id: null,
  created_at: '2026-06-14T09:05:00+05:30',
  updated_at: '2026-06-14T09:05:00+05:30',
}

const existingPmPlan: PmPlan = {
  ...generatedPmPlan,
  id: 'PM-6999',
  title: 'Existing blower PM plan',
  equipment_id: 'BF-BLOWER-02',
  status: 'active',
  next_due_date: '2026-06-20T08:00:00+05:30',
  trigger: {
    ...generatedPmPlan.trigger,
    metric_key: 'outlet_pressure_variance',
    description: 'Maintain blower pressure stability before the next furnace ramp.',
  },
  thresholds: ['outlet_pressure_variance <= 10%'],
  converted_work_order_id: null,
}

let apiPmPlans: PmPlan[] = [existingPmPlan]

const rcaCase = {
  id: 'RCA-9001',
  equipment_id: 'RM-DRIVE-01',
  work_order_id: 'WO-8304',
  title: 'Drive-end vibration root cause review',
  status: 'investigating',
  severity: 'critical',
  problem_statement: 'Critical drive-end vibration continues while the bearing spare is unavailable.',
  symptoms: ['Drive-end vibration exceeded threshold.', 'Hotspots and looseness were observed.'],
  hypotheses: [
    {
      id: 'HYP-1',
      cause: 'Drive-end bearing wear or coupling looseness under load',
      confidence: 0.68,
      evidence: ['WO-8304', 'Prior vibration alert'],
      missing_checks: ['Bearing temperature trend', 'Coupling alignment readings'],
      status: 'candidate',
    },
  ],
  why_chain: [
    'Why did vibration exceed threshold? The drive-end rotating assembly is unstable under load.',
    'Why is the assembly unstable? Bearing condition or coupling alignment has not been isolated.',
  ],
  fishbone: {
    Machine: ['Drive-end bearing', 'Coupling alignment'],
    Material: ['Drive end spherical roller bearing availability'],
  },
  evidence_timeline: [
    {
      id: 'EV-1',
      timestamp: '2026-06-12T14:00:00+05:30',
      source_type: 'work_order',
      source_id: 'WO-8304',
      title: 'Work order blocked by material',
      summary: 'Bearing spare availability must be confirmed before intrusive work.',
      relevance: 'Primary work order under RCA review.',
    },
  ],
  corrective_actions: [
    {
      id: 'CA-1',
      action: 'Procure drive-end bearing and reserve installation window.',
      owner: 'Planner',
      due_date: '2026-07-03',
      status: 'approved',
      verification: 'Bearing received and reserved against WO-8304.',
    },
  ],
  closure_review: null,
  probable_cause: 'Drive-end bearing wear or coupling looseness under load',
  confidence: 0.68,
  missing_checks: ['Bearing temperature trend', 'Coupling alignment readings'],
  morpheus_summary: 'Morpheus links the vibration event to bearing and coupling hypotheses pending missing checks.',
  used_live_provider: true,
  provider: 'openai',
  created_at: '2026-06-12T14:00:00+05:30',
  updated_at: '2026-06-12T15:00:00+05:30',
  closed_at: null,
}

it('shows material-blocked approved work orders as waiting for material and locks start', () => {
  const blockedWorkOrder: WorkOrder = {
    ...(workOrders[0] as WorkOrder),
    status: 'APPR',
    material_readiness: 'blocked',
    material_blocker_status: 'blocked',
    material_blocker_note: 'Drive end bearing is out of stock.',
    spare_reservations: [
      {
        ...(workOrders[0].spare_reservations[0]),
        reserved_qty: 0,
        available_qty: 0,
        procurement_status: 'requested',
        expected_available_date: '2026-07-03',
        blocker_status: 'blocked',
      },
    ],
  }

  render(
    <TechnicianExecutionCard
      assistant={null}
      isLoading={false}
      onComplete={vi.fn()}
      onStart={vi.fn()}
      workOrder={blockedWorkOrder}
    />,
  )

  const workflow = screen.getByLabelText('Technician execution workflow')
  expect(within(workflow).getByText('Waiting for material')).toBeInTheDocument()
  expect(within(workflow).getByText('Execution is blocked until required parts or consumables are available.')).toBeInTheDocument()
  expect(within(workflow).getByText(/Drive end spherical roller bearing is not ready/)).toBeInTheDocument()
  expect(within(workflow).getByRole('button', { name: 'Start work' })).toBeDisabled()
})

const assets = [
  {
    id: 'RM-DRIVE-01',
    name: 'Hot Strip Mill Main Drive Motor',
    asset_type: 'AC main drive motor',
    area: 'Hot Rolling Mill',
    process: 'Finishing stand drive',
    location_code: 'HSM-FS-01',
    location_name: 'Hot strip mill finishing stand F1',
    criticality: 5,
    status: 'degraded',
    health_score: 0,
    risk_level: 'critical',
    active_alerts: 2,
    open_work_orders: 1,
    supervisor: 'Dhruv',
    last_updated: '2026-06-12T09:10:00+05:30',
  },
  {
    id: 'BF-BLOWER-02',
    name: 'Blast Furnace Combustion Air Blower',
    asset_type: 'Combustion air blower',
    area: 'Blast Furnace',
    process: 'Combustion air supply',
    location_code: 'BF-STOVE-02',
    location_name: 'Blast furnace stove house blower bay',
    criticality: 5,
    status: 'watch',
    health_score: 29,
    risk_level: 'high',
    active_alerts: 1,
    open_work_orders: 1,
    supervisor: 'Blast Furnace Supervisor',
    last_updated: '2026-06-12T08:40:00+05:30',
  },
]

const assetDetail = {
  profile: {
    equipment_id: 'RM-DRIVE-01',
    name: 'Hot Strip Mill Main Drive Motor',
    area: 'Hot Rolling Mill',
    process: 'Finishing stand drive',
    criticality: 5,
    status: 'degraded',
    asset_type: 'AC main drive motor',
    location_code: 'HSM-FS-01',
    location_name: 'Hot strip mill finishing stand F1',
    parent_system: 'Hot rolling mill power train',
    manufacturer: 'Bharat Heavy Electricals',
    model: 'MDR-7800',
    serial_number: 'RM01-2017-044',
    installed_at: '2017-09-14',
    owner_team: 'Rolling maintenance',
    supervisor: 'Dhruv',
    description: 'Main finishing stand drive motor supporting high-torque strip rolling campaigns.',
    last_updated: '2026-06-12T09:10:00+05:30',
  },
  health: dashboard.highest_risk_equipment[0],
  metrics: [
    {
      id: 'AMS-RM-HEALTH',
      equipment_id: 'RM-DRIVE-01',
      metric_key: 'health',
      label: 'Health',
      value: 10,
      unit: '%',
      target_value: 80,
      status: 'under_target',
      trend: 'down',
      detail: 'Health is constrained by vibration, bearing temperature, and bearing spare availability.',
      captured_at: '2026-06-12T09:10:00+05:30',
      sort_order: 1,
    },
    {
      id: 'AMS-RM-EFF',
      equipment_id: 'RM-DRIVE-01',
      metric_key: 'efficiency',
      label: 'Efficiency',
      value: 68,
      unit: '%',
      target_value: 82,
      status: 'under_target',
      trend: 'down',
      detail: 'Mill drive load was reduced after vibration exceeded the advisory threshold.',
      captured_at: '2026-06-12T09:10:00+05:30',
      sort_order: 2,
    },
    {
      id: 'AMS-RM-RISK',
      equipment_id: 'RM-DRIVE-01',
      metric_key: 'risk',
      label: 'Risk',
      value: 90,
      unit: '%',
      target_value: 40,
      status: 'over_target',
      trend: 'up',
      detail: 'Risk combines critical vibration, temperature trend, and unavailable bearing spare.',
      captured_at: '2026-06-12T09:10:00+05:30',
      sort_order: 3,
    },
  ],
  recommendations: [
    {
      id: 'AR-RM-001',
      equipment_id: 'RM-DRIVE-01',
      action_type: 'inspection',
      title: 'Bearing housing inspection',
      description: 'Verify drive-end bearing housing temperature, looseness, lubrication condition, and vibration after load reduction.',
      priority: 1,
      source: 'asset_detail_seed',
      created_at: '2026-06-12T09:10:00+05:30',
      sort_order: 1,
    },
  ],
  maintenance_events: [
    {
      id: 'ME-1001',
      equipment_id: 'RM-DRIVE-01',
      date: '2026-05-12T09:00:00+05:30',
      issue: 'Drive-end vibration recurrence',
      root_cause: 'Bearing wear',
      action: 'Inspected bearing housing and coupling alignment.',
      downtime_hours: 6,
    },
  ],
  work_orders: [workOrders[0]],
  subsystems: [
    {
      id: 'AS-RM-001',
      equipment_id: 'RM-DRIVE-01',
      name: 'Drive train and coupling',
      component: 'Flexible coupling and guard',
      condition: 'watch',
      detail: 'Coupling alignment must be checked because vibration rose under rolling load.',
      sort_order: 1,
    },
  ],
  reliability_metrics: [
    {
      id: 'ARM-RM-001',
      equipment_id: 'RM-DRIVE-01',
      metric_name: 'MTBF',
      value: 96,
      unit: 'days',
      target_value: 180,
      status: 'under_target',
      trend: 'down',
      detail: 'Bearing and alignment events reduced mean time between failures.',
      sort_order: 1,
    },
  ],
  performance_charts: [
    {
      signal: 'drive_end_vibration',
      title: 'Drive End Vibration',
      unit: 'mm/s',
      points: [
        { timestamp: '2026-06-06T07:00:00+05:30', value: 4.6, threshold: 7.1 },
        { timestamp: '2026-06-06T08:15:00+05:30', value: 9.8, threshold: 7.1 },
      ],
    },
  ],
  documents: [
    {
      id: 'DOC-RM-SOP-01',
      source_type: 'sop',
      equipment_id: 'RM-DRIVE-01',
      title: 'Hot Strip Mill Main Drive Vibration SOP',
      excerpt: 'Inspect bearing housing temperature and coupling alignment.',
    },
    {
      id: 'DOC-RM-LOG-03',
      source_type: 'log',
      equipment_id: 'RM-DRIVE-01',
      title: 'Main Drive Vibration Shift Log',
      excerpt: 'Shift log: vibration increased after finishing stand load rose.',
    },
  ],
  knowledge: recommendation.evidence,
  prediction: {
    equipment_id: 'RM-DRIVE-01',
    risk_level: 'critical',
    failure_probability: 0.77,
    remaining_useful_life_days: 23,
    confidence_interval: {
      lower_probability: 0.68,
      upper_probability: 0.84,
      lower_rul_days: 17,
      upper_rul_days: 29,
      confidence_level: 0.8,
      rationale: 'Interval width reflects active alerts, anomalies, maintenance events, and feedback records.',
    },
    model_version: {
      id: 'rul-risk-heuristic-v2',
      name: 'Maintenance Wizard RUL Risk Model',
      version: '2.0.0',
      algorithm: 'deterministic weighted risk score with rolling-baseline anomaly features',
      feature_set: ['active alert severity', 'rolling-baseline anomaly severity'],
      trained_on: 'seeded maintenance history, active alerts, sensor readings, and approved feedback labels',
      status: 'active',
    },
    model_evaluation: {
      evaluation_id: 'backtest-2.0.0-RM-DRIVE-01',
      backtest_window_days: 180,
      sample_count: 14,
      precision: 0.74,
      recall: 0.69,
      mean_absolute_rul_error_days: 16,
      calibration_error: 0.14,
      summary: 'Backtest compares historical alert/anomaly windows against recorded maintenance events.',
    },
    prediction_evidence: [
      {
        source_type: 'alert',
        source_id: 'ALT-1001',
        title: 'drive_end_vibration critical alert',
        detail: 'Drive end vibration exceeds trip advisory threshold.',
        contribution: 1,
      },
    ],
    degradation_trend: [
      {
        timestamp: '2026-06-06T08:15:00+05:30',
        signal: 'drive_end_vibration',
        value: 9.8,
        unit: 'mm/s',
        threshold: 7.1,
        normalized_severity: 1,
        estimated_rul_days: 18,
      },
    ],
    drivers: ['2 active alert(s) require maintenance review.', 'drive_end_vibration is critical risk.'],
    reasoning_explanation: null,
  },
}

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
  output_refs: { dataset_id: 'LDS-1', example_count: 1 },
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
  runtime_provider: 'lm_studio',
  serving_provider: 'openai',
  served_model_name: 'qwen2.5-7b-instruct-lora-candidate',
  base_url: 'http://localhost:1234/v1',
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

let learningDeploymentResponses = [learningDeployment]
let learningArtifactCleanupRequests: unknown[] = []
let learningSummaryExamples = [learningExample]
let learningRefreshExamples = [learningExample]

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

function learningSummaryPayload(
  examples = [learningExample],
  datasets = [learningDataset],
  evaluations = [learningEvaluation],
  jobs = [learningJob],
  artifacts = [learningArtifact],
  promotions = [learningPromotion],
  deployments = learningDeploymentResponses,
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
        notes: 'Local LM Studio model used by Neo, Morpheus, and Smith.',
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
      openai_base_url: 'http://localhost:1234/v1',
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
      embedding_profile: {
        ...learningEmbeddingProfile,
        provider: 'deterministic_hash',
        model: 'maintenance-hash-v1',
        version: '1',
        dimensions: 64,
        configured_dimensions: 64,
        distance: 'Cosine',
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
    admin: 'Ragav',
    maintenance_engineer: 'Lokesh',
    maintenance_technician: 'Vinoth',
    maintenance_supervisor: 'Dhruv',
    reliability_engineer: 'Guna',
    planner: 'Priya',
    operator: 'Jan',
    iot_service: 'Vijay',
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

function neoWelcomeFor(user = userFor()): NeoChatResponse {
  if (user.role === 'maintenance_technician') {
    return {
      answer:
        'I’m Neo. Vinoth, immediate attention: 1 open work order is assigned to you.\n\n### Primary Work Order: WO-8304 (APPR)\nThis work order is approved. Confirm lockout/tagout, then ask me to start it before field execution.\n1. Safety: verify permits and stored-energy release.\n2. Execute: Reduce load if vibration persists.\n3. Evidence: record readings and photos.\n4. Coding: use problem code BRGVIB.\n5. Closeout: summarize cause, action taken, residual risk, and follow-up.',
      table: {
        title: 'Your Assigned Work',
        columns: ['Work order', 'Asset', 'Status', 'Priority'],
        rows: [{ 'Work order': 'WO-8304', Asset: 'RM-DRIVE-01', Status: 'APPR', Priority: 1 }],
      },
      action: {
        type: 'neo_welcome',
        label: 'Loaded technician attention',
        status: 'completed',
        target_id: 'WO-8304',
        detail: '1 open assigned work order.',
      },
      used_live_provider: false,
      provider: 'deterministic',
    }
  }
  if (user.role === 'operator') {
    return {
      answer:
        'I’m Neo. Immediate attention for Jan: 2 critical/high-risk assets should be watched from operations. Your role is read-only here.',
      table: {
        title: 'Operator Attention',
        columns: ['Asset', 'Name', 'Area', 'Status', 'Risk'],
        rows: [{ Asset: 'RM-DRIVE-01', Name: 'Hot Strip Mill Main Drive Motor', Area: 'Hot Rolling Mill', Status: 'degraded', Risk: 'critical' }],
      },
      action: {
        type: 'neo_welcome',
        label: 'Loaded operator attention',
        status: 'completed',
        detail: '1 operator attention asset.',
      },
      used_live_provider: false,
      provider: 'deterministic',
    }
  }
  return {
    answer:
      'I’m Neo. Dhruv, immediate attention: 1 work order waiting for approval, 1 follow-up item, and 1 urgent open item.',
    table: {
      title: 'Supervisor Attention',
      columns: ['Work order', 'Asset', 'Status', 'Priority'],
      rows: [{ 'Work order': 'WO-8311', Asset: 'BF-BLOWER-02', Status: 'WAPPR', Priority: 2 }],
    },
    action: {
      type: 'neo_welcome',
      label: 'Loaded supervisor attention',
      status: 'completed',
      detail: '1 supervisor attention item.',
    },
    used_live_provider: false,
    provider: 'deterministic',
  }
}

async function signIn(email = 'admin@plant.local') {
  if (email !== 'admin@plant.local') {
    fireEvent.change(await screen.findByLabelText('Email'), { target: { value: email } })
  }
  fireEvent.click(await screen.findByRole('button', { name: /sign in/i }))
  await screen.findByRole('button', { name: 'Logout' })
}

beforeEach(() => {
  neoResponseDelayMs = 0
  assistantResponseDelayMs = 0
  logoutResponseDelayMs = 0
  maintenanceInsightsDelayMs = 0
  ingestionResponseDelayMs = 0
  learningJudgeDelayMs = 0
  apiWorkOrders = workOrders as WorkOrder[]
  apiPmPlans = [existingPmPlan]
  learningDeploymentResponses = [learningDeployment]
  learningArtifactCleanupRequests = []
  learningSummaryExamples = [learningExample]
  learningRefreshExamples = [learningExample]
  supervisorAssistantRequests = []
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
        if (logoutResponseDelayMs > 0) {
          return new Promise((resolve) => {
            window.setTimeout(() => resolve(new Response(JSON.stringify({ status: 'logged_out' }), { status: 200 })), logoutResponseDelayMs)
          })
        }
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
      if (url.endsWith('/api/rca-cases')) {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}')
          return Promise.resolve(
            new Response(
              JSON.stringify({
                ...rcaCase,
                id: 'RCA-9002',
                equipment_id: body.equipment_id,
                work_order_id: body.work_order_id,
                title: body.title,
                symptoms: body.symptoms ?? [],
                status: 'open',
              }),
              { status: 201 },
            ),
          )
        }
        return Promise.resolve(new Response(JSON.stringify([rcaCase]), { status: 200 }))
      }
      if (url.endsWith('/api/rca-cases/morpheus-draft/stream')) {
        return Promise.resolve(
          rcaDraftStreamResponse({
            case: {
              ...rcaCase,
              confidence: 0.74,
              morpheus_summary: 'Morpheus drafted RCA hypotheses, missing checks, and corrective actions from RAG evidence.',
              morpheus_fishbone_text: '- Contaminants/Buildup:\n- Seal flush strainer restriction (Primary cause)',
            },
            evidence: recommendation.evidence,
            message: 'Morpheus drafted RCA hypotheses, evidence, missing checks, and corrective actions.',
          }),
        )
      }
      if (url.endsWith('/api/rca-cases/morpheus-draft')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              case: {
                ...rcaCase,
                confidence: 0.74,
                morpheus_summary: 'Morpheus drafted RCA hypotheses, missing checks, and corrective actions from RAG evidence.',
                morpheus_fishbone_text: '- Contaminants/Buildup:\n- Seal flush strainer restriction (Primary cause)',
              },
              evidence: recommendation.evidence,
              message: 'Morpheus drafted RCA hypotheses, evidence, missing checks, and corrective actions.',
            }),
            { status: 200 },
          ),
        )
      }
      if (url.includes('/api/rca-cases/') && init?.method === 'PATCH') {
        const body = JSON.parse((init.body as string) ?? '{}')
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...rcaCase,
              ...body,
              closed_at: body.status === 'closed' ? '2026-06-14T09:00:00+05:30' : rcaCase.closed_at,
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/summary')) {
        return Promise.resolve(new Response(JSON.stringify(learningSummaryPayload(learningSummaryExamples)), { status: 200 }))
      }
      if (url.endsWith('/api/learning/examples/refresh')) {
        return Promise.resolve(new Response(JSON.stringify(learningRefreshExamples), { status: 200 }))
      }
      if (url.includes('/api/learning/examples/') && url.endsWith('/judge')) {
        const response = new Response(
          JSON.stringify({
            ...learningExample,
            judge_score: 0.91,
            judge_rationale: 'Live LLM judge confirmed the example is specific, safe, and outcome-backed.',
          }),
          { status: 200 },
        )
        return learningJudgeDelayMs > 0 ? delayedResponse(response, init, learningJudgeDelayMs) : Promise.resolve(response)
      }
      if (url.includes('/api/learning/examples/')) {
        const body = JSON.parse((init?.body as string) ?? '{}')
        return Promise.resolve(new Response(JSON.stringify({ ...learningExample, approved: body.approved }), { status: 200 }))
      }
      if (url.endsWith('/api/learning/examples')) {
        return Promise.resolve(new Response(JSON.stringify([learningExample]), { status: 200 }))
      }
      if (url.endsWith('/api/learning/model-deployments')) {
        return Promise.resolve(new Response(JSON.stringify(learningDeploymentResponses), { status: 200 }))
      }
      if (url.endsWith('/api/learning/artifacts/cleanup')) {
        learningArtifactCleanupRequests.push(JSON.parse((init?.body as string) ?? '{}'))
        return Promise.resolve(new Response(JSON.stringify(learningArtifactCleanupResult), { status: 200 }))
      }
      if (url.includes('/api/learning/model-versions/') && url.endsWith('/deploy')) {
        const body = JSON.parse((init?.body as string) ?? '{}')
        const nextDeployment = {
          ...learningDeployment,
          id: 'LDEPLOY-NEW',
          job_id: 'LJOB-DEPLOY-1',
          runtime_provider: body.runtime_provider ?? 'lm_studio',
          served_model_name: body.served_model_name,
          base_url: body.base_url ?? null,
          artifact_uri: body.artifact_uri ?? null,
          artifact_hash: body.artifact_hash ?? null,
          status: 'deploying',
          health_status: 'pending',
          health_checked_at: null,
          error: null,
          updated_at: '2026-06-13T09:30:00+05:30',
        }
        learningDeploymentResponses = [nextDeployment, ...learningDeploymentResponses]
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...learningJob,
              id: 'LJOB-DEPLOY-1',
              job_type: 'adapter_deployment',
              subject: 'maintenance.learning.adapter.deployment.requested',
              status: 'queued',
              input_refs: body,
              output_refs: { deployment_id: nextDeployment.id },
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/model-versions')) {
        const body = JSON.parse((init?.body as string) ?? '{}')
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'model-adapter-candidate',
              provider: body.provider,
              model_name: body.model_name,
              base_model: body.base_model,
              adapter_path: body.adapter_path,
              status: body.status ?? 'candidate',
              notes: body.notes,
              created_at: '2026-06-13T09:12:00+05:30',
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/model-versions/promote')) {
        return Promise.resolve(new Response(JSON.stringify({ ...learningPromotion, id: 'LPROMO-NEW' }), { status: 200 }))
      }
      if (url.endsWith('/api/learning/model-versions/rollback')) {
        return Promise.resolve(
          new Response(JSON.stringify({ ...learningPromotion, id: 'LPROMO-ROLLBACK-1', action: 'rollback' }), { status: 200 }),
        )
      }
      if (url.endsWith('/api/learning/model-promotions')) {
        return Promise.resolve(new Response(JSON.stringify([learningPromotion]), { status: 200 }))
      }
      if (url.endsWith('/api/learning/evaluations')) {
        if (init?.method === 'POST') {
          return Promise.resolve(new Response(JSON.stringify({ ...learningEvaluation, id: 'LEVAL-NEW' }), { status: 200 }))
        }
        return Promise.resolve(new Response(JSON.stringify([learningEvaluation]), { status: 200 }))
      }
      if (url.endsWith('/api/learning/jobs/peft')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...learningJob,
              id: 'LJOB-PEFT-1',
              job_type: 'peft_tuning',
              subject: 'maintenance.learning.peft.requested',
              status: 'queued',
              output_refs: { dispatch: 'disabled' },
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/rag/embedding-profiles')) {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}')
          return Promise.resolve(
            new Response(
              JSON.stringify({
                ...learningEmbeddingProfile,
                id: 'emb-candidate',
                provider: body.provider,
                model: body.model,
                version: body.version,
                dimensions: body.dimensions,
                distance: body.distance,
                status: 'candidate',
                notes: body.notes,
              }),
              { status: 200 },
            ),
          )
        }
        return Promise.resolve(new Response(JSON.stringify([learningEmbeddingProfile]), { status: 200 }))
      }
      if (url.includes('/api/learning/rag/embedding-profiles/') && url.endsWith('/activate')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...learningJob,
              id: 'LJOB-EMBED-1',
              job_type: 'rag_embedding_profile',
              subject: 'maintenance.learning.rag.embedding.profile.requested',
              status: 'completed',
              output_refs: { active_profile_id: learningEmbeddingProfile.id },
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/rag/migration/preview')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
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
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/rag/migration')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...learningJob,
              id: 'LJOB-RAG-MIGRATE-1',
              job_type: 'rag_migration',
              subject: 'maintenance.learning.rag.migration.requested',
              status: 'completed',
              output_refs: {
                document_count: 6,
                chunk_count: 14,
                target_collection: 'maintenance_wizard_documents_v1',
              },
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/rag/reindex')) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...learningJob,
              id: 'LJOB-RAG-1',
              job_type: 'rag_reindex',
              subject: 'maintenance.learning.rag.reindex.requested',
              status: 'completed',
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
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/learning/jobs')) {
        return Promise.resolve(new Response(JSON.stringify([learningJob]), { status: 200 }))
      }
      if (url.endsWith('/api/learning/datasets')) {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}')
          return Promise.resolve(
            new Response(
              JSON.stringify({
                ...learningDataset,
                id: 'LDS-NEW',
                name: body.name,
                description: body.description,
                example_count: 1,
              }),
              { status: 200 },
            ),
          )
        }
        return Promise.resolve(new Response(JSON.stringify([learningDataset]), { status: 200 }))
      }
      if (url.includes('/api/learning/datasets/') && url.endsWith('/jsonl')) {
        return Promise.resolve(
          new Response(
            '{"messages":[{"role":"system","content":"maintenance assistant"}],"metadata":{"judge_score":0.82}}\n',
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/dashboard/summary')) {
        return Promise.resolve(new Response(JSON.stringify(dashboard), { status: 200 }))
      }
      if (url.endsWith('/api/assets')) {
        return Promise.resolve(new Response(JSON.stringify(assets), { status: 200 }))
      }
      if (url.includes('/api/assets/') && url.endsWith('/reliability/stream')) {
        return Promise.resolve(reliabilityPredictionStreamResponse(assetDetail.prediction))
      }
      if (url.includes('/api/assets/')) {
        const equipmentId = url.match(/\/api\/assets\/([^/?]+)/)?.[1] ?? 'RM-DRIVE-01'
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...assetDetail,
              profile: {
                ...assetDetail.profile,
                equipment_id: equipmentId,
                name: assets.find((asset) => asset.id === equipmentId)?.name ?? assetDetail.profile.name,
              },
            }),
            { status: 200 },
          ),
        )
      }
      if (url.endsWith('/api/neo/welcome/stream')) {
        const response = neoWelcomeFor(userFromRequest(init))
        return Promise.resolve(neoStreamResponse(response, [response.answer]))
      }
      if (url.endsWith('/api/neo/welcome')) {
        return Promise.resolve(new Response(JSON.stringify(neoWelcomeFor(userFromRequest(init))), { status: 200 }))
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
        const body = JSON.parse((init?.body as string) ?? '{}')
        const initialContext = body.requested_step === 'initial_context'
        const selectedOrder = apiWorkOrders.find((item) => item.id === body.work_order_id) ?? apiWorkOrders[0]
        if (initialContext) {
          const blocked = selectedOrder.material_readiness === 'blocked' || selectedOrder.material_blocker_status === 'blocked'
          const initialAnswer = blocked
            ? `Vinoth, WO-8304 is waiting for material. Drive end spherical roller bearing is not ready; expected availability is 2026-07-03. Do not start field execution until the blocker is resolved.`
            : `Vinoth, WO-8304 is approved and ready for technician execution. Review the current work order context before recording observations.`
          const response = assistantStreamResponse(
            {
              work_order_id: selectedOrder.id,
              next_prompt: initialAnswer,
              live_directions: [initialAnswer],
              recommendations: ['Use Neo to record the next relevant observation.'],
              safety_reminders: ['Apply lockout/tagout.'],
              suggested_problem_code: selectedOrder.problem_code,
              suggested_failure_class: selectedOrder.failure_class,
              completion_summary: `${selectedOrder.id} initial context reviewed.`,
              evidence: recommendation.evidence,
              used_live_provider: false,
              provider: 'mock',
            },
            [initialAnswer],
          )
          if (assistantResponseDelayMs > 0) {
            return delayedResponse(response, init, assistantResponseDelayMs)
          }
          return Promise.resolve(response)
        }
        const response = assistantStreamResponse(
          {
            work_order_id: 'WO-8304',
            next_prompt: 'Neo recommends verifying torque and documenting completion.',
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
          ['Neo recommends verifying torque ', 'and documenting completion.'],
        )
        if (assistantResponseDelayMs > 0) {
          return delayedResponse(response, init, assistantResponseDelayMs)
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
        const body = JSON.parse((init?.body as string) ?? '{}')
        supervisorAssistantRequests.push(body)
        const approvalQueue = body.queue_name === 'waiting_approval'
        const summary = approvalQueue
          ? 'Dhruv, waiting for approval: WO-8311 needs supervisor approval before execution.'
          : 'Dhruv, Neo reviewed 2 work orders and found 2 follow-ups.'
        const response = assistantStreamResponse(
          {
            summary,
            follow_up_actions: approvalQueue
              ? ['Approve or reject WO-8311 for BF-BLOWER-02.']
              : ['Review WO-8297 brake shoe replacement planning.'],
            risks: approvalQueue
              ? ['WO-8311 is waiting for approval.']
              : ['WO-8304 remains priority 1 and APPR.'],
            draft_work_order: null,
            referenced_work_orders: approvalQueue ? ['WO-8311'] : ['WO-8304', 'WO-8297'],
            used_live_provider: false,
            provider: 'mock',
          },
          approvalQueue ? ['Dhruv, waiting for approval: WO-8311 needs supervisor approval.'] : ['Dhruv, Neo reviewed 2 work orders ', 'and found 2 follow-ups.'],
        )
        if (assistantResponseDelayMs > 0) {
          return delayedResponse(response, init, assistantResponseDelayMs)
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
      if (url.includes('/api/pm-templates')) {
        return Promise.resolve(new Response(JSON.stringify(pmTemplates), { status: 200 }))
      }
      if (url.endsWith('/api/pm-plans/morpheus-draft/stream')) {
        apiPmPlans = [generatedPmPlan, ...apiPmPlans.filter((plan) => plan.id !== generatedPmPlan.id)]
        return Promise.resolve(
          pmDraftStreamResponse({
            plan: generatedPmPlan,
            templates: pmTemplates,
            message: 'Morpheus drafted PM plan PM-7001 and Smith generated technician-ready steps.',
          }),
        )
      }
      if (url.endsWith('/api/pm-plans/morpheus-draft')) {
        apiPmPlans = [generatedPmPlan, ...apiPmPlans.filter((plan) => plan.id !== generatedPmPlan.id)]
        return Promise.resolve(
          new Response(
            JSON.stringify({
              plan: generatedPmPlan,
              templates: pmTemplates,
              message: 'Morpheus drafted PM plan PM-7001 and Smith generated technician-ready steps.',
            }),
            { status: 200 },
          ),
        )
      }
      if (url.includes('/api/pm-plans/') && url.endsWith('/convert-work-order')) {
        const planId = url.match(/\/api\/pm-plans\/([^/?]+)\/convert-work-order/)?.[1] ?? 'PM-7001'
        const created = {
          ...workOrders[0],
          id: 'WO-9100',
          equipment_id: 'RM-DRIVE-01',
          title: 'PM: Main drive proactive PM plan',
          work_type: 'PM',
          planning_status: 'planned',
          recommended_action: generatedPmPlan.tasks[0].task,
          ai_summary: `Generated from PM plan ${planId}.`,
        } as WorkOrder
        apiWorkOrders = [created, ...apiWorkOrders.filter((order) => order.id !== created.id)]
        apiPmPlans = apiPmPlans.map((plan) => (
          plan.id === planId ? { ...plan, status: 'converted', converted_work_order_id: created.id } : plan
        ))
        return Promise.resolve(new Response(JSON.stringify(created), { status: 200 }))
      }
      if (url.includes('/api/pm-plans')) {
        return Promise.resolve(new Response(JSON.stringify(apiPmPlans), { status: 200 }))
      }
      if (url.includes('/api/work-orders')) {
        if (init?.method === 'POST') {
          const body = JSON.parse((init.body as string) ?? '{}')
          return Promise.resolve(
            new Response(
              JSON.stringify({
                ...workOrders[0],
                planning_status: 'unscheduled',
                planned_start: null,
                planned_end: null,
                outage_window: null,
                material_readiness: 'unknown',
                material_blocker_status: 'not_required',
                material_blocker_note: null,
                spare_reservations: [],
                dispatch_notes: null,
                dispatched_at: null,
                ...body,
                id: 'WO-9001',
                status: 'WAPPR',
              }),
              { status: 201 },
            ),
          )
        }
        if (init?.method === 'PATCH') {
          const body = JSON.parse((init.body as string) ?? '{}')
          const workOrderId = url.match(/\/api\/work-orders\/([^/?]+)/)?.[1]
          const original = apiWorkOrders.find((item) => item.id === workOrderId) ?? { ...apiWorkOrders[0], id: workOrderId ?? apiWorkOrders[0].id }
          const updated = {
            ...original,
            ...body,
            dispatched_at: body.planning_status === 'dispatched' ? '2026-06-12T13:45:00+05:30' : original.dispatched_at,
          }
          apiWorkOrders = apiWorkOrders.some((item) => item.id === updated.id)
            ? apiWorkOrders.map((item) => (item.id === updated.id ? updated : item))
            : [updated, ...apiWorkOrders]
          return Promise.resolve(
            new Response(
              JSON.stringify(updated),
              { status: 200 },
            ),
          )
        }
        const requestUser = userFromRequest(init)
        const rows = requestUser.role === 'maintenance_technician'
          ? apiWorkOrders.filter((order) => order.assigned_to === requestUser.display_name)
          : apiWorkOrders
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
      if (url.endsWith('/api/diagnose/stream')) {
        return Promise.resolve(diagnosisStreamResponse(recommendation))
      }
      if (url.endsWith('/api/diagnose')) {
        return Promise.resolve(new Response(JSON.stringify(recommendation), { status: 200 }))
      }
      if (url.endsWith('/api/ingest/document-file')) {
        const response = new Response(JSON.stringify({ status: 'stored', documents: 1 }), { status: 200 })
        return ingestionResponseDelayMs > 0 ? delayedResponse(response, init, ingestionResponseDelayMs) : Promise.resolve(response)
      }
      if (url.endsWith('/api/ingest/documents')) {
        const response = new Response(JSON.stringify({ status: 'stored', documents: 1 }), { status: 200 })
        return ingestionResponseDelayMs > 0 ? delayedResponse(response, init, ingestionResponseDelayMs) : Promise.resolve(response)
      }
      if (url.endsWith('/api/ingest/records')) {
        const response = new Response(JSON.stringify({ status: 'stored', counts: { alerts: 1, equipment: 0 } }), { status: 200 })
        return ingestionResponseDelayMs > 0 ? delayedResponse(response, init, ingestionResponseDelayMs) : Promise.resolve(response)
      }
      if (url.endsWith('/feedback')) {
        return Promise.resolve(new Response(JSON.stringify({ stored: true }), { status: 200 }))
      }
      if (url.includes('/api/reports/maintenance-insights/markdown')) {
        return Promise.resolve(new Response('# Structured Maintenance Insights', { status: 200 }))
      }
      if (url.includes('/api/reports/maintenance-insights')) {
        const reportUrl = new URL(url, 'http://localhost')
        const scopedEquipmentId = reportUrl.searchParams.get('equipment_id')
        const scopedStructuredReports = scopedEquipmentId
          ? maintenanceInsights.structured_reports.filter((report) => report.equipment_id === scopedEquipmentId)
          : maintenanceInsights.structured_reports
        const scopedAbnormalReports = scopedEquipmentId
          ? maintenanceInsights.abnormal_alert_reports.filter((report) => report.equipment_id === scopedEquipmentId)
          : maintenanceInsights.abnormal_alert_reports
        const scopedLogEntries = scopedEquipmentId
          ? maintenanceInsights.maintenance_log_entries.filter((entry) => entry.equipment_id === scopedEquipmentId)
          : maintenanceInsights.maintenance_log_entries
        const scopedBundle = {
          ...maintenanceInsights,
          scope_equipment_id: scopedEquipmentId,
          assets_reviewed: scopedEquipmentId ? 1 : maintenanceInsights.assets_reviewed,
          structured_reports: scopedStructuredReports,
          abnormal_alert_reports: scopedAbnormalReports,
          maintenance_log_entries: scopedLogEntries,
        }
        let body: unknown = scopedBundle
        if (reportUrl.pathname.endsWith('/summary')) {
          body = {
            generated_at: scopedBundle.generated_at,
            scope_equipment_id: scopedBundle.scope_equipment_id,
            assets_reviewed: scopedBundle.assets_reviewed,
            structured_report_count: scopedStructuredReports.length,
            abnormal_alert_report_count: scopedAbnormalReports.length,
            decision_summary_count: maintenanceInsights.decision_summaries.length,
            maintenance_log_entry_count: scopedLogEntries.length,
          }
        } else if (reportUrl.pathname.endsWith('/structured-reports')) {
          body = scopedStructuredReports
        } else if (reportUrl.pathname.endsWith('/abnormal-alerts')) {
          body = scopedAbnormalReports
        } else if (reportUrl.pathname.endsWith('/decision-summaries')) {
          body = maintenanceInsights.decision_summaries
        } else if (reportUrl.pathname.endsWith('/maintenance-log-entries')) {
          body = scopedLogEntries
        }
        const response = new Response(JSON.stringify(body), { status: 200 })
        if (maintenanceInsightsDelayMs > 0) {
          return new Promise((resolve) => {
            window.setTimeout(() => resolve(response), maintenanceInsightsDelayMs)
          })
        }
        return Promise.resolve(response)
      }
      if (url.endsWith('/api/reports/RM-DRIVE-01/markdown')) {
        return Promise.resolve(new Response('# Maintenance Decision Report: RM-DRIVE-01', { status: 200 }))
      }
      return Promise.resolve(new Response('{}', { status: 200 }))
    }),
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  window.sessionStorage.clear()
  api.setSession(null)
  api.onUnauthorized(null)
})

describe('Intelligent Maintenance Wizard dashboard', () => {
  it('renders dashboard metrics, anomalies, and selected asset details', async () => {
    render(<App />)
    await signIn()
    fireEvent.click(await screen.findByRole('button', { name: 'Command Center' }))

    expect(screen.queryByText('API connected')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Assets at risk' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Work queues' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Equipment efficiency' })).toBeInTheDocument()
    expect(screen.getByText('Health score (%)')).toBeInTheDocument()
    expect(screen.getByText('Equipment group')).toBeInTheDocument()
    expect(screen.getByText('SLA compliance (%)')).toBeInTheDocument()
    expect(screen.getByText('Incident priority')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Neo' })).toBeInTheDocument()
    expect(screen.getByText('Dashboard AI assistant')).toBeInTheDocument()
    const supervisorTable = await screen.findByLabelText('Supervisor Attention results table')
    expect(within(supervisorTable).getByText('Waiting for approval')).toBeInTheDocument()
    expect(within(supervisorTable).queryByText('WAPPR')).not.toBeInTheDocument()
    expect(screen.getByText('Priority Assets (5)')).toBeInTheDocument()
    const navigation = screen.getByLabelText('Maintenance navigation')
    expect(within(navigation).getByRole('button', { name: 'Assets' })).toBeInTheDocument()
    const quickActions = within(navigation).getByLabelText('Quick actions')
    expect(within(quickActions).getByRole('heading', { name: 'Quick actions' })).toBeInTheDocument()
    expect(within(quickActions).getByRole('button', { name: /create work order/i })).toBeInTheDocument()
    expect(screen.getByText('Melt Shop Overhead Crane')).toBeInTheDocument()
    expect(screen.getByText('Hot Rolling Hydraulic System')).toBeInTheDocument()
    const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText('Hot Strip Mill Main Drive Motor').closest('button')
    if (!assetButton) throw new Error('Missing asset button')
    fireEvent.click(assetButton)
    expect(await screen.findByRole('heading', { name: 'Hot Strip Mill Main Drive Motor' })).toBeInTheDocument()
    expect(screen.getByText('Performance insights')).toBeInTheDocument()
    expect(screen.getByText('Drive train and coupling')).toBeInTheDocument()
    expect(screen.getByText('Bearing housing inspection')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Diagnosis and recommendation' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Engineer Query' })).not.toBeInTheDocument()
    expect(screen.queryByText('Drive End Vibration')).not.toBeInTheDocument()
    expect(screen.queryByText('Maintenance history')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run Morpheus' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Morpheus' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Performance' }))
    expect(await screen.findByRole('heading', { name: 'Performance metrics' })).toBeInTheDocument()
    expect(screen.getByText('Signal time')).toBeInTheDocument()
    expect(screen.getByText('Value (mm/s)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Command Center' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Admin' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Ingestion file')).not.toBeInTheDocument()
  })

  it('opens a prefilled work order review dialog before submitting creation', async () => {
    render(<App />)
    await signIn()

    const quickActions = within(screen.getByLabelText('Maintenance navigation')).getByLabelText('Quick actions')
    fireEvent.click(within(quickActions).getByRole('button', { name: /create work order/i }))

    const dialog = await screen.findByRole('dialog', { name: 'Review Work Order' })
    expect(within(dialog).getByLabelText('Equipment')).toHaveValue('RM-DRIVE-01')
    expect(within(dialog).getByLabelText('Work order title')).toHaveValue('Inspect Hot Strip Mill Main Drive Motor')
    expect(within(dialog).getByLabelText('Recommended action')).toHaveValue(
      'Critical vibration alert and unavailable bearing spare require intervention planning.',
    )
    expect(
      vi.mocked(fetch).mock.calls.some(([url, init]) => url.toString().endsWith('/api/work-orders') && init?.method === 'POST'),
    ).toBe(false)

    fireEvent.change(within(dialog).getByLabelText('Work order title'), {
      target: { value: 'Inspect drive bearing after vibration alert' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: 'Confirm and submit' }))

    expect(await screen.findByText('Created WO-9001')).toBeInTheDocument()
    const createCall = vi.mocked(fetch).mock.calls.find(([url, init]) => (
      url.toString().endsWith('/api/work-orders') && init?.method === 'POST'
    ))
    expect(JSON.parse((createCall?.[1]?.body as string) ?? '{}')).toMatchObject({
      equipment_id: 'RM-DRIVE-01',
      title: 'Inspect drive bearing after vibration alert',
      work_type: 'CM',
      problem_code: 'INVESTIGATE',
    })
  })

  it('opens an Assets page with a company asset table and data-backed asset detail', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(within(screen.getByLabelText('Maintenance navigation')).getByRole('button', { name: 'Assets' }))

    const assetsTable = await screen.findByLabelText('Company assets table')
    expect(within(assetsTable).getByText('AC main drive motor')).toBeInTheDocument()
    expect(within(assetsTable).getByText('HSM-FS-01')).toBeInTheDocument()
    expect(within(assetsTable).getByText('Dhruv')).toBeInTheDocument()

    fireEvent.click(within(assetsTable).getByRole('button', { name: /Hot Strip Mill Main Drive Motor/ }))

    expect(await screen.findByText('Bharat Heavy Electricals')).toBeInTheDocument()
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => url.toString().includes('/api/assets/RM-DRIVE-01?sections=summary')),
    ).toBe(true)
    const assetTabs = screen.getByRole('tablist', { name: 'Asset detail tabs' })
    expect(within(assetTabs).getByRole('tab', { name: 'Summary' })).toHaveAttribute('aria-selected', 'true')
    const assetReliabilityTab = within(assetTabs).getByRole('tab', { name: 'Reliability' })
    expect(assetReliabilityTab).toHaveAttribute('aria-selected', 'false')
    fireEvent.click(assetReliabilityTab)
    expect(assetReliabilityTab).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('MTBF')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Smith' })).toBeInTheDocument()
    expect(screen.getByText('Predictive failure assistant')).toBeInTheDocument()
    expect(screen.getByLabelText('Smith failure prediction stream')).toBeInTheDocument()
    expect(await screen.findByText('Live LLM · openai')).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Failure Prediction' })).toBeInTheDocument()
    expect(screen.getByText('77% failure probability')).toBeInTheDocument()
    expect(screen.getByLabelText('Prediction model evidence')).toBeInTheDocument()
    expect(screen.getByText('Maintenance Wizard RUL Risk Model 2.0.0')).toBeInTheDocument()
    expect(screen.getByText('74% precision / 69% recall')).toBeInTheDocument()
    expect(screen.getByText('68-84% probability')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Prediction Evidence' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Degradation Trend History' })).toBeInTheDocument()
    expect(screen.queryByText('Performance insights')).not.toBeInTheDocument()
    expect(screen.queryByText('Recommended actions')).not.toBeInTheDocument()
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => url.toString().includes('/api/assets/RM-DRIVE-01?sections=reliability')),
    ).toBe(true)
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => url.toString().includes('/api/assets/RM-DRIVE-01/reliability/stream')),
    ).toBe(true)
    const assetDocumentsTab = within(assetTabs).getByRole('tab', { name: 'Documents' })
    fireEvent.click(assetDocumentsTab)
    expect(assetDocumentsTab).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('Knowledge Retrieval')).toBeInTheDocument()
    expect(screen.getAllByText('Hot Strip Mill Main Drive Vibration SOP').length).toBeGreaterThan(0)
    expect(screen.getByText('Main Drive Vibration Shift Log')).toBeInTheDocument()
    expect(screen.queryByText('Performance insights')).not.toBeInTheDocument()
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => url.toString().includes('/api/assets/RM-DRIVE-01?sections=documents')),
    ).toBe(true)
  })

  it('opens structured maintenance insights and scopes reports to the selected asset', async () => {
    maintenanceInsightsDelayMs = 50
    const createObjectUrl = vi.fn(() => 'blob:maintenance-insights')
    const revokeObjectUrl = vi.fn()
    Object.defineProperty(window.URL, 'createObjectURL', { configurable: true, value: createObjectUrl })
    Object.defineProperty(window.URL, 'revokeObjectURL', { configurable: true, value: revokeObjectUrl })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    render(<App />)
    await signIn()

    fireEvent.click(within(screen.getByLabelText('Maintenance navigation')).getByRole('button', { name: 'Reports' }))

    await waitFor(() => {
      expect(screen.getAllByRole('status').length).toBeGreaterThanOrEqual(1)
    })
    expect(screen.getAllByRole('status').map((item) => item.textContent).join(' ')).toContain('Loading')
    expect(await screen.findByRole('heading', { name: 'Structured Maintenance Insights and Reports' })).toBeInTheDocument()
    expect(screen.getByText(/LLM-dependent report content is limited to recommendation Markdown exports/)).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Structured Maintenance Reports' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Abnormal Alert Reports' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Engineer Maintenance Decision Summary' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { name: 'Supervisor Maintenance Decision Summary' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Equipment Digital Maintenance Log Entries' })).toBeInTheDocument()
    expect(screen.getByText('Hot Strip Mill Main Drive Motor is at critical risk with 10% health.')).toBeInTheDocument()
    expect(screen.getByText('Blast Furnace Combustion Air Blower has pressure variance risk.')).toBeInTheDocument()
    expect(screen.getByText('Escalate for same-shift maintenance review.')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh selected asset' }))

    await waitFor(() => {
      expect(screen.queryByText('Blast Furnace Combustion Air Blower has pressure variance risk.')).not.toBeInTheDocument()
    })
    expect(await screen.findByText('Hot Strip Mill Main Drive Motor is at critical risk with 10% health.')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Export Markdown' })).not.toBeDisabled()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Export Markdown' }))

    await waitFor(() => {
      expect(anchorClick).toHaveBeenCalled()
    })
    expect(createObjectUrl).toHaveBeenCalledWith(expect.any(Blob))
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:maintenance-insights')
    expect(screen.getByText('Structured maintenance insights downloaded')).toBeInTheDocument()
    expect(
      vi.mocked(fetch).mock.calls.some(([url]) => url.toString().includes('/api/reports/maintenance-insights/markdown')),
    ).toBe(false)
  })

  it('lets Neo update the dashboard center table for read-only users', async () => {
    neoResponseDelayMs = 500
    render(<App />)
    await signIn('operator@plant.local')

    expect(await screen.findByRole('heading', { name: 'Neo' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Ask Neo'), { target: { value: 'Show work orders needing follow-up' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await screen.findByText(/Thinking/)).toBeInTheDocument()
    expect(await screen.findByText('Neo found work orders that need attention. WO-8304 and WO-8297 require follow-up.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Work Orders' })).toBeInTheDocument()
    const neoResultTable = screen.getByLabelText('Work Orders results table')
    expect(within(neoResultTable).getByText('WO-8304')).toBeInTheDocument()
    expect(within(neoResultTable).getByText('OH-CRANE-05')).toBeInTheDocument()
    expect(within(neoResultTable).getByText('Approved')).toBeInTheDocument()
    expect(within(neoResultTable).getByText('Completed')).toBeInTheDocument()
    expect(within(neoResultTable).queryByText('APPR')).not.toBeInTheDocument()
    expect(within(neoResultTable).queryByText('COMP')).not.toBeInTheDocument()
    const transcript = screen.getByLabelText('Neo chat transcript')
    expect(transcript.textContent).not.toContain('The table is updated')
    expect(transcript.textContent).not.toContain('Updated table')
    expect(transcript.textContent).not.toContain('row(s)')
    expect(transcript.textContent).not.toContain('2 rows for Work Orders')
  })

  it('loads a role-aware Neo welcome with technician immediate work guidance', async () => {
    render(<App />)
    await signIn('technician@plant.local')
    fireEvent.click(await screen.findByRole('button', { name: 'Command Center' }))

    const transcript = screen.getByLabelText('Neo chat transcript')
    expect(await within(transcript).findByText(/Vinoth, immediate attention: 1 open work order is assigned to you/i)).toBeInTheDocument()
    expect(within(transcript).getByRole('heading', { name: 'Primary Work Order: WO-8304 (Approved)' })).toBeInTheDocument()
    expect(within(transcript).getByText(/Closeout: summarize cause/)).toBeInTheDocument()
    expect(transcript.textContent).not.toContain('Loaded technician attention')
    expect(transcript.textContent).not.toContain('Updated table')
    expect(transcript.textContent).not.toContain('row(s)')
    expect(transcript.textContent).not.toContain('APPR')
    expect(screen.getByRole('heading', { name: 'Your Assigned Work' })).toBeInTheDocument()
    const welcomeTable = screen.getByLabelText('Your Assigned Work results table')
    expect(within(welcomeTable).getByText('WO-8304')).toBeInTheDocument()
    expect(within(welcomeTable).getByText('RM-DRIVE-01')).toBeInTheDocument()
    expect(within(welcomeTable).getByText('Approved')).toBeInTheDocument()
    expect(within(welcomeTable).queryByText('APPR')).not.toBeInTheDocument()
  })

  it('loads selected material-blocked technician context from Neo instead of a static start message', async () => {
    apiWorkOrders = [
      {
        ...(workOrders[0] as WorkOrder),
        status: 'WMATL',
        material_readiness: 'blocked',
        material_blocker_status: 'blocked',
        material_blocker_note: 'Drive end bearing is out of stock.',
        spare_reservations: [
          {
            ...(workOrders[0].spare_reservations[0]),
            reserved_qty: 0,
            available_qty: 0,
            procurement_status: 'requested',
            expected_available_date: '2026-07-03',
            blocker_status: 'blocked',
            blocker_note: 'No bearing is available for replacement.',
          },
        ],
      },
    ]

    render(<App />)
    await signIn('technician@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])

    const transcript = screen.getByLabelText('Neo technician chat')
    expect(await within(transcript).findByText(/WO-8304 is waiting for material/)).toBeInTheDocument()
    expect(transcript.textContent).toContain('expected availability is 2026-07-03')
    expect(transcript.textContent).not.toContain('Let’s start the work order')
    expect(within(screen.getByLabelText('Technician execution workflow')).getByText('Waiting for material')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Start work' })).toBeDisabled()

    const initialContextCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => {
        if (!url.toString().includes('/api/work-orders/technician-assist/stream')) return false
        return JSON.parse((init?.body as string) ?? '{}').requested_step === 'initial_context'
      })
    expect(JSON.parse((initialContextCall?.[1] as RequestInit).body as string)).toEqual(
      expect.objectContaining({
        work_order_id: 'WO-8304',
        requested_step: 'initial_context',
      }),
    )
    expect(JSON.parse((initialContextCall?.[1] as RequestInit).body as string).observation).toContain(
      'Address Vinoth by name, not by role.',
    )
  })

  it('keeps waiting for technician initial context past 15 seconds while the stream is still pending', async () => {
    assistantResponseDelayMs = 20_000
    vi.useFakeTimers()
    render(<App />)
    await act(async () => {})
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'technician@plant.local' } })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.getByRole('button', { name: 'Logout' })).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(within(screen.getByLabelText('Neo technician chat')).getByText(/Thinking/)).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(7_100)
    })
    expect(
      within(screen.getByLabelText('Neo technician chat')).getByText(/Waiting for the LLM response/),
    ).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8_100)
    })
    const transcript = screen.getByLabelText('Neo technician chat')
    expect(
      within(transcript).queryByText(/could not get a live LLM response within \d+ seconds/),
    ).not.toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000)
      await Promise.resolve()
    })
    expect(transcript.textContent).toContain('Vinoth, WO-8304')
  })

  it('keeps waiting for a submitted technician query past 15 seconds while the stream is still pending', async () => {
    render(<App />)
    await signIn('technician@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    expect(await within(screen.getByLabelText('Neo technician chat')).findByText(/approved and ready for technician execution/)).toBeInTheDocument()

    vi.useFakeTimers()
    assistantResponseDelayMs = 20_000
    fireEvent.change(screen.getByLabelText('Technician observation'), {
      target: { value: 'Connections 3 and 5 were loose.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Neo technician chat')).getByText('Connections 3 and 5 were loose.')).toBeInTheDocument()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_100)
    })

    const transcript = screen.getByLabelText('Neo technician chat')
    expect(within(transcript).queryByText(/could not get a live LLM response within \d+ seconds/)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_100)
      await Promise.resolve()
    })

    expect(transcript.textContent).toContain('Neo recommends verifying torque')
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it('falls back when a submitted technician query receives no LLM token within the stream timeout', async () => {
    render(<App />)
    await signIn('technician@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    expect(await within(screen.getByLabelText('Neo technician chat')).findByText(/approved and ready for technician execution/)).toBeInTheDocument()

    vi.useFakeTimers()
    assistantResponseDelayMs = 70_000
    fireEvent.change(screen.getByLabelText('Technician observation'), {
      target: { value: 'Connections 3 and 5 were loose.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_100)
    })

    const transcript = screen.getByLabelText('Neo technician chat')
    expect(within(transcript).getByText(/could not get a live LLM response within 60 seconds/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Send' })).toBeEnabled()
  })

  it('formats Markdown-like Neo responses into readable sections', async () => {
    render(<App />)
    await signIn()
    fireEvent.click(await screen.findByRole('button', { name: 'Command Center' }))

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
    fireEvent.click(await screen.findByText('Run Morpheus'))

    expect(await screen.findByText(/Morpheus is diagnosing/)).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getAllByText('Reduce load or schedule controlled shutdown.').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Trend the abnormal signal.')).toBeInTheDocument()
    expect(screen.getByText('23 days')).toBeInTheDocument()
    expect(screen.getByText('77%')).toBeInTheDocument()
    expect(screen.getByText('Hot Strip Mill Main Drive Vibration SOP')).toBeInTheDocument()
    const recommendationHeading = screen.getByRole('heading', { name: 'Recommendation' })
    const diagnosisHeading = screen.getByRole('heading', { name: 'Diagnosis and recommendation' })
    expect(Boolean(diagnosisHeading.compareDocumentPosition(recommendationHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(screen.queryByRole('heading', { name: 'Engineer Query' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /export report/i })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: /create work order/i }).length).toBeGreaterThan(0)
  })

  it('stores detailed engineer feedback for learning', async () => {
    render(<App />)
    await signIn()

    const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText('Hot Strip Mill Main Drive Motor').closest('button')
    if (!assetButton) throw new Error('Missing asset button')
    fireEvent.click(assetButton)
    fireEvent.click(await screen.findByText('Run Morpheus'))
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

  it('hides non-applicable work order assistant panels from admin users', async () => {
    render(<App />)
    await signIn()

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    expect(await screen.findByText('Assigned and follow-up work')).toBeInTheDocument()
    const centerPane = screen.getByLabelText('Work order center pane')
    const rightPane = screen.getByLabelText('Work order right pane')
    expect(screen.getByText('Work Order 8304')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Neo' })).not.toBeInTheDocument()
    const workOrdersHeading = screen.getByRole('heading', { name: 'Assigned and follow-up work' })
    expect(workOrdersHeading).toBeInTheDocument()
    expect(within(centerPane).queryByText('Neo is available to technician and supervisor accounts.')).not.toBeInTheDocument()
    expect(within(centerPane).queryByText('Select a work order to use the assistant.')).not.toBeInTheDocument()
    expect(within(rightPane).queryByText('Neo is available to technician and supervisor accounts.')).not.toBeInTheDocument()

    expect(screen.queryByLabelText('Assign WO-8297')).not.toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: 'Planning' }))
    expect(await screen.findByText('Planning backlog')).toBeInTheDocument()
    expect(screen.queryByLabelText('Work order right pane')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve WO-8297' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve WO-8275' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Approve WO-8297' }))
    await screen.findByText('WO-8297 approved')
    const approveCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => url.toString().includes('/api/work-orders/WO-8297') && init?.method === 'PATCH')
    expect(JSON.parse((approveCall?.[1] as RequestInit).body as string)).toEqual({ status: 'APPR' })

    fireEvent.change(screen.getByLabelText('Assign WO-8297'), { target: { value: 'Vinoth' } })
    await screen.findByText('WO-8297 assigned to Vinoth')
    const assignCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => {
        if (!url.toString().includes('/api/work-orders/WO-8297') || init?.method !== 'PATCH') return false
        return JSON.parse((init.body as string) ?? '{}').assigned_to === 'Vinoth'
      })
    expect(JSON.parse((assignCall?.[1] as RequestInit).body as string)).toEqual({ assigned_to: 'Vinoth' })
  })

  it('lets planners schedule and dispatch approved work orders without assistant panels', async () => {
    render(<App />)
    await signIn('planner@plant.local')

    fireEvent.click(await screen.findByRole('button', { name: 'Planning' }))
    const centerPane = screen.getByLabelText('Work order center pane')
    expect(screen.queryByLabelText('Work order right pane')).not.toBeInTheDocument()
    const preventiveTab = within(centerPane).getByRole('tab', { name: 'Preventive plans' })
    const dispatchTab = within(centerPane).getByRole('tab', { name: 'Schedule & dispatch' })
    expect(preventiveTab).toHaveAttribute('aria-selected', 'true')
    expect(dispatchTab).toHaveAttribute('aria-selected', 'false')
    const pmPanel = await within(centerPane).findByLabelText('Preventive maintenance planning')
    expect(within(pmPanel).getByRole('heading', { name: 'Preventive Maintenance Plans' })).toBeInTheDocument()
    expect(document.getElementById('planning-tab-dispatch')).toHaveAttribute('hidden')
    expect(within(pmPanel).getByLabelText('Preventive maintenance plans')).toBeInTheDocument()
    expect(within(pmPanel).getByLabelText('Active preventive maintenance plan')).toBeInTheDocument()
    expect(within(pmPanel).getByLabelText('Active preventive maintenance plan')).toHaveTextContent('Existing blower PM plan')
    expect(within(pmPanel).getAllByText('Drive bearing and coupling health PM').length).toBeGreaterThanOrEqual(1)
    fireEvent.click(within(pmPanel).getByRole('button', { name: /Morpheus PM draft/i }))
    expect(await within(pmPanel).findByRole('heading', { name: 'Morpheus PM live draft' })).toBeInTheDocument()
    expect(await within(pmPanel).findByText('Monitoring Thresholds')).toBeInTheDocument()
    await waitFor(() => {
      expect(within(pmPanel).getByLabelText('Active preventive maintenance plan')).toHaveTextContent('Main drive proactive PM plan')
    })
    expect((await within(pmPanel).findAllByText('Main drive proactive PM plan')).length).toBeGreaterThanOrEqual(2)
    expect(within(pmPanel).getAllByText('drive_end_vibration >= 7.1 mm/s').length).toBeGreaterThanOrEqual(2)
    expect(within(pmPanel).getByText('Confirm LOTO and permits.')).toBeInTheDocument()
    const pmPlanTable = within(pmPanel).getByLabelText('Preventive maintenance plans')
    fireEvent.click(within(pmPlanTable).getByRole('button', { name: 'Select' }))
    expect(within(pmPanel).getByLabelText('Active preventive maintenance plan')).toHaveTextContent('Existing blower PM plan')
    fireEvent.click(within(pmPanel).getByRole('button', { name: 'Convert to planned work' }))
    await within(pmPanel).findByText(/Created WO-/)

    fireEvent.click(dispatchTab)
    expect(preventiveTab).toHaveAttribute('aria-selected', 'false')
    expect(dispatchTab).toHaveAttribute('aria-selected', 'true')
    expect(document.getElementById('planning-tab-preventive')).toHaveAttribute('hidden')
    const dispatchBoard = await within(centerPane).findByLabelText('Maintenance planning and dispatch board')
    expect(within(dispatchBoard).getByRole('heading', { name: 'Planning, Scheduling & Dispatch' })).toBeInTheDocument()
    expect(within(centerPane).queryByRole('heading', { name: 'Neo' })).not.toBeInTheDocument()

    const workOrderPicker = within(dispatchBoard).getByLabelText('Select work order for planning')
    expect(workOrderPicker).toBeInTheDocument()
    fireEvent.change(workOrderPicker, { target: { value: 'WO-8304' } })

    const plannerCard = within(dispatchBoard).getByLabelText('WO-8304 planner card')
    expect(within(dispatchBoard).queryByLabelText('WO-8311 planner card')).not.toBeInTheDocument()
    expect(within(plannerCard).getByText('Planned')).toBeInTheDocument()
    expect(within(plannerCard).getByDisplayValue('Vinoth')).toBeInTheDocument()
    expect(within(plannerCard).getByLabelText('Planned start WO-8304')).toHaveAttribute('type', 'datetime-local')
    expect(within(plannerCard).getByLabelText('Planned start WO-8304')).not.toHaveAttribute('placeholder')
    expect(within(plannerCard).getByLabelText('Spare availability WO-8304')).toBeInTheDocument()
    expect(within(plannerCard).getByDisplayValue('Drive end spherical roller bearing')).toBeInTheDocument()
    expect(within(plannerCard).getByLabelText('Material blocker WO-8304')).toHaveValue('reserved')

    fireEvent.change(within(plannerCard).getByLabelText('Planned start WO-8304'), {
      target: { value: '2026-06-12T15:00' },
    })
    fireEvent.change(within(plannerCard).getByLabelText('Material readiness WO-8304'), {
      target: { value: 'ready' },
    })
    fireEvent.change(within(plannerCard).getByLabelText('Procurement status WO-8304 1'), {
      target: { value: 'ordered' },
    })
    fireEvent.click(within(plannerCard).getByLabelText('Reorder requested WO-8304 1'))
    fireEvent.click(within(plannerCard).getByRole('button', { name: 'Save plan' }))
    await screen.findByText('WO-8304 planning saved')

    const planCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => {
        if (!url.toString().includes('/api/work-orders/WO-8304') || init?.method !== 'PATCH') return false
        const body = JSON.parse((init.body as string) ?? '{}')
        return body.planned_start === '2026-06-12T15:00'
      })
    expect(JSON.parse((planCall?.[1] as RequestInit).body as string)).toMatchObject({
      assigned_to: 'Vinoth',
      planning_status: 'planned',
      planned_start: '2026-06-12T15:00',
      material_readiness: 'ready',
      material_blocker_status: 'reserved',
      spare_reservations: [
        expect.objectContaining({
          spare_name: 'Drive end spherical roller bearing',
          procurement_status: 'ordered',
          reorder_requested: true,
          blocker_status: 'reserved',
        }),
      ],
    })

    fireEvent.click(within(plannerCard).getByRole('button', { name: /dispatch/i }))
    await screen.findByText('WO-8304 dispatched')
    const dispatchCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => {
        if (!url.toString().includes('/api/work-orders/WO-8304') || init?.method !== 'PATCH') return false
        return JSON.parse((init.body as string) ?? '{}').planning_status === 'dispatched'
    })
    expect(JSON.parse((dispatchCall?.[1] as RequestInit).body as string)).toEqual({ planning_status: 'dispatched' })
  })

  it('keeps the PM plans table visible when no plans are loaded', async () => {
    apiPmPlans = []
    render(<App />)
    await signIn('planner@plant.local')

    fireEvent.click(await screen.findByRole('button', { name: 'Planning' }))
    const centerPane = screen.getByLabelText('Work order center pane')
    const pmPanel = await within(centerPane).findByLabelText('Preventive maintenance planning')
    const pmPlanTable = within(pmPanel).getByLabelText('Preventive maintenance plans')

    expect(within(pmPanel).queryByLabelText('Active preventive maintenance plan')).not.toBeInTheDocument()
    expect(within(pmPanel).getByText('0 plans')).toBeInTheDocument()
    expect(within(pmPlanTable).getByRole('columnheader', { name: 'Plan' })).toBeInTheDocument()
    expect(within(pmPlanTable).getByText('No PM plans generated yet. Draft one from asset risk prediction and a PM template.')).toBeInTheDocument()
  })

  it('shows only the technician LLM assistant to technician users', async () => {
    assistantResponseDelayMs = 300
    render(<App />)
    await signIn('technician@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    expect(await screen.findByText('Assigned and follow-up work')).toBeInTheDocument()
    const centerPane = screen.getByLabelText('Work order center pane')
    const rightPane = screen.getByLabelText('Work order right pane')
    const neoHeading = within(centerPane).getByRole('heading', { name: 'Neo' })
    const workOrdersHeading = screen.getByRole('heading', { name: 'Assigned and follow-up work' })
    expect(neoHeading).toBeInTheDocument()
    expect(Boolean(neoHeading.compareDocumentPosition(workOrdersHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(within(centerPane).getByText('Technician AI assistant with shared LLM configuration')).toBeInTheDocument()
    expect(within(centerPane).getByRole('heading', { name: 'Assigned Schedule' })).toBeInTheDocument()
    expect(within(centerPane).queryByLabelText('Maintenance planning and dispatch board')).not.toBeInTheDocument()
    expect(within(rightPane).queryByRole('heading', { name: 'Neo' })).not.toBeInTheDocument()
    const executionWorkflow = within(centerPane).getByLabelText('Technician execution workflow')
    expect(within(executionWorkflow).getByRole('heading', { name: 'Technician Execution' })).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('Approved')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('The work order is approved and ready for technician execution.')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('1')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('Confirm readiness')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('Start field execution')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('Capture observations')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('Apply guided action')).toBeInTheDocument()
    expect(within(executionWorkflow).getByText('Submit completion')).toBeInTheDocument()
    expect(within(centerPane).getByRole('button', { name: 'WO-8304' })).toBeInTheDocument()
    expect(within(centerPane).queryByRole('button', { name: 'WO-8297' })).not.toBeInTheDocument()
    expect(await within(screen.getByLabelText('Neo technician chat')).findByText(/approved and ready for technician execution/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Start WO-8304' }))
    await screen.findByText('WO-8304 started')
    expect(await within(screen.getByLabelText('Technician execution workflow')).findByText('In progress')).toBeInTheDocument()
    const startCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => url.toString().includes('/api/work-orders/WO-8304') && init?.method === 'PATCH')
    expect(JSON.parse((startCall?.[1] as RequestInit).body as string)).toEqual({ status: 'INPRG' })

    fireEvent.change(screen.getByLabelText('Technician observation'), {
      target: { value: 'Connections 3 and 5 were loose.' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Neo technician chat')).getByText('Connections 3 and 5 were loose.')).toBeInTheDocument()
    expect(await within(screen.getByLabelText('Neo technician chat')).findByText(/Thinking/)).toBeInTheDocument()
    expect(await within(screen.getByLabelText('Neo technician chat')).findByText(/Neo recommends verifying torque/)).toBeInTheDocument()
    const updatedWorkflow = screen.getByLabelText('Technician execution workflow')
    expect(await within(updatedWorkflow).findByText('Set problem code LWTQCONNECT.')).toBeInTheDocument()
    expect(within(updatedWorkflow).getByText(/Connections were tightened to spec./)).toBeInTheDocument()
    expect(screen.getByLabelText('Neo technician chat').textContent).not.toContain('Verify torque on bolted connections.')
    expect(screen.getByLabelText('Neo technician chat').textContent).not.toContain('Problem code: LWTQCONNECT')
    expect(screen.getAllByText('LLM fallback · mock').length).toBeGreaterThanOrEqual(1)
    const submitCompleted = within(updatedWorkflow).getByRole('button', { name: 'Submit completed work' })
    expect(submitCompleted).toBeEnabled()
  })

  it('shows only the supervisor LLM assistant to supervisor users', async () => {
    assistantResponseDelayMs = 300
    render(<App />)
    await signIn('supervisor@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    expect(await screen.findByText('Assigned and follow-up work')).toBeInTheDocument()
    const centerPane = screen.getByLabelText('Work order center pane')
    const rightPane = screen.getByLabelText('Work order right pane')
    const neoHeading = within(centerPane).getByRole('heading', { name: 'Neo' })
    const workOrdersHeading = screen.getByRole('heading', { name: 'Assigned and follow-up work' })
    expect(neoHeading).toBeInTheDocument()
    expect(Boolean(neoHeading.compareDocumentPosition(workOrdersHeading) & Node.DOCUMENT_POSITION_FOLLOWING)).toBe(true)
    expect(within(centerPane).getByText('Supervisor AI assistant with shared LLM configuration')).toBeInTheDocument()
    expect(within(rightPane).queryByRole('heading', { name: 'Neo' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Assign WO-8304')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Approve WO-8297' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Approve WO-8275' })).not.toBeInTheDocument()
    expect(await within(screen.getByLabelText('Neo supervisor chat')).findByText(/Neo reviewed 2 work orders/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(within(screen.getByLabelText('Neo supervisor chat')).getByText('Summarize follow-up actions for completed work orders.')).toBeInTheDocument()
    expect(await within(screen.getByLabelText('Neo supervisor chat')).findByText(/Thinking/)).toBeInTheDocument()
    expect(await screen.findByText(/Neo reviewed 2 work orders/)).toBeInTheDocument()
    const supervisorTranscript = screen.getByLabelText('Neo supervisor chat')
    expect(supervisorTranscript.textContent).not.toContain('Review WO-8297 brake shoe replacement planning.')
    expect(supervisorTranscript.textContent).not.toContain('Risk: WO-8304 remains priority 1 and Approved.')
    expect(supervisorTranscript.textContent).not.toContain('APPR')
    expect(screen.getByText('LLM fallback · mock')).toBeInTheDocument()
  })

  it('routes supervisor approval questions to the waiting approval queue', async () => {
    render(<App />)
    await signIn('supervisor@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    const transcript = await screen.findByLabelText('Neo supervisor chat')
    expect(await within(transcript).findByText(/Neo reviewed 2 work orders/)).toBeInTheDocument()
    expect(supervisorAssistantRequests[0].question).toContain('Address Dhruv by name, not by role.')

    const question = 'what are the work orders pending for my approval'
    fireEvent.change(screen.getByLabelText('Supervisor question'), { target: { value: question } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await within(transcript).findByText(/waiting for approval: WO-8311/i)).toBeInTheDocument()
    expect(supervisorAssistantRequests[supervisorAssistantRequests.length - 1]).toMatchObject({
      queue_name: 'waiting_approval',
      question,
    })
  })

  it('lets supervisor Neo approve an explicit work order command through the action tool', async () => {
    render(<App />)
    await signIn('supervisor@plant.local')

    fireEvent.click((await screen.findAllByRole('button', { name: 'Work Execution' }))[0])
    const transcript = await screen.findByLabelText('Neo supervisor chat')
    expect(await within(transcript).findByText(/Neo reviewed 2 work orders/)).toBeInTheDocument()
    const assistantRequestCount = supervisorAssistantRequests.length

    fireEvent.change(screen.getByLabelText('Supervisor question'), { target: { value: 'Approve WO-8311' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(await within(transcript).findByText(/Dhruv, approved WO-8311/)).toBeInTheDocument()
    expect(within(transcript).getByText('Neo action')).toBeInTheDocument()
    expect(supervisorAssistantRequests).toHaveLength(assistantRequestCount)
    expect(await screen.findByText('WO-8311 approved')).toBeInTheDocument()
    const approveCall = vi
      .mocked(fetch)
      .mock.calls.find(([url, init]) => url.toString().includes('/api/work-orders/WO-8311') && init?.method === 'PATCH')
    expect(JSON.parse((approveCall?.[1] as RequestInit).body as string)).toEqual({ status: 'APPR' })
  })

  it('logs out immediately even when the logout API is slow', async () => {
    logoutResponseDelayMs = 60_000
    render(<App />)
    await signIn('supervisor@plant.local')

    expect(await screen.findByRole('button', { name: 'Logout' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Logout' }))

    expect(await screen.findByRole('button', { name: /sign in/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Logout' })).not.toBeInTheDocument()
  })

  it('uploads document files from the ingestion panel', async () => {
    ingestionResponseDelayMs = 100
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    expect(await screen.findByText('IoT Stream')).toBeInTheDocument()
    expect(screen.getByText('MW_IOT')).toBeInTheDocument()
    const file = new File(['Inspect bearing housing when vibration increases.'], 'uploaded_sop.txt', { type: 'text/plain' })
    fireEvent.change(await screen.findByLabelText('Ingestion file'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: /upload/i }))
    expect(screen.getByRole('button', { name: /uploading/i })).toBeDisabled()

    await waitFor(() => {
      expect(screen.getByText(/Stored 1 document and extracted/)).toBeInTheDocument()
    })
    expect(screen.getByText(/Stored 1 document and extracted/).closest('.toastMessage')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /uploading/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^upload$/i })).not.toBeDisabled()
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/ingest/document-file',
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    )
  })

  it('uploads every bundled ingestion sample file with the intended source type and asset', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    expect(await screen.findByText('IoT Stream')).toBeInTheDocument()

    for (const sample of sampleFiles) {
      const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText(sample.assetName).closest('button')
      if (!assetButton) {
        throw new Error(`Missing asset button for ${sample.assetName}`)
      }
      fireEvent.click(assetButton)
      fireEvent.click(screen.getByRole('button', { name: 'Admin' }))
      fireEvent.change(screen.getByLabelText('Source'), { target: { value: sample.sourceType } })
      const content = readFileSync(sample.path, 'utf8')
      const file = new File([content], sample.fileName, { type: sample.mimeType })
      fireEvent.change(screen.getByLabelText('Ingestion file'), { target: { files: [file] } })
      fireEvent.click(screen.getByRole('button', { name: /upload/i }))

      await waitFor(() => {
        expect(screen.getAllByText(/Stored 1 document and extracted/).length).toBeGreaterThan(0)
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
    ingestionResponseDelayMs = 100
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    fireEvent.change(await screen.findByLabelText('Ingestion JSON'), {
      target: {
        value:
          '{"documents":[{"id":"DOC-UI","source_type":"sop","equipment_id":"RM-DRIVE-01","title":"UI SOP","content":"Check vibration."}]}',
      },
    })
    fireEvent.click(screen.getByRole('button', { name: /import json/i }))
    expect(screen.getByRole('button', { name: /importing/i })).toBeDisabled()

    await waitFor(() => {
      expect(screen.getByText(/Stored 1 document and extracted/)).toBeInTheDocument()
    })
    expect(screen.getByText(/Stored 1 document and extracted/).closest('.toastMessage')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /importing/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /import json/i })).not.toBeDisabled()
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/ingest/documents',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('lets reviewers score and export LLM-as-a-Judge learning examples', async () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView

    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Reliability' }))

    expect(await screen.findByRole('heading', { name: 'RCA Workspace' })).toBeInTheDocument()
    const rcaWorkspace = screen.getByLabelText('RCA workspace')
    expect(within(rcaWorkspace).getByRole('heading', { name: 'Work order context' })).toBeInTheDocument()
    expect(within(rcaWorkspace).getByRole('heading', { name: 'RCA case' })).toBeInTheDocument()
    expect(within(rcaWorkspace).getByRole('heading', { name: 'Review actions' })).toBeInTheDocument()
    await waitFor(() => expect(within(rcaWorkspace).getByLabelText('Work order')).toHaveValue('WO-8304'))
    expect(within(rcaWorkspace).getByLabelText('Selected RCA case')).toHaveValue('RCA-9001')
    expect(within(rcaWorkspace).getByRole('button', { name: 'RCA case selected' })).toBeDisabled()
    fireEvent.change(within(rcaWorkspace).getByLabelText('Work order'), { target: { value: 'WO-8297' } })
    expect(within(rcaWorkspace).getByLabelText('Selected RCA case')).toHaveValue('')
    expect(within(rcaWorkspace).getByRole('button', { name: 'Create RCA for work order' })).toBeEnabled()
    fireEvent.change(within(rcaWorkspace).getByLabelText('Work order'), { target: { value: 'WO-8304' } })
    await waitFor(() => expect(within(rcaWorkspace).getByLabelText('Selected RCA case')).toHaveValue('RCA-9001'))
    expect(screen.getByText('Drive-end vibration root cause review')).toBeInTheDocument()
    expect(screen.getAllByText('Drive-end bearing wear or coupling looseness under load').length).toBeGreaterThan(0)
    expect(screen.getByText('5-Why')).toBeInTheDocument()
    expect(screen.getByText('Fishbone')).toBeInTheDocument()
    expect(screen.getByText('Evidence Timeline')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Learning and Tuning' })).not.toBeInTheDocument()
    fireEvent.click(within(rcaWorkspace).getByRole('button', { name: 'Morpheus draft selected RCA' }))
    expect(await screen.findByRole('heading', { name: 'Morpheus live draft' })).toBeInTheDocument()
    expect(await screen.findByText('Drive-end bearing looseness remains the leading candidate.')).toBeInTheDocument()
    expect(await screen.findAllByText('Seal flush strainer restriction (Primary cause)')).toHaveLength(2)
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledWith({ block: 'end' }))
    expect(
      await screen.findByText('Morpheus drafted RCA hypotheses, evidence, missing checks, and corrective actions. Provider: live openai.'),
    ).toBeInTheDocument()
    fireEvent.click(within(rcaWorkspace).getByRole('button', { name: 'Close selected RCA and learn' }))
    expect(await screen.findByText('RCA-9001 closed and accepted for learning')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Admin' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'Learning and Tuning' }))
    expect(await screen.findByRole('heading', { name: 'Learning and Tuning' })).toBeInTheDocument()
    expect(screen.getByText(/Review approved human feedback/)).toBeInTheDocument()
    expect(screen.getByText('RAG vector DB')).toBeInTheDocument()
    expect(screen.getByText('qdrant · ready')).toBeInTheDocument()
    expect(screen.getByText('Active embedding')).toBeInTheDocument()
    expect(screen.getByText('deterministic_hash · maintenance-hash-v1 · v1')).toBeInTheDocument()
    expect(screen.getByText('Embedding profile')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preview migration' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run Qdrant migration' })).toBeInTheDocument()
    expect(screen.getByText('Migration')).toBeInTheDocument()
    expect(screen.getByText('Current')).toBeInTheDocument()
    expect(screen.getByText('Serving LLM')).toBeInTheDocument()
    expect(screen.getByText('learning active model · openai')).toBeInTheDocument()
    expect(screen.getByText('model-local-qwen2.5-current')).toBeInTheDocument()
    expect(screen.getByText('Artifact store')).toBeInTheDocument()
    expect(screen.getByText('filesystem · ready')).toBeInTheDocument()
    expect(screen.getByText('disabled · 7 days')).toBeInTheDocument()
    expect(screen.getByText('PEFT trainer')).toBeInTheDocument()
    expect(screen.getByText('prepared_artifacts · not configured')).toBeInTheDocument()
    expect(screen.getByText('82% · training worthy')).toBeInTheDocument()
    expect(screen.getByText('Live LLM judge · openai')).toBeInTheDocument()
    expect(screen.getByText(/Specific, outcome-backed feedback/)).toBeInTheDocument()
    expect(screen.getByText('Passed')).toBeInTheDocument()
    expect(screen.getByText('Quality')).toBeInTheDocument()
    expect(screen.getByText('dataset snapshot')).toBeInTheDocument()
    expect(screen.getByText(/completed ·/)).toBeInTheDocument()
    expect(screen.getByText('peft training manifest')).toBeInTheDocument()
    expect(screen.getByText('sha256 abcdef123456')).toBeInTheDocument()
    expect(screen.getByText('Promotion Audit')).toBeInTheDocument()
    expect(screen.getByText('Adapter promoted')).toBeInTheDocument()
    expect(screen.getByText(/Promotion gate passed by evaluation LEVAL-1/)).toBeInTheDocument()
    expect(screen.getByText(/Verified deployment qwen2\.5-7b-instruct-lora-candidate · openai/)).toBeInTheDocument()
    expect(screen.getByText('Adapter Runtime Deployments')).toBeInTheDocument()
    expect(screen.getByText('verified')).toBeInTheDocument()
    expect(screen.getByText('health healthy')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Preview cleanup' }))
    expect(await screen.findByText('Artifact cleanup preview found 1 eligible and 1 protected artifact(s).')).toBeInTheDocument()
    expect(screen.getByText('Artifact lifecycle preview')).toBeInTheDocument()
    expect(screen.getByText('LJOB-OLD/dataset.jsonl')).toBeInTheDocument()
    expect(screen.getByText('active/candidate/promoted model reference')).toBeInTheDocument()
    expect(learningArtifactCleanupRequests.at(-1)).toMatchObject({ dry_run: true })

    fireEvent.click(screen.getByRole('button', { name: 'Judge' }))
    expect(await screen.findByText('Judge scored feedback at 91%')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Remove approval' }))
    expect(await screen.findByText('feedback example removed from approved set')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh examples' }))
    expect(await screen.findByText('Refreshed 1 learning example')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Create JSONL snapshot' }))
    expect(await screen.findByText('Created dataset snapshot with 1 approved example')).toBeInTheDocument()
    expect(screen.getByText('Latest dataset snapshot')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Download JSONL' })).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'JSONL' }).length).toBeGreaterThan(0)

    fireEvent.change(screen.getByLabelText('Adapter path'), { target: { value: 'file:///models/qwen2.5-lora' } })
    fireEvent.click(screen.getByRole('button', { name: 'Register adapter' }))
    expect(await screen.findByText('Registered adapter candidate qwen2.5-7b-instruct-lora-candidate')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Run dataset evaluation' }))
    expect(await screen.findByText('Evaluation passed with quality 0.81')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Queue PEFT tuning job' }))
    expect(await screen.findByText('Queued PEFT tuning job LJOB-PEFT-1 with status queued')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Runtime provider'), { target: { value: 'vllm' } })
    fireEvent.change(screen.getByLabelText('Runtime base URL'), { target: { value: 'http://localhost:8001/v1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Deploy adapter' }))
    expect(await screen.findByText('Deployment job LJOB-DEPLOY-1 requested with status queued')).toBeInTheDocument()
    expect(await screen.findByText('deploying')).toBeInTheDocument()
    expect(screen.getByText('health pending')).toBeInTheDocument()
    const deployCall = [...vi.mocked(fetch).mock.calls]
      .reverse()
      .find(([url]) => url.toString().endsWith('/api/learning/model-versions/model-adapter-candidate/deploy'))
    expect(JSON.parse((deployCall?.[1]?.body as string) ?? '{}')).toMatchObject({
      runtime_provider: 'vllm',
      served_model_name: 'qwen2.5-7b-instruct-lora-candidate',
      base_url: 'http://localhost:8001/v1',
      artifact_uri: 'file:///models/qwen2.5-lora',
    })

    fireEvent.click(screen.getByRole('button', { name: 'Preview migration' }))
    expect(await screen.findByText('Previewed RAG migration to maintenance_wizard_documents_v1')).toBeInTheDocument()
    expect(screen.getByText('Migration preview')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Reindex current profile' }))
    expect(
      await screen.findByText('Reindexed 14 RAG chunks and synced 1 approved learning example (synced) with status completed'),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Promote adapter' }))
    expect(await screen.findByText('Promoted adapter qwen2.5-7b-instruct-lora-candidate with audit record LPROMO-NEW')).toBeInTheDocument()
  }, 10_000)

  it('explains when refreshing learning examples finds no training sources', async () => {
    learningSummaryExamples = []
    learningRefreshExamples = []

    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'Learning and Tuning' }))
    expect(await screen.findByRole('heading', { name: 'Learning and Tuning' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Refresh examples' }))

    expect(
      await screen.findByText(
        'Refresh completed, but no learning examples were found. Add accepted feedback, usable maintenance labels, completed work orders, closed RCA cases, ingested documents, or approved assistant interactions, then refresh again.',
      ),
    ).toBeInTheDocument()
  })

  it('shows progress while a learning example is being judged', async () => {
    learningJudgeDelayMs = 250

    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'Learning and Tuning' }))
    expect(await screen.findByRole('heading', { name: 'Learning and Tuning' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Judge' }))

    expect(await screen.findByRole('button', { name: 'Judging...' })).toBeDisabled()
    expect(screen.getByText('Judging feedback example. Live LM Studio checks can take up to 15 seconds before falling back.')).toBeInTheDocument()
    expect(await screen.findByText('Judge scored feedback at 91%')).toBeInTheDocument()
  })

  it('keeps Learning and Tuning inside Admin instead of reliability navigation', async () => {
    render(<App />)
    await signIn('reliability@plant.local')

    expect(await screen.findByRole('button', { name: 'Reliability' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Learning and Tuning' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Admin' })).not.toBeInTheDocument()
  })

  it('hides restricted actions for operators', async () => {
    render(<App />)
    await signIn('operator@plant.local')

    expect(screen.getByText('Jan')).toBeInTheDocument()
    const navigation = screen.getByLabelText('Maintenance navigation')
    expect(within(navigation).getByRole('button', { name: 'Command Center' })).toBeInTheDocument()
    expect(within(navigation).getByRole('button', { name: 'Assets' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Admin' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reliability' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Learning and Tuning' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Planning' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Work Execution' })).not.toBeInTheDocument()
    expect(screen.queryByText('Run Morpheus')).not.toBeInTheDocument()
    expect(screen.queryByText('Engineer Query')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /create work order/i })).not.toBeInTheDocument()

    const assetButton = within(screen.getByLabelText('Tracked priority assets')).getByText('Hot Strip Mill Main Drive Motor').closest('button')
    if (!assetButton) throw new Error('Missing asset button')
    fireEvent.click(assetButton)
    expect(await screen.findByRole('heading', { name: 'Hot Strip Mill Main Drive Motor' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /create work order/i })).not.toBeInTheDocument()
  })

  it('lets admins open the users view and create a user', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    expect(await screen.findByRole('tab', { name: 'Ingestion' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'User management' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tab', { name: 'Learning and Tuning' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('heading', { name: 'Ingestion' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: 'User management' }))
    expect(screen.getByRole('tab', { name: 'User management' })).toHaveAttribute('aria-selected', 'true')
    expect(await screen.findByText('Jan')).toBeInTheDocument()
    expect(screen.queryByRole('dialog', { name: 'Create User' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Create User' }))
    const dialog = await screen.findByRole('dialog', { name: 'Create User' })
    fireEvent.change(within(dialog).getByLabelText('Email'), { target: { value: 'new.operator@plant.local' } })
    fireEvent.change(within(dialog).getByLabelText('Name'), { target: { value: 'New Operator' } })
    fireEvent.change(within(dialog).getByLabelText('Password'), { target: { value: 'NewOperator123!' } })

    expect(
      vi.mocked(fetch).mock.calls.some(([url, init]) => url.toString().endsWith('/api/users') && init?.method === 'POST'),
    ).toBe(false)

    fireEvent.click(within(dialog).getByRole('button', { name: 'Create' }))

    await waitFor(() => {
      expect(screen.getByText('User created')).toBeInTheDocument()
    })
    expect(screen.queryByRole('dialog', { name: 'Create User' })).not.toBeInTheDocument()
  })

  it('opens password reset in a dialog instead of inline user rows', async () => {
    render(<App />)
    await signIn()

    fireEvent.click(await screen.findByRole('button', { name: 'Admin' }))
    fireEvent.click(await screen.findByRole('tab', { name: 'User management' }))
    expect(await screen.findByText('Jan')).toBeInTheDocument()

    expect(screen.queryByLabelText('New Password')).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByRole('button', { name: 'Reset' })[0])

    expect(await screen.findByRole('dialog', { name: 'Reset Password' })).toBeInTheDocument()
    expect(screen.getByLabelText('New Password')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.queryByRole('dialog', { name: 'Reset Password' })).not.toBeInTheDocument()
  })
})
