from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import AliasChoices, BaseModel, Field, field_validator


RiskLevel = Literal["low", "medium", "high", "critical"]
WorkOrderStatus = Literal["WAPPR", "APPR", "WMATL", "INPRG", "COMP", "CLOSE"]
WorkOrderPlanningStatus = Literal["unscheduled", "planned", "dispatched"]
MaterialReadiness = Literal["unknown", "pending", "ready", "blocked"]
MaterialBlockerStatus = Literal[
    "not_required",
    "reserved",
    "reorder_requested",
    "waiting_procurement",
    "substitute_available",
    "blocked",
]
ProcurementStatus = Literal["not_required", "not_requested", "requested", "ordered", "received"]
WorkOrderAssistantAudience = Literal["technician", "supervisor"]
RcaCaseStatus = Literal["open", "investigating", "actions_defined", "closed"]
RcaCorrectiveActionStatus = Literal["proposed", "approved", "in_progress", "complete", "rejected"]
PmPlanStatus = Literal["draft", "active", "converted", "paused"]
PmTriggerType = Literal["recurring", "condition", "risk_prediction"]
NotificationSeverity = Literal["info", "low", "medium", "high", "critical"]
NotificationLlmStatus = Literal["not_requested", "pending", "completed", "failed"]
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


class WorkOrderSpareReservation(BaseModel):
    id: Optional[int] = None
    work_order_id: Optional[str] = None
    spare_id: Optional[str] = None
    spare_name: str
    required_qty: int = Field(default=1, ge=0)
    reserved_qty: int = Field(default=0, ge=0)
    available_qty: int = Field(default=0, ge=0)
    reorder_requested: bool = False
    procurement_status: ProcurementStatus = "not_requested"
    procurement_lead_time_days: int = Field(default=0, ge=0)
    expected_available_date: Optional[str] = None
    substitute_spare_id: Optional[str] = None
    substitute_name: Optional[str] = None
    blocker_status: MaterialBlockerStatus = "not_required"
    blocker_note: Optional[str] = None


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
    planning_status: WorkOrderPlanningStatus = "unscheduled"
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    outage_window: Optional[str] = None
    material_readiness: MaterialReadiness = "unknown"
    material_blocker_status: MaterialBlockerStatus = "not_required"
    material_blocker_note: Optional[str] = None
    dispatch_notes: Optional[str] = None
    dispatched_at: Optional[str] = None
    recommended_action: str
    follow_up_required: bool = False
    ai_summary: Optional[str] = None
    completion_summary: Optional[str] = None
    created_at: str
    updated_at: str
    completed_at: Optional[str] = None
    logs: list[WorkOrderLog] = []
    spare_reservations: list[WorkOrderSpareReservation] = []


class WorkOrderPage(BaseModel):
    items: list[WorkOrder] = []
    total: int
    limit: int
    offset: int


class WorkOrderCreateRequest(BaseModel):
    equipment_id: str
    title: str
    description: str
    priority: int = Field(default=2, ge=1, le=5)
    work_type: str = "CM"
    failure_class: str = "MECH"
    problem_code: str = "INVESTIGATE"
    classification: str = "Corrective"
    assigned_to: str = ""
    supervisor: str = "Maintenance Supervisor"
    due_date: str
    planning_status: WorkOrderPlanningStatus = "unscheduled"
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    outage_window: Optional[str] = None
    material_readiness: MaterialReadiness = "unknown"
    material_blocker_status: MaterialBlockerStatus = "not_required"
    material_blocker_note: Optional[str] = None
    spare_reservations: list[WorkOrderSpareReservation] = []
    dispatch_notes: Optional[str] = None
    dispatched_at: Optional[str] = None
    recommended_action: str = "Inspect asset and update work log with findings."
    follow_up_required: bool = False
    ai_summary: Optional[str] = None


