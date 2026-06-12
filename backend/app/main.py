import json
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.core.auth import (
    ADMIN_ROLES,
    DECISION_ROLES,
    FEEDBACK_ROLES,
    INGESTION_ROLES,
    READ_ROLES,
    SUPERVISOR_ASSISTANT_ROLES,
    TECHNICIAN_ASSISTANT_ROLES,
    STREAMING_STATUS_ROLES,
    WORK_ORDER_ACTION_ROLES,
    WORK_ORDER_ASSIGNMENT_ROLES,
    get_current_user,
    require_roles,
)
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.data import repository
from app.data.database import initialize_database
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DashboardSummary,
    DiagnosisRequest,
    DocumentIngestResponse,
    FeedbackRequest,
    FeedbackResponse,
    HealthSummary,
    MaintenanceLabelsResponse,
    LoginRequest,
    NeoChatRequest,
    NeoChatResponse,
    PasswordResetRequest,
    PredictionRequest,
    Recommendation,
    StreamingStatus,
    SupervisorAssistantRequest,
    SupervisorAssistantResponse,
    TechnicianAssistantRequest,
    TechnicianAssistantResponse,
    TokenResponse,
    UserCreateRequest,
    UserPublic,
    UserUpdateRequest,
    WorkOrder,
    WorkOrderCreateRequest,
    WorkOrderLogRequest,
    WorkOrderUpdateRequest,
)
from app.services.document_intelligence import analyze_documents, document_intelligence
from app.services.iot_streaming import StreamingIngestionService
from app.services.maintenance_labeling import label_feedback, label_maintenance_event, label_maintenance_history, stored_labels
from app.services.neo_assistant import neo_assistance, stream_neo_assistance
from app.services.recommendations import generate_recommendation
from app.services.document_parser import parse_upload_to_document
from app.services.reports import recommendation_to_markdown
from app.services.retrieval import retrieve_evidence
from app.services.risk import active_alerts, equipment_records, health_summary, predict_failure
from app.services.anomaly import analyze_anomalies, sensor_readings
from app.services.work_order_assistant import (
    stream_supervisor_assistance,
    stream_technician_assistance,
    supervisor_assistance,
    technician_assistance,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    initialize_database(seed=True)
    streaming_service = StreamingIngestionService()
    app.state.streaming_service = streaming_service
    await streaming_service.start()
    try:
        yield
    finally:
        await streaming_service.stop()


app = FastAPI(title="Maintenance Wizard API", version="0.1.0", lifespan=lifespan)
settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "maintenance-wizard-api"}


