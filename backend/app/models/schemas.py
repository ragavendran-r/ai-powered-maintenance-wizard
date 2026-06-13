from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]
WorkOrderStatus = Literal["WAPPR", "WMATL", "APPR", "INPRG", "COMP", "CLOSE"]
WorkOrderAssistantAudience = Literal["technician", "supervisor"]
AnomalyContextClass = Literal[
    "requires_investigation",
    "startup_transient",
    "known_process_condition",
    "maintenance_induced",
    "normal_variation",
]
UserRole = Literal[
    "admin",
    "maintenance_engineer",
    "maintenance_technician",
    "maintenance_supervisor",
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
    relevance_reason: Optional[str] = None


class Equipment(BaseModel):
    id: str
    name: str
    area: str
    process: str
    criticality: int = Field(ge=1, le=5)
    status: str


class AssetProfile(BaseModel):
    equipment_id: str
    name: str
    area: str
    process: str
    criticality: int = Field(ge=1, le=5)
    status: str
    asset_type: str
    location_code: str
    location_name: str
    parent_system: str
    manufacturer: str
    model: str
    serial_number: str
    installed_at: str
    owner_team: str
    supervisor: str
    description: str
    last_updated: str


class AssetMetricSnapshot(BaseModel):
    id: str
    equipment_id: str
    metric_key: str
    label: str
    value: float
    unit: str
    target_value: Optional[float] = None
    status: str
    trend: str
    detail: str
    captured_at: str
    sort_order: int


class AssetRecommendation(BaseModel):
    id: str
    equipment_id: str
    action_type: str
    title: str
    description: str
    priority: int
    source: str
    created_at: str
    sort_order: int


class AssetSubsystem(BaseModel):
    id: str
    equipment_id: str
    name: str
    component: str
    condition: str
    detail: str
    sort_order: int


class AssetReliabilityMetric(BaseModel):
    id: str
    equipment_id: str
    metric_name: str
    value: float
    unit: str
    target_value: Optional[float] = None
    status: str
    trend: str
    detail: str
    sort_order: int


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


class WorkOrderLog(BaseModel):
    id: int
    work_order_id: str
    author: str
    entry_type: str
    content: str
    created_at: str


class WorkOrder(BaseModel):
    id: str
    equipment_id: str
    title: str
    description: str
    status: WorkOrderStatus = "WAPPR"
    priority: int = Field(ge=1, le=5)
    work_type: str = "CM"
    failure_class: str = "MECH"
    problem_code: str = "INVESTIGATE"
    classification: str = "Corrective"
    assigned_to: str
    supervisor: str
    due_date: str
    recommended_action: str
    follow_up_required: bool = False
    ai_summary: Optional[str] = None
    completion_summary: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    logs: list[WorkOrderLog] = []


class WorkOrderCreateRequest(BaseModel):
    equipment_id: str
    title: str
    description: str
    priority: int = Field(default=2, ge=1, le=5)
    work_type: str = "CM"
    failure_class: str = "MECH"
    problem_code: str = "INVESTIGATE"
    classification: str = "Corrective"
    assigned_to: str = "Maintenance Engineer"
    supervisor: str = "Maintenance Supervisor"
    due_date: str
    recommended_action: str = "Inspect asset and update work log with findings."
    follow_up_required: bool = False
    ai_summary: Optional[str] = None


class WorkOrderUpdateRequest(BaseModel):
    status: Optional[WorkOrderStatus] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    assigned_to: Optional[str] = None
    supervisor: Optional[str] = None
    due_date: Optional[str] = None
    recommended_action: Optional[str] = None
    problem_code: Optional[str] = None
    failure_class: Optional[str] = None
    classification: Optional[str] = None
    follow_up_required: Optional[bool] = None
    ai_summary: Optional[str] = None
    completion_summary: Optional[str] = None


class AssetDocument(BaseModel):
    id: str
    source_type: str
    equipment_id: Optional[str] = None
    title: str
    excerpt: str


class AssetPerformancePoint(BaseModel):
    timestamp: str
    value: float
    threshold: float


class AssetPerformanceChart(BaseModel):
    signal: str
    title: str
    unit: str
    points: list[AssetPerformancePoint]


class AssetListItem(BaseModel):
    id: str
    name: str
    asset_type: str
    area: str
    process: str
    location_code: str
    location_name: str
    criticality: int
    status: str
    health_score: int
    risk_level: RiskLevel
    active_alerts: int
    open_work_orders: int
    supervisor: str
    last_updated: str


class AssetDetail(BaseModel):
    profile: AssetProfile
    health: HealthSummary
    metrics: list[AssetMetricSnapshot] = Field(default_factory=list)
    recommendations: list[AssetRecommendation] = Field(default_factory=list)
    maintenance_events: list[MaintenanceEvent] = Field(default_factory=list)
    work_orders: list[WorkOrder] = Field(default_factory=list)
    subsystems: list[AssetSubsystem] = Field(default_factory=list)
    reliability_metrics: list[AssetReliabilityMetric] = Field(default_factory=list)
    performance_charts: list[AssetPerformanceChart] = Field(default_factory=list)
    documents: list[AssetDocument] = Field(default_factory=list)
    knowledge: list[Evidence] = Field(default_factory=list)
    prediction: Optional[PredictionResponse] = None


class WorkOrderLogRequest(BaseModel):
    author: str
    entry_type: str = "note"
    content: str


class TechnicianAssistantRequest(BaseModel):
    work_order_id: str
    observation: Optional[str] = None
    requested_step: Optional[str] = None


class TechnicianAssistantResponse(BaseModel):
    work_order_id: str
    next_prompt: str
    live_directions: list[str]
    recommendations: list[str]
    safety_reminders: list[str]
    suggested_problem_code: str
    suggested_failure_class: str
    completion_summary: str
    evidence: list[Evidence] = []
    used_live_provider: bool = False
    provider: str = "mock"


class SupervisorAssistantRequest(BaseModel):
    work_order_id: Optional[str] = None
    queue_name: Optional[str] = None
    question: Optional[str] = None


class SupervisorAssistantResponse(BaseModel):
    summary: str
    follow_up_actions: list[str]
    risks: list[str]
    draft_work_order: Optional[WorkOrderCreateRequest] = None
    referenced_work_orders: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"


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
    context_class: Optional[AnomalyContextClass] = None
    context_rationale: Optional[str] = None
    recommended_inspection_steps: list[str] = []


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


class NeoTable(BaseModel):
    title: str
    columns: list[str]
    rows: list[dict[str, Any]]


class NeoAction(BaseModel):
    type: str
    label: str
    status: Literal["completed", "blocked", "not_allowed", "not_found"]
    target_id: Optional[str] = None
    detail: Optional[str] = None


class NeoChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


class NeoChatResponse(BaseModel):
    answer: str
    table: Optional[NeoTable] = None
    action: Optional[NeoAction] = None
    used_live_provider: bool = False
    provider: str = "mock"


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
    reasoning_explanation: Optional["ReasoningExplanation"] = None
    used_live_provider: bool = False
    provider: str = "mock"
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
    reasoning_explanation: Optional["ReasoningExplanation"] = None


class DocumentIntelligence(BaseModel):
    document_id: str
    summary: str
    asset_ids: list[str] = []
    components: list[str] = []
    failure_modes: list[str] = []
    symptoms: list[str] = []
    safety_constraints: list[str] = []
    spares: list[str] = []
    thresholds: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"


class MaintenanceLabel(BaseModel):
    source_type: Literal["maintenance_event", "feedback"]
    source_id: str
    equipment_id: Optional[str] = None
    failure_mode: str
    component: str
    root_cause: str
    action_class: str
    outcome_status: str
    signal_hints: list[str] = []
    usable_for_training: bool = True
    used_live_provider: bool = False
    provider: str = "mock"


class LearningInteraction(BaseModel):
    id: str
    assistant: str
    interaction_type: str
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    equipment_id: Optional[str] = None
    work_order_id: Optional[str] = None
    prompt: str
    response: str
    provider: str = "mock"
    used_live_provider: bool = False
    prompt_version: str = "default"
    model_version: str = "model-local-qwen2.5-current"
    source_refs: list[dict[str, Any]] = []
    approved_for_learning: bool = False
    outcome_status: Optional[str] = None
    created_at: str


class LearningExample(BaseModel):
    id: str
    source_type: str
    source_id: str
    equipment_id: Optional[str] = None
    work_order_id: Optional[str] = None
    instruction: str
    input_text: str
    expected_output: str
    metadata: dict[str, Any] = {}
    approved: bool = False
    judge_score: float = Field(default=0, ge=0, le=1)
    judge_label: str = "not_scored"
    judge_rationale: Optional[str] = None
    judge_provider: str = "not_scored"
    judge_used_live_provider: bool = False
    judged_at: Optional[str] = None
    created_at: str


class LearningJudgeResult(BaseModel):
    score: float = Field(ge=0, le=1)
    label: Literal["training_worthy", "review", "reject"]
    rationale: str
    strengths: list[str] = []
    risks: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"


class LearningExampleUpdateRequest(BaseModel):
    approved: bool


class LearningDatasetCreateRequest(BaseModel):
    name: str = "maintenance-wizard-learning-snapshot"
    description: Optional[str] = None
    approved_only: bool = True
    min_judge_score: float = Field(default=0.65, ge=0, le=1)


class LearningDatasetSnapshot(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    example_count: int
    approved_only: bool = True
    jsonl_content: str
    created_by: Optional[str] = None
    created_at: str


class LearningModelVersion(BaseModel):
    id: str
    provider: str
    model_name: str
    base_model: Optional[str] = None
    adapter_path: Optional[str] = None
    status: str
    notes: Optional[str] = None
    created_at: str


class LearningPromptVersion(BaseModel):
    id: str
    assistant: str
    version: str
    prompt: str
    status: str
    notes: Optional[str] = None
    created_at: str


class LearningModelVersionCreateRequest(BaseModel):
    provider: str = "openai"
    model_name: str
    base_model: Optional[str] = None
    adapter_path: Optional[str] = None
    status: Literal["candidate", "active", "retired"] = "candidate"
    notes: Optional[str] = None


class LearningModelPromotionRequest(BaseModel):
    model_version_id: str
    evaluation_run_id: str
    notes: Optional[str] = None


class LearningModelRollbackRequest(BaseModel):
    target_model_version_id: str
    evaluation_run_id: str
    notes: Optional[str] = None


class LearningModelPromotion(BaseModel):
    id: str
    model_version_id: str
    previous_active_model_id: Optional[str] = None
    evaluation_run_id: str
    dataset_id: str
    prompt_version_id: str
    action: Literal["promote", "rollback"]
    reviewer_email: str
    notes: Optional[str] = None
    created_at: str


class LearningEvaluationCreateRequest(BaseModel):
    dataset_id: str
    model_version_id: str = "model-local-qwen2.5-current"
    prompt_version_id: str = "prompt-neo-default"
    min_quality_score: float = Field(default=0.7, ge=0, le=1)
    notes: Optional[str] = None


class LearningEvaluationRun(BaseModel):
    id: str
    dataset_id: Optional[str] = None
    model_version_id: Optional[str] = None
    prompt_version_id: Optional[str] = None
    metrics: dict[str, Any] = {}
    notes: Optional[str] = None
    passed: bool = False
    created_at: str


LearningJobType = Literal[
    "refresh_examples",
    "judge_example",
    "dataset_snapshot",
    "evaluation",
    "peft_tuning",
    "adapter_registered",
    "model_promotion",
]
LearningJobStatus = Literal["queued", "published", "running", "completed", "failed"]


class LearningJob(BaseModel):
    id: str
    job_type: LearningJobType
    subject: str
    status: LearningJobStatus
    requested_by: Optional[str] = None
    correlation_id: str
    input_refs: dict[str, Any] = {}
    output_refs: dict[str, Any] = {}
    error: Optional[str] = None
    retry_count: int = 0
    created_at: str
    updated_at: str


class LearningArtifact(BaseModel):
    id: str
    job_id: str
    artifact_type: str
    uri: str
    content_hash: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class LearningPeftJobCreateRequest(BaseModel):
    dataset_id: str
    model_version_id: str = "model-local-qwen2.5-current"
    prompt_version_id: str = "prompt-neo-default"
    adapter_name: str = "maintenance-wizard-qwen-lora"
    base_model: Optional[str] = "qwen2.5-7b-instruct"
    training_config: dict[str, Any] = {}
    notes: Optional[str] = None


class LearningSummary(BaseModel):
    counts: dict[str, int]
    recent_examples: list[LearningExample] = []
    recent_snapshots: list[LearningDatasetSnapshot] = []
    model_versions: list[LearningModelVersion] = []
    prompt_versions: list[LearningPromptVersion] = []
    evaluation_runs: list[LearningEvaluationRun] = []
    recent_jobs: list[LearningJob] = []
    recent_artifacts: list[LearningArtifact] = []
    recent_promotions: list[LearningModelPromotion] = []
    serving_model: dict[str, Any] = Field(default_factory=dict)
    artifact_store: dict[str, Any] = Field(default_factory=dict)
    peft_trainer: dict[str, Any] = Field(default_factory=dict)
    vector_store: dict[str, Any] = Field(default_factory=dict)


class AnomalyContext(BaseModel):
    equipment_id: str
    signal: str
    timestamp: str
    context_class: AnomalyContextClass
    rationale: str
    recommended_inspection_steps: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"


class ReasoningExplanation(BaseModel):
    subject_type: Literal["prediction", "anomaly", "recommendation", "retrieval"]
    summary: str
    driver_explanations: list[str] = []
    cautions: list[str] = []
    recommended_next_steps: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"


class DocumentIngestResponse(BaseModel):
    status: str
    documents: int
    document: Optional[dict[str, Any]] = None
    intelligence: list[DocumentIntelligence] = []


class MaintenanceLabelsResponse(BaseModel):
    equipment_id: Optional[str] = None
    labels: list[MaintenanceLabel]


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


Recommendation.model_rebuild()
PredictionResponse.model_rebuild()
AssetDetail.model_rebuild()