class WorkOrderUpdateRequest(BaseModel):
    status: Optional[WorkOrderStatus] = None
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    assigned_to: Optional[str] = None
    supervisor: Optional[str] = None
    due_date: Optional[str] = None
    planning_status: Optional[WorkOrderPlanningStatus] = None
    planned_start: Optional[str] = None
    planned_end: Optional[str] = None
    outage_window: Optional[str] = None
    material_readiness: Optional[MaterialReadiness] = None
    material_blocker_status: Optional[MaterialBlockerStatus] = None
    material_blocker_note: Optional[str] = None
    spare_reservations: Optional[list[WorkOrderSpareReservation]] = None
    dispatch_notes: Optional[str] = None
    dispatched_at: Optional[str] = None
    recommended_action: Optional[str] = None
    problem_code: Optional[str] = None
    failure_class: Optional[str] = None
    classification: Optional[str] = None
    follow_up_required: Optional[bool] = None
    ai_summary: Optional[str] = None
    completion_summary: Optional[str] = None


class PmTemplate(BaseModel):
    id: str
    equipment_id: Optional[str] = None
    title: str
    description: str
    cadence_days: int = Field(default=30, ge=1)
    work_type: str = "PM"
    task_list: list[str] = Field(default_factory=list)
    thresholds: list[str] = Field(default_factory=list)
    source: str = "seed"
    created_at: str
    updated_at: str


class PmTask(BaseModel):
    id: str
    sequence: int = Field(ge=1)
    task: str
    owner_role: str = "Maintenance Technician"
    estimated_minutes: int = Field(default=30, ge=1)
    safety_note: Optional[str] = None


class PmTrigger(BaseModel):
    type: PmTriggerType = "recurring"
    metric_key: Optional[str] = None
    operator: Optional[Literal[">=", "<=", ">", "<", "change"]] = None
    threshold: Optional[float] = None
    unit: Optional[str] = None
    description: str


class PmPlan(BaseModel):
    id: str
    equipment_id: str
    template_id: Optional[str] = None
    title: str
    status: PmPlanStatus = "draft"
    cadence_days: int = Field(default=30, ge=1)
    next_due_date: str
    trigger: PmTrigger
    thresholds: list[str] = Field(default_factory=list)
    tasks: list[PmTask] = Field(default_factory=list)
    smith_steps: list[str] = Field(default_factory=list)
    spares_strategy: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    adjustment_notes: list[str] = Field(default_factory=list)
    source: str = "deterministic"
    generated_by: str = "morpheus"
    used_live_provider: bool = False
    provider: str = "mock"
    converted_work_order_id: Optional[str] = None
    created_at: str
    updated_at: str


class PmPlanPage(BaseModel):
    items: list[PmPlan] = []
    total: int
    limit: int
    offset: int


class PmPlanDraftRequest(BaseModel):
    equipment_id: str
    template_id: Optional[str] = None
    convert_from_prediction: bool = False
    risk_threshold: RiskLevel = "high"
    requested_focus: Optional[str] = None


class PmPlanDraftResponse(BaseModel):
    plan: PmPlan
    templates: list[PmTemplate] = Field(default_factory=list)
    message: str


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
    session_id: Optional[str] = None


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
    session_id: Optional[str] = None


class SupervisorAssistantResponse(BaseModel):
    summary: str
    follow_up_actions: list[str]
    risks: list[str]
    draft_work_order: Optional[WorkOrderCreateRequest] = None
    referenced_work_orders: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"


class RcaHypothesis(BaseModel):
    id: str
    cause: str
    confidence: float = Field(default=0.5, ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)
    missing_checks: list[str] = Field(default_factory=list)
    status: Literal["candidate", "validated", "rejected"] = "candidate"


class RcaEvidenceItem(BaseModel):
    id: str
    timestamp: str
    source_type: str
    source_id: str
    title: str
    summary: str
    relevance: str


class RcaCorrectiveAction(BaseModel):
    id: str
    action: str
    owner: str = "Maintenance Engineer"
    due_date: Optional[str] = None
    status: RcaCorrectiveActionStatus = "proposed"
    verification: Optional[str] = None


class RcaClosureReview(BaseModel):
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    accepted_for_learning: bool = False
    final_root_cause: Optional[str] = None
    recurrence_prevention: Optional[str] = None
    lessons_learned: Optional[str] = None


