from typing import Literal, Optional
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]


class Evidence(BaseModel):
    source_type: str
    source_id: str
    title: str
    excerpt: str
    equipment_id: Optional[str] = None
    timestamp: Optional[str] = None


class Equipment(BaseModel):
    id: str
    name: str
    area: str
    process: str
    criticality: int = Field(ge=1, le=5)
    status: str


class Alert(BaseModel):
    id: str
    equipment_id: str
    timestamp: str
    signal: str
    value: float
    unit: str
    threshold: float
    severity: RiskLevel
    message: str


class SparePart(BaseModel):
    id: str
    equipment_id: str
    name: str
    available_qty: int
    lead_time_days: int
    criticality: int = Field(ge=1, le=5)


class MaintenanceEvent(BaseModel):
    id: str
    equipment_id: str
    date: str
    issue: str
    root_cause: str
    action: str
    downtime_hours: float


class SensorReading(BaseModel):
    id: str
    equipment_id: str
    timestamp: str
    signal: str
    value: float
    unit: str
    threshold: float


class AnomalyFinding(BaseModel):
    equipment_id: str
    signal: str
    timestamp: str
    value: float
    unit: str
    baseline_mean: float
    z_score: float
    threshold: float
    threshold_breached: bool
    trend_delta: float
    risk_level: RiskLevel
    explanation: str


class HealthSummary(BaseModel):
    equipment: Equipment
    risk_level: RiskLevel
    health_score: int = Field(ge=0, le=100)
    active_alerts: list[Alert]
    anomalies: list[AnomalyFinding] = []
    top_spares_constraints: list[SparePart]
    notes: list[str]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    equipment_id: Optional[str] = None
    message: str
    history: list[ChatMessage] = []


class DiagnosisRequest(BaseModel):
    equipment_id: str
    alert_id: Optional[str] = None
    symptoms: Optional[str] = None


class PredictionRequest(BaseModel):
    equipment_id: str


class Recommendation(BaseModel):
    id: str
    equipment_id: str
    diagnosis: str
    probable_root_causes: list[str]
    risk_level: RiskLevel
    urgency: str
    remaining_useful_life_days: Optional[int]
    confidence: float = Field(ge=0, le=1)
    immediate_actions: list[str]
    planned_actions: list[str]
    spares_strategy: list[str]
    evidence: list[Evidence]
    report_summary: str


class ChatResponse(BaseModel):
    answer: str
    recommendation: Recommendation
    evidence: list[Evidence]


class PredictionResponse(BaseModel):
    equipment_id: str
    risk_level: RiskLevel
    failure_probability: float = Field(ge=0, le=1)
    remaining_useful_life_days: int
    drivers: list[str]


class FeedbackRequest(BaseModel):
    status: Literal["accepted", "rejected", "corrected"]
    corrected_diagnosis: Optional[str] = None
    actual_root_cause: Optional[str] = None
    action_taken: Optional[str] = None
    outcome: Optional[str] = None
    notes: Optional[str] = None


class FeedbackResponse(BaseModel):
    recommendation_id: str
    stored: bool
    message: str


class DashboardSummary(BaseModel):
    equipment_count: int
    active_alert_count: int
    critical_alert_count: int
    average_health_score: int
    highest_risk_equipment: list[HealthSummary]
