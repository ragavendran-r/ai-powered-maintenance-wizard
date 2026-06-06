from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.data import repository
from app.data.database import initialize_database
from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    DashboardSummary,
    DiagnosisRequest,
    FeedbackRequest,
    FeedbackResponse,
    HealthSummary,
    PredictionRequest,
    Recommendation,
)
from app.services.recommendations import generate_recommendation
from app.services.document_parser import parse_upload_to_document
from app.services.reports import recommendation_to_markdown
from app.services.retrieval import retrieve_evidence
from app.services.risk import active_alerts, equipment_records, health_summary, predict_failure
from app.services.anomaly import analyze_anomalies, sensor_readings


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    initialize_database(seed=True)
    yield


app = FastAPI(title="Maintenance Wizard API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "maintenance-wizard-api"}


@app.post("/api/ingest/documents")
def ingest_documents(payload: Optional[dict[str, list[dict[str, Any]]]] = None) -> dict[str, Any]:
    documents = payload.get("documents", []) if payload else []
    count = repository.add_documents(documents)
    return {"status": "stored", "documents": count}


@app.post("/api/ingest/document-file")
async def ingest_document_file(
    file: UploadFile = File(...),
    source_type: str = Form(default="manual"),
    equipment_id: Optional[str] = Form(default=None),
    title: Optional[str] = Form(default=None),
) -> dict[str, Any]:
    document = await parse_upload_to_document(file, source_type, equipment_id, title)
    count = repository.add_documents([document])
    return {"status": "stored", "documents": count, "document": document}


@app.post("/api/ingest/records")
def ingest_records(payload: Optional[dict[str, list[dict[str, Any]]]] = None) -> dict[str, Any]:
    counts = repository.add_records(payload or {})
    return {"status": "stored", "counts": counts}


@app.get("/api/equipment")
def get_equipment():
    return equipment_records()


@app.get("/api/equipment/{equipment_id}/health", response_model=HealthSummary)
def get_equipment_health(equipment_id: str):
    try:
        return health_summary(equipment_id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="Equipment not found") from exc


@app.get("/api/alerts")
def get_alerts():
    return active_alerts()


@app.get("/api/equipment/{equipment_id}/sensor-readings")
def get_sensor_readings(equipment_id: str):
    return sensor_readings(equipment_id)


@app.get("/api/equipment/{equipment_id}/anomalies")
def get_anomalies(equipment_id: str):
    return analyze_anomalies(equipment_id)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    equipment_id = request.equipment_id or "RM-DRIVE-01"
    recommendation = generate_recommendation(DiagnosisRequest(equipment_id=equipment_id, symptoms=request.message))
    evidence = retrieve_evidence(request.message, equipment_id)
    return ChatResponse(
        answer=f"{recommendation.diagnosis} Recommended urgency: {recommendation.urgency}",
        recommendation=recommendation,
        evidence=evidence or recommendation.evidence,
    )


@app.post("/api/diagnose", response_model=Recommendation)
def diagnose(request: DiagnosisRequest):
    return generate_recommendation(request)


@app.post("/api/predict")
def predict(request: PredictionRequest):
    return predict_failure(request.equipment_id)


@app.post("/api/recommendations/{recommendation_id}/feedback", response_model=FeedbackResponse)
def store_feedback(recommendation_id: str, feedback: FeedbackRequest):
    repository.save_feedback(recommendation_id, feedback.model_dump())
    return FeedbackResponse(
        recommendation_id=recommendation_id,
        stored=True,
        message="Feedback stored for future recommendation context.",
    )


@app.get("/api/reports/{equipment_id}", response_model=Recommendation)
def report(equipment_id: str):
    return generate_recommendation(DiagnosisRequest(equipment_id=equipment_id))


@app.get("/api/reports/{equipment_id}/markdown")
def report_markdown(equipment_id: str):
    recommendation = generate_recommendation(DiagnosisRequest(equipment_id=equipment_id))
    markdown = recommendation_to_markdown(recommendation)
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{equipment_id}-maintenance-report.md"'},
    )


@app.get("/api/dashboard/summary", response_model=DashboardSummary)
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
