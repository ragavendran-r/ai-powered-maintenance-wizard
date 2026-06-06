export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export interface Equipment {
  id: string
  name: string
  area: string
  process: string
  criticality: number
  status: string
}

export interface Alert {
  id: string
  equipment_id: string
  timestamp: string
  signal: string
  value: number
  unit: string
  threshold: number
  severity: RiskLevel
  message: string
}

export interface Evidence {
  source_type: string
  source_id: string
  title: string
  excerpt: string
  equipment_id?: string
  timestamp?: string
}

export interface SparePart {
  id: string
  equipment_id: string
  name: string
  available_qty: number
  lead_time_days: number
  criticality: number
}

export interface AnomalyFinding {
  equipment_id: string
  signal: string
  timestamp: string
  value: number
  unit: string
  baseline_mean: number
  z_score: number
  threshold: number
  threshold_breached: boolean
  trend_delta: number
  risk_level: RiskLevel
  explanation: string
}

export interface HealthSummary {
  equipment: Equipment
  risk_level: RiskLevel
  health_score: number
  active_alerts: Alert[]
  anomalies: AnomalyFinding[]
  top_spares_constraints: SparePart[]
  notes: string[]
}

export interface DashboardSummary {
  equipment_count: number
  active_alert_count: number
  critical_alert_count: number
  average_health_score: number
  highest_risk_equipment: HealthSummary[]
}

export interface Recommendation {
  id: string
  equipment_id: string
  diagnosis: string
  probable_root_causes: string[]
  risk_level: RiskLevel
  urgency: string
  remaining_useful_life_days: number | null
  confidence: number
  immediate_actions: string[]
  planned_actions: string[]
  spares_strategy: string[]
  evidence: Evidence[]
  report_summary: string
}

export interface ChatResponse {
  answer: string
  recommendation: Recommendation
  evidence: Evidence[]
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`)
  }
  return response.json() as Promise<T>
}

export const api = {
  equipment: () => request<Equipment[]>('/api/equipment'),
  dashboard: () => request<DashboardSummary>('/api/dashboard/summary'),
  health: (equipmentId: string) => request<HealthSummary>(`/api/equipment/${equipmentId}/health`),
  alerts: () => request<Alert[]>('/api/alerts'),
  diagnose: (equipmentId: string, alertId?: string) =>
    request<Recommendation>('/api/diagnose', {
      method: 'POST',
      body: JSON.stringify({ equipment_id: equipmentId, alert_id: alertId }),
    }),
  chat: (equipmentId: string, message: string) =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ equipment_id: equipmentId, message }),
    }),
  feedback: (recommendationId: string, status: 'accepted' | 'rejected' | 'corrected') =>
    request(`/api/recommendations/${recommendationId}/feedback`, {
      method: 'POST',
      body: JSON.stringify({ status }),
    }),
  reportMarkdownUrl: (equipmentId: string) => `${API_BASE}/api/reports/${equipmentId}/markdown`,
}

export const fallbackDashboard: DashboardSummary = {
  equipment_count: 3,
  active_alert_count: 3,
  critical_alert_count: 1,
  average_health_score: 45,
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
      health_score: 10,
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
          z_score: 7.2,
          threshold: 7.1,
          threshold_breached: true,
          trend_delta: 4.56,
          risk_level: 'critical',
          explanation: 'drive_end_vibration is critical risk against rolling baseline and threshold.',
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
      notes: ['Critical vibration alert and unavailable bearing spare require intervention planning.'],
    },
  ],
}
