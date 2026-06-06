import pytest
from fastapi.testclient import TestClient

from app.data import repository
from app.data.database import database_status, reset_database
from app.main import app
from app.services.retrieval import retrieve_evidence


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    reset_database()


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_status_reports_seeded_tables():
    status = database_status()
    assert status["schema_version"] == "2"
    assert status["counts"]["equipment"] == 3
    assert status["counts"]["document_chunks"] >= 4


def test_dashboard_summary_contains_sample_equipment():
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert payload["equipment_count"] == 3
    assert payload["active_alert_count"] == 3
    assert payload["highest_risk_equipment"]


def test_diagnosis_returns_evidence_and_actions():
    response = client.post(
        "/api/diagnose",
        json={"equipment_id": "RM-DRIVE-01", "alert_id": "ALT-1001"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["risk_level"] in {"high", "critical"}
    assert payload["evidence"]
    assert payload["immediate_actions"]
    assert payload["spares_strategy"]


def test_chat_returns_recommendation():
    response = client.post(
        "/api/chat",
        json={"equipment_id": "RM-DRIVE-01", "message": "Why is the mill drive vibrating?"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Recommended urgency" in payload["answer"]
    assert payload["recommendation"]["equipment_id"] == "RM-DRIVE-01"


def test_feedback_is_accepted():
    response = client.post(
        "/api/recommendations/rec-test/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "accepted",
            "actual_root_cause": "Coupling guard looseness from prior repair",
            "action_taken": "Retightened coupling guard and verified vibration trend",
            "outcome": "Vibration reduced after retightening",
            "notes": "Action matched inspection finding.",
        },
    )
    assert response.status_code == 200
    assert response.json()["stored"] is True
    stored = repository.list_feedback("RM-DRIVE-01")
    assert any(record["recommendation_id"] == "rec-test" for record in stored)
    assert any(record["equipment_id"] == "RM-DRIVE-01" for record in stored)


def test_feedback_is_reused_in_future_recommendations():
    client.post(
        "/api/recommendations/rec-learning/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "corrected",
            "actual_root_cause": "Loose foundation bolt resonance",
            "action_taken": "Retorque foundation bolts and recheck alignment",
            "outcome": "Vibration normalized after bolt retorque",
        },
    )

    response = client.post(
        "/api/diagnose",
        json={"equipment_id": "RM-DRIVE-01", "alert_id": "ALT-1001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Loose foundation bolt resonance" in payload["probable_root_causes"]
    assert any("Retorque foundation bolts" in action for action in payload["immediate_actions"])
    assert payload["learning_notes"]
    assert "engineer feedback record" in payload["report_summary"]


def test_document_ingestion_persists_to_repository():
    response = client.post(
        "/api/ingest/documents",
        json={
            "documents": [
                {
                    "id": "DOC-TEST-INGEST",
                    "source_type": "sop",
                    "equipment_id": "CC-PUMP-03",
                    "title": "Cooling Pump Seal Inspection SOP",
                    "content": "Seal leakage with rising motor current should trigger pump seal inspection.",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["documents"] == 1
    documents = repository.list_documents("CC-PUMP-03")
    assert any(document["id"] == "DOC-TEST-INGEST" for document in documents)
    chunks = repository.list_document_chunks("CC-PUMP-03")
    assert any(chunk["document_id"] == "DOC-TEST-INGEST" for chunk in chunks)


def test_document_file_upload_persists_and_chunks_text():
    response = client.post(
        "/api/ingest/document-file",
        data={"source_type": "sop", "equipment_id": "RM-DRIVE-01", "title": "Uploaded Coupling SOP"},
        files={
            "file": (
                "coupling_sop.txt",
                b"Inspect coupling alignment when drive vibration rises above baseline. Confirm lockout before inspection.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()
    document_id = payload["document"]["id"]
    assert payload["documents"] == 1
    assert payload["document"]["title"] == "Uploaded Coupling SOP"
    chunks = repository.list_document_chunks("RM-DRIVE-01")
    assert any(chunk["document_id"] == document_id for chunk in chunks)
    evidence = retrieve_evidence("coupling alignment baseline", "RM-DRIVE-01")
    assert any(item.source_id.startswith(f"{document_id}::chunk-") for item in evidence)


def test_document_file_upload_rejects_unsupported_type():
    response = client.post(
        "/api/ingest/document-file",
        data={"source_type": "manual", "equipment_id": "RM-DRIVE-01"},
        files={"file": ("image.bin", b"\x00\x01\x02", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "Unsupported document type" in response.json()["detail"]


def test_record_ingestion_persists_alert_to_api():
    response = client.post(
        "/api/ingest/records",
        json={
            "alerts": [
                {
                    "id": "ALT-TEST-3001",
                    "equipment_id": "CC-PUMP-03",
                    "timestamp": "2026-06-06T10:10:00+05:30",
                    "signal": "motor_current",
                    "value": 112.0,
                    "unit": "A",
                    "threshold": 95.0,
                    "severity": "medium",
                    "message": "Cooling pump motor current above baseline",
                }
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["counts"]["alerts"] == 1
    alerts = client.get("/api/alerts").json()
    assert any(alert["id"] == "ALT-TEST-3001" for alert in alerts)


def test_sensor_readings_are_seeded_and_available():
    response = client.get("/api/equipment/RM-DRIVE-01/sensor-readings")
    assert response.status_code == 200
    readings = response.json()
    assert any(reading["signal"] == "drive_end_vibration" for reading in readings)
    assert any(reading["signal"] == "bearing_temperature" for reading in readings)


def test_anomaly_endpoint_detects_vibration_and_temperature():
    response = client.get("/api/equipment/RM-DRIVE-01/anomalies")
    assert response.status_code == 200
    anomalies = response.json()
    signals = {item["signal"] for item in anomalies}
    assert "drive_end_vibration" in signals
    assert "bearing_temperature" in signals
    assert any(item["risk_level"] in {"high", "critical"} for item in anomalies)


def test_health_summary_includes_anomaly_findings():
    response = client.get("/api/equipment/RM-DRIVE-01/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["anomalies"]
    assert any("sensor anomaly" in note for note in payload["notes"])


def test_prediction_drivers_include_anomaly_explanations():
    response = client.post("/api/predict", json={"equipment_id": "RM-DRIVE-01"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["failure_probability"] > 0.5
    assert any("z-score" in driver for driver in payload["drivers"])


def test_prediction_drivers_include_feedback_history():
    client.post(
        "/api/recommendations/rec-prediction-feedback/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "accepted",
            "actual_root_cause": "Bearing cage defect confirmed by inspection",
            "outcome": "Bearing replacement scheduled for next outage",
        },
    )

    response = client.post("/api/predict", json={"equipment_id": "RM-DRIVE-01"})

    assert response.status_code == 200
    payload = response.json()
    assert any("engineer feedback" in driver for driver in payload["drivers"])
    assert any("Bearing cage defect" in driver for driver in payload["drivers"])


def test_markdown_report_export_contains_actions_and_evidence():
    response = client.get("/api/reports/RM-DRIVE-01/markdown")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Maintenance Decision Report: RM-DRIVE-01" in response.text
    assert "## Immediate Actions" in response.text
    assert "Hot Strip Mill Main Drive Vibration SOP" in response.text


def test_seeded_documents_are_chunked_for_local_retrieval():
    chunks = repository.list_document_chunks("RM-DRIVE-01")
    assert chunks
    assert all(chunk["embedding"] for chunk in chunks)
    assert any(chunk["document_id"] == "DOC-RM-SOP-01" for chunk in chunks)


def test_retrieval_returns_chunk_evidence_for_vibration_query():
    evidence = retrieve_evidence("drive end vibration bearing housing", "RM-DRIVE-01")
    assert evidence
    assert any(
        item.source_id.startswith("DOC-RM-SOP-01::chunk-") or item.source_id.startswith("DOC-RM-MAN-02::chunk-")
        for item in evidence
    )
    assert any("vibration" in item.excerpt.lower() or "bearing" in item.excerpt.lower() for item in evidence)