class RcaCase(BaseModel):
    id: str
    equipment_id: str
    work_order_id: Optional[str] = None
    title: str
    status: RcaCaseStatus = "open"
    severity: RiskLevel = "medium"
    problem_statement: str
    symptoms: list[str] = Field(default_factory=list)
    hypotheses: list[RcaHypothesis] = Field(default_factory=list)
    why_chain: list[str] = Field(default_factory=list)
    fishbone: dict[str, list[str]] = Field(default_factory=dict)
    evidence_timeline: list[RcaEvidenceItem] = Field(default_factory=list)
    corrective_actions: list[RcaCorrectiveAction] = Field(default_factory=list)
    closure_review: Optional[RcaClosureReview] = None
    probable_cause: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    missing_checks: list[str] = Field(default_factory=list)
    morpheus_summary: Optional[str] = None
    morpheus_fishbone_text: Optional[str] = None
    used_live_provider: bool = False
    provider: str = "mock"
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None


class RcaCaseCreateRequest(BaseModel):
    equipment_id: str
    work_order_id: Optional[str] = None
    title: Optional[str] = None
    problem_statement: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)


class RcaCaseUpdateRequest(BaseModel):
    title: Optional[str] = None
    status: Optional[RcaCaseStatus] = None
    severity: Optional[RiskLevel] = None
    problem_statement: Optional[str] = None
    symptoms: Optional[list[str]] = None
    hypotheses: Optional[list[RcaHypothesis]] = None
    why_chain: Optional[list[str]] = None
    fishbone: Optional[dict[str, list[str]]] = None
    evidence_timeline: Optional[list[RcaEvidenceItem]] = None
    corrective_actions: Optional[list[RcaCorrectiveAction]] = None
    closure_review: Optional[RcaClosureReview] = None
    probable_cause: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    missing_checks: Optional[list[str]] = None
    morpheus_summary: Optional[str] = None
    morpheus_fishbone_text: Optional[str] = None
    used_live_provider: Optional[bool] = None
    provider: Optional[str] = None


class RcaMorpheusDraftRequest(BaseModel):
    case_id: Optional[str] = None
    equipment_id: Optional[str] = None
    work_order_id: Optional[str] = None
    symptoms: list[str] = Field(default_factory=list)
    question: Optional[str] = None


class RcaMorpheusDraftResponse(BaseModel):
    case: RcaCase
    evidence: list[Evidence] = Field(default_factory=list)
    message: str


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


class AlertViewState(BaseModel):
    user_id: str
    alert_id: str
    first_seen_at: str
    dismissed_at: Optional[str] = None


class AlertSeenRequest(BaseModel):
    dismissed: bool = False


class NotificationEvent(BaseModel):
    id: str
    event_key: str
    event_type: str
    severity: NotificationSeverity = "info"
    title: str
    summary: str
    recommended_action: str
    source_type: str
    source_id: str
    equipment_id: Optional[str] = None
    work_order_id: Optional[str] = None
    alert_id: Optional[str] = None
    recommendation_id: Optional[str] = None
    actor_user_id: Optional[str] = None
    actor_display_name: Optional[str] = None
    recipient_roles: list[UserRole] = []
    recipient_user_ids: list[str] = []
    metadata: dict[str, Any] = {}
    llm_provider: str = "mock"
    llm_used_live_provider: bool = False
    llm_status: NotificationLlmStatus = "not_requested"
    llm_error: Optional[str] = None
    llm_requested_at: Optional[str] = None
    llm_completed_at: Optional[str] = None
    created_at: str
    seen_at: Optional[str] = None
    dismissed_at: Optional[str] = None


class NotificationSeenRequest(BaseModel):
    dismissed: bool = False


class NotificationCleanupRequest(BaseModel):
    dry_run: bool = True
    dismissed_retention_days: int = Field(default=7, ge=0, le=365)
    delete_superseded_assignments: bool = True
    delete_dismissed_direct_notifications: bool = True


class NotificationCleanupResult(BaseModel):
    dry_run: bool
    dismissed_retention_days: int
    delete_superseded_assignments: bool
    delete_dismissed_direct_notifications: bool
    candidate_count: int
    deleted_count: int
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    deleted_ids: list[str] = Field(default_factory=list)
    vector_index_result: Optional[dict[str, Any]] = None