@app.post("/api/auth/login", response_model=TokenResponse)
def login(request: LoginRequest):
    email = request.email.strip().lower()
    user = repository.get_user_by_email(email)
    if not user or not user["is_active"] or not verify_password(request.password, user["password_hash"]):
        repository.save_auth_audit_event("login", False, email=email, detail="Invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_access_token(user["id"], user["role"])
    repository.record_user_login(user["id"])
    repository.save_auth_audit_event(
        "login",
        True,
        email=user["email"],
        user_id=user["id"],
        role=user["role"],
        detail="Login succeeded",
    )
    refreshed_user = repository.get_user_by_id(user["id"]) or user
    return TokenResponse(access_token=token, expires_in=expires_in, user=UserPublic(**refreshed_user))


@app.get("/api/auth/me", response_model=UserPublic)
def me(current_user: UserPublic = Depends(get_current_user)):
    return current_user


@app.post("/api/auth/logout")
def logout(current_user: UserPublic = Depends(get_current_user)) -> dict[str, str]:
    repository.save_auth_audit_event(
        "logout",
        True,
        email=current_user.email,
        user_id=current_user.id,
        role=current_user.role,
        detail="Client logout",
    )
    return {"status": "logged_out"}


@app.get("/api/users", response_model=list[UserPublic], dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def list_users():
    return [UserPublic(**user) for user in repository.list_users()]


@app.get(
    "/api/users/technicians",
    response_model=list[UserPublic],
    dependencies=[Depends(require_roles(*WORK_ORDER_ASSIGNMENT_ROLES))],
)
def list_technicians():
    return [
        UserPublic(**user)
        for user in repository.list_users()
        if user["role"] == "maintenance_technician" and user["is_active"]
    ]


@app.post(
    "/api/users",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
)
def create_user(request: UserCreateRequest):
    try:
        user = repository.create_user(request.model_dump())
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="User email already exists") from exc
    return UserPublic(**user)


@app.patch("/api/users/{user_id}", response_model=UserPublic, dependencies=[Depends(require_roles(*ADMIN_ROLES))])
def update_user(user_id: str, request: UserUpdateRequest):
    user = repository.update_user(user_id, request.model_dump(exclude_unset=True))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic(**user)


@app.post(
    "/api/users/{user_id}/reset-password",
    response_model=UserPublic,
    dependencies=[Depends(require_roles(*ADMIN_ROLES))],
)
def reset_password(user_id: str, request: PasswordResetRequest):
    user = repository.reset_user_password(user_id, request.password)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserPublic(**user)


@app.post(
    "/api/ingest/documents",
    response_model=DocumentIngestResponse,
    dependencies=[Depends(require_roles(*INGESTION_ROLES))],
)
def ingest_documents(payload: Optional[dict[str, list[dict[str, Any]]]] = None):
    documents = payload.get("documents", []) if payload else []
    count = repository.add_documents(documents)
    intelligence = analyze_documents(documents)
    return {"status": "stored", "documents": count, "intelligence": intelligence}


@app.post(
    "/api/ingest/document-file",
    response_model=DocumentIngestResponse,
    dependencies=[Depends(require_roles(*INGESTION_ROLES))],
)
async def ingest_document_file(
    file: UploadFile = File(...),
    source_type: str = Form(default="manual"),
    equipment_id: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
) -> dict[str, Any]:
    document = await parse_upload_to_document(file, source_type, equipment_id, title)
    count = repository.add_documents([document])
    intelligence = analyze_documents([document])
    return {"status": "stored", "documents": count, "document": document, "intelligence": intelligence}


@app.post("/api/ingest/records", dependencies=[Depends(require_roles(*INGESTION_ROLES))])
def ingest_records(payload: Optional[dict[str, list[dict[str, Any]]]] = None) -> dict[str, Any]:
    records = payload or {}
    counts = repository.add_records(records)
    for event in records.get("maintenance_events", []):
        label_maintenance_event(event)
    return {"status": "stored", "counts": counts}


@app.get(
    "/api/streaming/status",
    response_model=StreamingStatus,
    dependencies=[Depends(require_roles(*STREAMING_STATUS_ROLES))],
)
def streaming_status():
    service = getattr(app.state, "streaming_service", None)
    if not service:
        service = StreamingIngestionService()
    return service.status()


@app.get("/api/equipment", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_equipment():
    return equipment_records()


@app.get(
    "/api/equipment/{equipment_id}/health",
    response_model=HealthSummary,
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def get_equipment_health(equipment_id: str):
    try:
        return health_summary(equipment_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Equipment not found") from exc


@app.get("/api/alerts", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_alerts():
    return active_alerts()


@app.get("/api/equipment/{equipment_id}/sensor-readings", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_sensor_readings(equipment_id: str):
    return sensor_readings(equipment_id)


@app.get("/api/equipment/{equipment_id}/anomalies", dependencies=[Depends(require_roles(*READ_ROLES))])
def get_anomalies(equipment_id: str):
    return analyze_anomalies(equipment_id)


@app.get(
    "/api/equipment/{equipment_id}/document-intelligence",
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def get_document_intelligence(equipment_id: str):
    return document_intelligence(equipment_id)


@app.post(
    "/api/equipment/{equipment_id}/maintenance-labels",
    response_model=MaintenanceLabelsResponse,
    dependencies=[Depends(require_roles(*DECISION_ROLES))],
)
def generate_maintenance_labels(equipment_id: str):
    labels = label_maintenance_history(equipment_id)
    return MaintenanceLabelsResponse(equipment_id=equipment_id, labels=labels)


@app.get(
    "/api/equipment/{equipment_id}/maintenance-labels",
    response_model=MaintenanceLabelsResponse,
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def get_maintenance_labels(equipment_id: str):
    return MaintenanceLabelsResponse(equipment_id=equipment_id, labels=stored_labels(equipment_id))


@app.get("/api/work-orders", response_model=list[WorkOrder])
def list_work_orders(
    equipment_id: Optional[str] = None,
    follow_up_only: bool = False,
    current_user: UserPublic = Depends(require_roles(*READ_ROLES)),
):
    assigned_to = current_user.display_name if current_user.role == "maintenance_technician" else None
    return repository.list_work_orders(
        equipment_id=equipment_id,
        assigned_to=assigned_to,
        follow_up_only=follow_up_only,
    )


@app.post(
    "/api/work-orders",
    response_model=WorkOrder,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_roles(*WORK_ORDER_ACTION_ROLES))],
)
def create_work_order(request: WorkOrderCreateRequest):
    if not repository.get_equipment(request.equipment_id):
        raise HTTPException(status_code=404, detail="Equipment not found")
    return repository.create_work_order(request.model_dump())


@app.get("/api/work-orders/{work_order_id}", response_model=WorkOrder, dependencies=[Depends(require_roles(*READ_ROLES))])
def get_work_order(work_order_id: str):
    work_order = repository.get_work_order(work_order_id)
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    return work_order


@app.patch(
    "/api/work-orders/{work_order_id}",
    response_model=WorkOrder,
    dependencies=[Depends(require_roles(*WORK_ORDER_ACTION_ROLES))],
)
def update_work_order(work_order_id: str, request: WorkOrderUpdateRequest):
    work_order = repository.update_work_order(work_order_id, request.model_dump(exclude_unset=True))
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    return work_order


@app.post(
    "/api/work-orders/{work_order_id}/logs",
    response_model=WorkOrder,
    dependencies=[Depends(require_roles(*WORK_ORDER_ACTION_ROLES))],
)
def add_work_order_log(work_order_id: str, request: WorkOrderLogRequest):
    work_order = repository.add_work_order_log(work_order_id, request.model_dump())
    if not work_order:
        raise HTTPException(status_code=404, detail="Work order not found")
    return work_order


@app.post(
    "/api/work-orders/technician-assist",
    response_model=TechnicianAssistantResponse,
    dependencies=[Depends(require_roles(*TECHNICIAN_ASSISTANT_ROLES))],
)
def technician_assist(request: TechnicianAssistantRequest):
    return technician_assistance(request)


@app.post(
    "/api/work-orders/technician-assist/stream",
    dependencies=[Depends(require_roles(*TECHNICIAN_ASSISTANT_ROLES))],
)
def technician_assist_stream(request: TechnicianAssistantRequest):
    def events():
        for event in stream_technician_assistance(request):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post(
    "/api/work-orders/supervisor-assist",
    response_model=SupervisorAssistantResponse,
    dependencies=[Depends(require_roles(*SUPERVISOR_ASSISTANT_ROLES))],
)
def supervisor_assist(request: SupervisorAssistantRequest):
    return supervisor_assistance(request)


@app.post(
    "/api/work-orders/supervisor-assist/stream",
    dependencies=[Depends(require_roles(*SUPERVISOR_ASSISTANT_ROLES))],
)
def supervisor_assist_stream(request: SupervisorAssistantRequest):
    def events():
        for event in stream_supervisor_assistance(request):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/neo/chat", response_model=NeoChatResponse)
def neo_chat(
    request: NeoChatRequest,
    current_user: UserPublic = Depends(require_roles(*READ_ROLES)),
):
    return neo_assistance(request, current_user)


@app.post("/api/neo/chat/stream")
def neo_chat_stream(
    request: NeoChatRequest,
    current_user: UserPublic = Depends(require_roles(*READ_ROLES)),
):
    def events():
        for event in stream_neo_assistance(request, current_user):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/chat", response_model=ChatResponse, dependencies=[Depends(require_roles(*DECISION_ROLES))])
def chat(request: ChatRequest):
    equipment_id = request.equipment_id or "RM-DRIVE-01"
    recommendation = generate_recommendation(DiagnosisRequest(equipment_id=equipment_id, symptoms=request.message))
    evidence = retrieve_evidence(request.message, equipment_id)
    return ChatResponse(
        answer=f"{recommendation.diagnosis} Recommended urgency: {recommendation.urgency}",
        recommendation=recommendation,
        evidence=evidence or recommendation.evidence,
    )


@app.post("/api/diagnose", response_model=Recommendation, dependencies=[Depends(require_roles(*DECISION_ROLES))])
def diagnose(request: DiagnosisRequest):
    return generate_recommendation(request)


@app.post("/api/predict", dependencies=[Depends(require_roles(*DECISION_ROLES))])
def predict(request: PredictionRequest):
    return predict_failure(request.equipment_id)


@app.post(
    "/api/recommendations/{recommendation_id}/feedback",
    response_model=FeedbackResponse,
    dependencies=[Depends(require_roles(*FEEDBACK_ROLES))],
)
def store_feedback(recommendation_id: str, feedback: FeedbackRequest):
    repository.save_feedback(recommendation_id, feedback.model_dump())
    saved_feedback = repository.list_feedback(feedback.equipment_id)[0] if feedback.equipment_id else repository.list_feedback()[0]
    label_feedback(saved_feedback)
    return FeedbackResponse(
        recommendation_id=recommendation_id,
        stored=True,
        message="Feedback stored for future recommendation context.",
    )


@app.get(
    "/api/reports/{equipment_id}",
    response_model=Recommendation,
    dependencies=[Depends(require_roles(*DECISION_ROLES))],
)
def report(equipment_id: str):
    return generate_recommendation(DiagnosisRequest(equipment_id=equipment_id))


@app.get("/api/reports/{equipment_id}/markdown", dependencies=[Depends(require_roles(*DECISION_ROLES))])
def report_markdown(equipment_id: str):
    recommendation = generate_recommendation(DiagnosisRequest(equipment_id=equipment_id))
    markdown = recommendation_to_markdown(recommendation)
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{equipment_id}-maintenance-report.md"'},
    )


@app.get(
    "/api/dashboard/summary",
    response_model=DashboardSummary,
    dependencies=[Depends(require_roles(*READ_ROLES))],
)
def dashboard_summary():
    summaries = [health_summary(equipment.id) for equipment in equipment_records()]
    highest = sorted(summaries, key=lambda item: item.health_score)
    alerts = active_alerts()
    critical_count = len([alert for alert in alerts if alert.severity == "critical"])
    average_health = int(sum(item.health_score for item in summaries) / max(1, len(summaries)))
    return DashboardSummary(
        equipment_count=len(summaries),
        active_alert_count=len(alerts),
        critical_alert_count=critical_count,
        average_health_score=average_health,
        highest_risk_equipment=highest,
    )
