from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]
UserRole = Literal[
    "admin",
    "maintenance_engineer",
    "reliability_engineer",
    "planner",
    "operator",
    "iot_service",
]


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
    learning_notes: list[str] = []
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
    equipment_id: Optional[str] = None
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


IoTMessageType = Literal["equipment", "alert", "spare", "sensor_reading", "maintenance_event"]
StreamingState = Literal["disabled", "disconnected", "connected", "error"]


class IoTMessageEnvelope(BaseModel):
    message_id: str = Field(min_length=1)
    schema_version: str = "1"
    source: str = Field(min_length=1)
    type: IoTMessageType
    timestamp: str
    payload: dict[str, Any]


class StreamingStatus(BaseModel):
    enabled: bool
    state: StreamingState
    broker: str = "nats"
    stream: str
    consumer: str
    subjects: list[str]
    processed_count: int
    failed_count: int
    last_message_timestamp: Optional[str] = None
    last_error: Optional[str] = None


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str
    role: UserRole
    is_active: bool = True
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_login_at: Optional[str] = None


class LoginRequest(BaseModel):
    email: str = Field(min_length=3)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3)
    display_name: str = Field(min_length=1)
    role: UserRole
    password: str = Field(min_length=8)
    is_active: bool = True


class UserUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class PasswordResetRequest(BaseModel):
    password: str = Field(min_length=8)