class MonitoringSensorPoint(BaseModel):
    id: str
    timestamp: str
    value: float
    threshold: float


class MonitoringSensorSeries(BaseModel):
    signal: str
    unit: str
    threshold: float
    latest_value: float
    latest_timestamp: str
    risk_level: RiskLevel
    stale: bool = False
    points: list[MonitoringSensorPoint] = []


class MonitoringAsset(BaseModel):
    equipment: Equipment
    latest_reading_timestamp: Optional[str] = None
    active_sensor_count: int = 0
    active_alert_count: int = 0
    highest_severity: RiskLevel = "low"
    stale: bool = True
    series: list[MonitoringSensorSeries] = []


class MonitoringDashboard(BaseModel):
    generated_at: str
    stale_after_seconds: int
    assets: list[MonitoringAsset] = []


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
    session_id: Optional[str] = None


class NeoChatResponse(BaseModel):
    answer: str
    table: Optional[NeoTable] = None
    action: Optional[NeoAction] = None
    used_live_provider: bool = False
    provider: str = "mock"


AssistantMessageRole = Literal["user", "assistant", "tool", "system"]
AssistantEventType = Literal["session", "meta", "token", "tool_call", "tool_result", "final", "done", "error"]
AssistantStatus = Literal["completed", "blocked", "not_allowed", "not_found", "failed"]


class AssistantToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    assistant_id: Optional[str] = None
    description: Optional[str] = None


class AssistantToolResult(BaseModel):
    tool_call_id: str
    name: str
    status: AssistantStatus = "completed"
    content: dict[str, Any] = Field(default_factory=dict)
    artifact_type: Optional[str] = None


class AssistantPriorityItem(BaseModel):
    priority: str
    title: str
    impact: str
    signal: str
    recommendation: str
    referenced_ids: list[str] = Field(default_factory=list)


class AssistantFinalResponse(BaseModel):
    assistant_id: str
    session_id: str
    markdown: str
    status: AssistantStatus = "completed"
    priorities: list[AssistantPriorityItem] = Field(default_factory=list)
    action: Optional[NeoAction] = None
    table: Optional[NeoTable] = None
    referenced_records: list[dict[str, Any]] = Field(default_factory=list)
    provider: str = "mock"
    used_live_provider: bool = False
    runtime: str = "legacy"
    runtime_fallback: bool = False
    runtime_fallback_reason: Optional[str] = None


class AssistantSessionPublic(BaseModel):
    id: str
    assistant_id: str
    user_id: Optional[str] = None
    user_role: Optional[str] = None
    screen: Optional[str] = None
    status: str = "active"
    created_at: str
    updated_at: str


class AssistantMessagePublic(BaseModel):
    id: str
    session_id: str
    assistant_id: str
    role: AssistantMessageRole
    content: str
    provider: Optional[str] = None
    used_live_provider: bool = False
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)
    final_response: Optional[dict[str, Any]] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


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


class StructuredMaintenanceReport(BaseModel):
    id: str
    equipment_id: str
    equipment_name: str
    area: str
    risk_level: RiskLevel
    health_score: int = Field(ge=0, le=100)
    failure_probability: float = Field(ge=0, le=1)
    remaining_useful_life_days: int = Field(ge=0)
    confidence_band: str
    active_alert_count: int = Field(ge=0)
    open_work_order_count: int = Field(ge=0)
    report_summary: str
    probable_causes: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    planned_actions: list[str] = Field(default_factory=list)
    spares_strategy: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    recommended_owner: str


class AbnormalAlertReport(BaseModel):
    alert_id: str
    equipment_id: str
    equipment_name: str
    timestamp: str
    signal: str
    severity: RiskLevel
    value: float
    unit: str
    threshold: float
    threshold_delta: float
    abnormality: str
    decision: str
    recommended_actions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class MaintenanceDecisionSummary(BaseModel):
    audience: Literal["engineer", "supervisor"]
    title: str
    summary: str
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    referenced_equipment: list[str] = Field(default_factory=list)
    referenced_alerts: list[str] = Field(default_factory=list)
    referenced_work_orders: list[str] = Field(default_factory=list)


class DigitalMaintenanceLogEntry(BaseModel):
    equipment_id: str
    equipment_name: str
    timestamp: str
    entry_type: str
    content: str
    source_ids: list[str] = Field(default_factory=list)


class MaintenanceInsightReportSummary(BaseModel):
    generated_at: str
    scope_equipment_id: Optional[str] = None
    assets_reviewed: int
    structured_report_count: int = Field(ge=0)
    abnormal_alert_report_count: int = Field(ge=0)
    decision_summary_count: int = Field(ge=0)
    maintenance_log_entry_count: int = Field(ge=0)


class MaintenanceInsightReportBundle(BaseModel):
    generated_at: str
    scope_equipment_id: Optional[str] = None
    assets_reviewed: int
    structured_reports: list[StructuredMaintenanceReport] = Field(default_factory=list)
    abnormal_alert_reports: list[AbnormalAlertReport] = Field(default_factory=list)
    decision_summaries: list[MaintenanceDecisionSummary] = Field(default_factory=list)
    maintenance_log_entries: list[DigitalMaintenanceLogEntry] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    recommendation: Recommendation
    evidence: list[Evidence]


class PredictionConfidenceInterval(BaseModel):
    lower_probability: float = Field(ge=0, le=1)
    upper_probability: float = Field(ge=0, le=1)
    lower_rul_days: int = Field(ge=0)
    upper_rul_days: int = Field(ge=0)
    confidence_level: float = Field(default=0.8, ge=0, le=1)
    rationale: str


class PredictionModelVersion(BaseModel):
    id: str
    name: str
    version: str
    algorithm: str
    feature_set: list[str] = Field(default_factory=list)
    trained_on: str
    status: str = "active"


class PredictionModelEvaluation(BaseModel):
    evaluation_id: str
    backtest_window_days: int = Field(ge=1)
    sample_count: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    mean_absolute_rul_error_days: int = Field(ge=0)
    calibration_error: float = Field(ge=0, le=1)
    summary: str


class PredictionEvidence(BaseModel):
    source_type: str
    source_id: str
    title: str
    detail: str
    contribution: float = Field(ge=0, le=1)


class DegradationTrendPoint(BaseModel):
    timestamp: str
    signal: str
    value: float
    unit: str
    threshold: float
    normalized_severity: float = Field(ge=0, le=1)
    estimated_rul_days: int = Field(ge=0)


class PredictionResponse(BaseModel):
    equipment_id: str
    risk_level: RiskLevel
    failure_probability: float = Field(ge=0, le=1)
    remaining_useful_life_days: int
    confidence_interval: Optional[PredictionConfidenceInterval] = None
    model_version: Optional[PredictionModelVersion] = None
    model_evaluation: Optional[PredictionModelEvaluation] = None
    prediction_evidence: list[PredictionEvidence] = Field(default_factory=list)
    degradation_trend: list[DegradationTrendPoint] = Field(default_factory=list)
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
    rationale: str = Field(validation_alias=AliasChoices("rationale", "reason", "explanation"))
    strengths: list[str] = []
    risks: list[str] = []
    used_live_provider: bool = False
    provider: str = "mock"

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, value):
        if isinstance(value, str):
            value = value.strip().rstrip("%")
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return value
        if numeric > 1:
            return numeric / 100
        return numeric

    @field_validator("label", mode="before")
    @classmethod
    def normalize_label(cls, value):
        normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "trainingworthy": "training_worthy",
            "worthy": "training_worthy",
            "approve": "training_worthy",
            "approved": "training_worthy",
            "accept": "training_worthy",
            "accepted": "training_worthy",
            "needs_review": "review",
            "manual_review": "review",
            "reject": "reject",
            "rejected": "reject",
        }
        return aliases.get(normalized, normalized)


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
    status: Literal["candidate"] = "candidate"
    notes: Optional[str] = None


class LearningModelDeploymentCreateRequest(BaseModel):
    runtime_provider: str = "manual"
    served_model_name: Optional[str] = None
    base_url: Optional[str] = None
    artifact_uri: Optional[str] = None
    artifact_hash: Optional[str] = None
    notes: Optional[str] = None


class LearningModelDeployment(BaseModel):
    id: str
    model_version_id: str
    job_id: Optional[str] = None
    runtime_provider: str
    serving_provider: str
    served_model_name: str
    base_url: Optional[str] = None
    artifact_uri: Optional[str] = None
    artifact_hash: Optional[str] = None
    status: str
    health_status: Optional[str] = None
    health_checked_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_at: str
    updated_at: str


class LearningModelPromotionRequest(BaseModel):
    model_version_id: str
    evaluation_run_id: str
    runtime_provider: Optional[str] = None
    served_model_name: Optional[str] = None
    base_url: Optional[str] = None
    artifact_uri: Optional[str] = None
    artifact_hash: Optional[str] = None
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
    "adapter_deployment",
    "adapter_registered",
    "model_promotion",
    "rag_reindex",
    "rag_embedding_profile",
    "rag_migration",
    "artifact_cleanup",
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


class LearningArtifactCleanupRequest(BaseModel):
    dry_run: bool = True
    notes: Optional[str] = None


class LearningArtifactCleanupResult(BaseModel):
    dry_run: bool
    cleanup_enabled: bool
    deletion_allowed: bool
    store: str
    retention: dict[str, Any] = Field(default_factory=dict)
    expired_count: int = 0
    protected_count: int = 0
    deleted_count: int = 0
    candidates: list[dict[str, Any]] = []
    protected: list[dict[str, Any]] = []
    deleted_paths: list[str] = []
    errors: list[str] = []


class RagEmbeddingProfile(BaseModel):
    id: str
    provider: str
    model: str
    version: str
    dimensions: int
    distance: str
    status: str = "candidate"
    notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class RagEmbeddingProfileCreateRequest(BaseModel):
    provider: Literal["deterministic_hash", "openai", "openai_compatible"] = "deterministic_hash"
    model: str
    version: str = "1"
    dimensions: int = Field(default=64, ge=1)
    distance: str = "Cosine"
    notes: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RagReindexRequest(BaseModel):
    target_collection: Optional[str] = None
    recreate_collection: bool = False
    notes: Optional[str] = None


class RagMigrationRequest(BaseModel):
    profile_id: Optional[str] = None
    target_collection: Optional[str] = None
    recreate_collection: bool = True
    activate_profile: bool = True
    notes: Optional[str] = None


class RagMigrationPlan(BaseModel):
    dry_run: bool = True
    store: str
    source_collection: str
    target_collection: str
    active_profile: dict[str, Any]
    target_profile: dict[str, Any]
    migration_required: bool = False
    will_activate_profile: bool = False
    will_recreate_collection: bool = False
    reasons: list[str] = []
    status: dict[str, Any] = Field(default_factory=dict)


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
    recent_deployments: list[LearningModelDeployment] = []
    serving_model: dict[str, Any] = Field(default_factory=dict)
    artifact_store: dict[str, Any] = Field(default_factory=dict)
    peft_trainer: dict[str, Any] = Field(default_factory=dict)
    vector_store: dict[str, Any] = Field(default_factory=dict)


class LearningExamplePage(BaseModel):
    items: list[LearningExample] = []
    total: int
    limit: int
    offset: int


class LearningEvaluationRunPage(BaseModel):
    items: list[LearningEvaluationRun] = []
    total: int
    limit: int
    offset: int


class LearningJobPage(BaseModel):
    items: list[LearningJob] = []
    total: int
    limit: int
    offset: int


class LearningArtifactPage(BaseModel):
    items: list[LearningArtifact] = []
    total: int
    limit: int
    offset: int


class LearningModelDeploymentPage(BaseModel):
    items: list[LearningModelDeployment] = []
    total: int
    limit: int
    offset: int


class LearningModelPromotionPage(BaseModel):
    items: list[LearningModelPromotion] = []
    total: int
    limit: int
    offset: int


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
