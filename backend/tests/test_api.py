import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.data import repository
from app.data.database import database_status, reset_database
from app.main import app
from app.services.iot_streaming import (
    InvalidIoTMessage,
    StreamingIngestionService,
    build_dead_letter_payload,
    process_iot_message,
)
from app.services.retrieval import retrieve_evidence
from app.services.document_intelligence import document_intelligence
from app.services.maintenance_labeling import stored_labels


client = TestClient(app)
DEMO_PASSWORD = "DemoPass123!"


def auth_headers(email: str = "admin@plant.local", password: str = DEMO_PASSWORD) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


class _FakeNatsMessage:
    def __init__(self, payload, subject: str):
        self.data = json.dumps(payload).encode("utf-8")
        self.subject = subject
        self.acked = False
        self.nacked = False

    async def ack(self):
        self.acked = True

    async def nak(self):
        self.nacked = True


class _FakeJetStream:
    def __init__(self):
        self.published = []

    async def publish(self, subject: str, payload: bytes):
        self.published.append((subject, payload.decode("utf-8")))


@pytest.fixture(autouse=True)
def reset_db():
    reset_database()


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_status_reports_seeded_tables():
    status = database_status()
    assert status["schema_version"] == "5"
    assert status["counts"]["equipment"] == 5
    assert status["counts"]["document_chunks"] >= 8
    assert "document_intelligence" in status["counts"]
    assert "maintenance_labels" in status["counts"]
    assert "streaming_messages" in status["counts"]
    assert status["counts"]["users"] == 6


def test_login_returns_bearer_token_and_current_user():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@plant.local", "password": DEMO_PASSWORD},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_type"] == "bearer"
    assert payload["access_token"]
    assert payload["expires_in"] > 0
    assert payload["user"]["role"] == "admin"
    user = repository.get_user_by_email("admin@plant.local")
    assert user
    assert user["password_hash"] != DEMO_PASSWORD

    me_response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {payload['access_token']}"})
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "admin@plant.local"


def test_login_rejects_invalid_password():
    response = client.post(
        "/api/auth/login",
        json={"email": "admin@plant.local", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


def test_protected_endpoint_requires_token():
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


def test_operator_can_read_but_cannot_diagnose_or_ingest():
    headers = auth_headers("operator@plant.local")

    dashboard_response = client.get("/api/dashboard/summary", headers=headers)
    diagnose_response = client.post("/api/diagnose", json={"equipment_id": "RM-DRIVE-01"}, headers=headers)
    ingest_response = client.post("/api/ingest/records", json={"alerts": []}, headers=headers)

    assert dashboard_response.status_code == 200
    assert diagnose_response.status_code == 403
    assert ingest_response.status_code == 403


def test_reliability_engineer_can_ingest_and_view_streaming_status():
    headers = auth_headers("reliability@plant.local")

    ingest_response = client.post("/api/ingest/records", json={"alerts": []}, headers=headers)
    streaming_response = client.get("/api/streaming/status", headers=headers)

    assert ingest_response.status_code == 200
    assert streaming_response.status_code == 200


def test_admin_manages_users_and_deactivated_user_cannot_login():
    headers = auth_headers()

    create_response = client.post(
        "/api/users",
        json={
            "email": "contractor@plant.local",
            "display_name": "Contractor Planner",
            "role": "planner",
            "password": "Contractor123!",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    user = create_response.json()
    assert user["role"] == "planner"

    update_response = client.patch(
        f"/api/users/{user['id']}",
        json={"is_active": False, "display_name": "Inactive Contractor"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_active"] is False

    login_response = client.post(
        "/api/auth/login",
        json={"email": "contractor@plant.local", "password": "Contractor123!"},
    )
    assert login_response.status_code == 401

    reset_response = client.post(
        f"/api/users/{user['id']}/reset-password",
        json={"password": "NewContractor123!"},
        headers=headers,
    )
    assert reset_response.status_code == 200


def test_dashboard_summary_contains_sample_equipment():
    response = client.get("/api/dashboard/summary", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["equipment_count"] == 5
    assert payload["active_alert_count"] == 5
    assert len(payload["highest_risk_equipment"]) == 5
    equipment_ids = {item["equipment"]["id"] for item in payload["highest_risk_equipment"]}
    assert {"HYD-SYS-04", "OH-CRANE-05"}.issubset(equipment_ids)


def test_streaming_status_is_disabled_by_default():
    response = client.get("/api/streaming/status", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["state"] == "disabled"
    assert payload["stream"] == "MW_IOT"
    assert "steelplant.iot.sensor_readings" in payload["subjects"]


def test_iot_sensor_message_persists_and_is_idempotent():
    message = {
        "message_id": "iot-sensor-001",
        "schema_version": "1",
        "source": "caster-plc-gateway",
        "type": "sensor_reading",
        "timestamp": "2026-06-06T09:00:00+05:30",
        "payload": {
            "equipment_id": "CC-PUMP-03",
            "signal": "cooling_water_flow",
            "value": 1300.0,
            "unit": "m3/h",
            "threshold": 1100.0,
        },
    }

    result = process_iot_message(message, "steelplant.iot.sensor_readings")
    duplicate = process_iot_message(message, "steelplant.iot.sensor_readings")

    assert result.status == "processed"
    assert duplicate.status == "duplicate"
    readings = repository.list_sensor_readings("CC-PUMP-03", "cooling_water_flow")
    derived = [reading for reading in readings if reading["id"].startswith("SR-IOT-")]
    assert len(derived) == 1
    anomalies = client.get("/api/equipment/CC-PUMP-03/anomalies", headers=auth_headers()).json()
    assert any(item["signal"] == "cooling_water_flow" for item in anomalies)


def test_iot_alert_message_persists_and_affects_health():
    message = {
        "message_id": "iot-alert-001",
        "schema_version": "1",
        "source": "caster-plc-gateway",
        "type": "alert",
        "timestamp": "2026-06-06T09:05:00+05:30",
        "payload": {
            "equipment_id": "CC-PUMP-03",
            "signal": "motor_current",
            "value": 116.0,
            "unit": "A",
            "threshold": 95.0,
            "severity": "high",
            "message": "Cooling pump motor current above IoT gateway threshold",
        },
    }

    result = process_iot_message(message, "steelplant.iot.alerts")

    assert result.status == "processed"
    health = client.get("/api/equipment/CC-PUMP-03/health", headers=auth_headers()).json()
    assert any(alert["message"] == "Cooling pump motor current above IoT gateway threshold" for alert in health["active_alerts"])


def test_invalid_iot_payload_builds_dead_letter_payload():
    message = {
        "message_id": "iot-invalid-001",
        "schema_version": "1",
        "source": "caster-plc-gateway",
        "type": "sensor_reading",
        "timestamp": "2026-06-06T09:00:00+05:30",
        "payload": {"signal": "cooling_water_flow"},
    }

    with pytest.raises(InvalidIoTMessage) as exc_info:
        process_iot_message(message, "steelplant.iot.sensor_readings")

    dead_letter = build_dead_letter_payload(message, "steelplant.iot.sensor_readings", str(exc_info.value))
    assert dead_letter["subject"] == "steelplant.iot.sensor_readings"
    assert "equipment_id" in dead_letter["error"]
    assert dead_letter["raw_message"]["message_id"] == "iot-invalid-001"


def test_invalid_nats_message_is_published_to_dlq_and_acked():
    message = _FakeNatsMessage(
        {
            "message_id": "iot-invalid-nats-001",
            "schema_version": "1",
            "source": "caster-plc-gateway",
            "type": "sensor_reading",
            "timestamp": "2026-06-06T09:00:00+05:30",
            "payload": {"signal": "cooling_water_flow"},
        },
        "steelplant.iot.sensor_readings",
    )
    service = StreamingIngestionService()
    service._js = _FakeJetStream()

    asyncio.run(service.handle_nats_message(message))

    assert message.acked is True
    assert message.nacked is False
    assert service.status().failed_count == 1
    assert service._js.published
    dlq_subject, dlq_payload = service._js.published[0]
    assert dlq_subject == "steelplant.iot.dlq"
    assert "equipment_id" in json.loads(dlq_payload)["error"]


def test_persistence_failure_naks_nats_message(monkeypatch):
    def fail_add_records(_):
        raise RuntimeError("database locked")

    monkeypatch.setattr(repository, "add_records", fail_add_records)
    message = _FakeNatsMessage(
        {
            "message_id": "iot-nak-001",
            "schema_version": "1",
            "source": "caster-plc-gateway",
            "type": "alert",
            "timestamp": "2026-06-06T09:05:00+05:30",
            "payload": {
                "equipment_id": "CC-PUMP-03",
                "signal": "motor_current",
                "value": 116.0,
                "unit": "A",
                "threshold": 95.0,
                "severity": "high",
                "message": "Cooling pump motor current above IoT gateway threshold",
            },
        },
        "steelplant.iot.alerts",
    )
    service = StreamingIngestionService()

    asyncio.run(service.handle_nats_message(message))

    assert message.acked is False
    assert message.nacked is True
    assert service.status().failed_count == 1
    assert service.status().last_error == "database locked"


@pytest.mark.parametrize(
    ("equipment_id", "expected_signal", "query", "expected_document"),
    [
        (
            "HYD-SYS-04",
            "hydraulic_oil_temperature",
            "hydraulic pressure pulsation servo valve oil temperature",
            "Hydraulic System Temperature And Pulsation SOP",
        ),
        (
            "OH-CRANE-05",
            "hoist_motor_current",
            "overhead crane hoist current brake temperature wire rope",
            "Overhead Crane Hoist Current And Brake Temperature SOP",
        ),
    ],
)
def test_added_assets_have_health_prediction_and_retrieval(
    equipment_id: str,
    expected_signal: str,
    query: str,
    expected_document: str,
):
    headers = auth_headers()
    health_response = client.get(f"/api/equipment/{equipment_id}/health", headers=headers)
    assert health_response.status_code == 200
    health = health_response.json()
    assert health["active_alerts"]
    assert health["top_spares_constraints"]
    assert any(item["signal"] == expected_signal for item in health["anomalies"])
    assert any(item["context_class"] for item in health["anomalies"])
    assert health["risk_level"] in {"high", "critical"}

    prediction_response = client.post("/api/predict", json={"equipment_id": equipment_id}, headers=headers)
    assert prediction_response.status_code == 200
    prediction = prediction_response.json()
    assert prediction["failure_probability"] > 0.5
    assert any("z-score" in driver for driver in prediction["drivers"])
    assert prediction["reasoning_explanation"]["subject_type"] == "prediction"

    diagnosis_response = client.post("/api/diagnose", json={"equipment_id": equipment_id}, headers=headers)
    assert diagnosis_response.status_code == 200
    diagnosis = diagnosis_response.json()
    assert diagnosis["evidence"]
    assert any(item["title"] == expected_document for item in diagnosis["evidence"])

    evidence = retrieve_evidence(query, equipment_id)
    assert any(item.title == expected_document for item in evidence)


def test_diagnosis_returns_evidence_and_actions():
    response = client.post(
        "/api/diagnose",
        json={"equipment_id": "RM-DRIVE-01", "alert_id": "ALT-1001"},
        headers=auth_headers(),
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
        headers=auth_headers(),
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
        headers=auth_headers("maintenance@plant.local"),
    )
    assert response.status_code == 200
    assert response.json()["stored"] is True
    stored = repository.list_feedback("RM-DRIVE-01")
    assert any(record["recommendation_id"] == "rec-test" for record in stored)
    assert any(record["equipment_id"] == "RM-DRIVE-01" for record in stored)


def test_feedback_is_reused_in_future_recommendations():
    headers = auth_headers("maintenance@plant.local")
    client.post(
        "/api/recommendations/rec-learning/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "corrected",
            "actual_root_cause": "Loose foundation bolt resonance",
            "action_taken": "Retorque foundation bolts and recheck alignment",
            "outcome": "Vibration normalized after bolt retorque",
        },
        headers=headers,
    )

    response = client.post(
        "/api/diagnose",
        json={"equipment_id": "RM-DRIVE-01", "alert_id": "ALT-1001"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Loose foundation bolt resonance" in payload["probable_root_causes"]
    assert any("Retorque foundation bolts" in action for action in payload["immediate_actions"])
    assert payload["learning_notes"]
    assert payload["reasoning_explanation"]["subject_type"] == "recommendation"
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
        headers=auth_headers("reliability@plant.local"),
    )
    assert response.status_code == 200
    assert response.json()["documents"] == 1
    assert response.json()["intelligence"]
    documents = repository.list_documents("CC-PUMP-03")
    assert any(document["id"] == "DOC-TEST-INGEST" for document in documents)
    chunks = repository.list_document_chunks("CC-PUMP-03")
    assert any(chunk["document_id"] == "DOC-TEST-INGEST" for chunk in chunks)
    intelligence = document_intelligence("CC-PUMP-03")
    assert any(item.document_id == "DOC-TEST-INGEST" for item in intelligence)


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
        headers=auth_headers("reliability@plant.local"),
    )
    assert response.status_code == 200
    payload = response.json()
    document_id = payload["document"]["id"]
    assert payload["documents"] == 1
    assert payload["document"]["title"] == "Uploaded Coupling SOP"
    assert payload["intelligence"][0]["document_id"] == document_id
    chunks = repository.list_document_chunks("RM-DRIVE-01")
    assert any(chunk["document_id"] == document_id for chunk in chunks)
    evidence = retrieve_evidence("coupling alignment baseline", "RM-DRIVE-01")
    assert any(item.source_id.startswith(f"{document_id}::chunk-") for item in evidence)


def test_document_file_upload_rejects_unsupported_type():
    response = client.post(
        "/api/ingest/document-file",
        data={"source_type": "manual", "equipment_id": "RM-DRIVE-01"},
        files={"file": ("image.bin", b"\x00\x01\x02", "application/octet-stream")},
        headers=auth_headers("reliability@plant.local"),
    )
    assert response.status_code == 400
    assert "Unsupported document type" in response.json()["detail"]


def test_record_ingestion_persists_alert_to_api():
    headers = auth_headers("reliability@plant.local")
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
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["counts"]["alerts"] == 1
    alerts = client.get("/api/alerts", headers=headers).json()
    assert any(alert["id"] == "ALT-TEST-3001" for alert in alerts)


def test_sensor_readings_are_seeded_and_available():
    response = client.get("/api/equipment/RM-DRIVE-01/sensor-readings", headers=auth_headers())
    assert response.status_code == 200
    readings = response.json()
    assert any(reading["signal"] == "drive_end_vibration" for reading in readings)
    assert any(reading["signal"] == "bearing_temperature" for reading in readings)


def test_anomaly_endpoint_detects_vibration_and_temperature():
    response = client.get("/api/equipment/RM-DRIVE-01/anomalies", headers=auth_headers())
    assert response.status_code == 200
    anomalies = response.json()
    signals = {item["signal"] for item in anomalies}
    assert "drive_end_vibration" in signals
    assert "bearing_temperature" in signals
    assert any(item["risk_level"] in {"high", "critical"} for item in anomalies)
    assert any(item["context_class"] == "requires_investigation" for item in anomalies)
    assert all(item["recommended_inspection_steps"] for item in anomalies)


def test_health_summary_includes_anomaly_findings():
    response = client.get("/api/equipment/RM-DRIVE-01/health", headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["anomalies"]
    assert any("sensor anomaly" in note for note in payload["notes"])


def test_prediction_drivers_include_anomaly_explanations():
    response = client.post("/api/predict", json={"equipment_id": "RM-DRIVE-01"}, headers=auth_headers())
    assert response.status_code == 200
    payload = response.json()
    assert payload["failure_probability"] > 0.5
    assert any("z-score" in driver for driver in payload["drivers"])
    assert payload["reasoning_explanation"]["driver_explanations"]


def test_prediction_drivers_include_feedback_history():
    headers = auth_headers("maintenance@plant.local")
    client.post(
        "/api/recommendations/rec-prediction-feedback/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "accepted",
            "actual_root_cause": "Bearing cage defect confirmed by inspection",
            "outcome": "Bearing replacement scheduled for next outage",
        },
        headers=headers,
    )

    response = client.post("/api/predict", json={"equipment_id": "RM-DRIVE-01"}, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert any("engineer feedback" in driver for driver in payload["drivers"])
    assert any("Bearing cage defect" in driver for driver in payload["drivers"])
    labels = stored_labels("RM-DRIVE-01")
    assert any(label.source_type == "feedback" for label in labels)


def test_markdown_report_export_contains_actions_and_evidence():
    response = client.get("/api/reports/RM-DRIVE-01/markdown", headers=auth_headers("planner@plant.local"))
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "Maintenance Decision Report: RM-DRIVE-01" in response.text
    assert "## Immediate Actions" in response.text
    assert "## Reasoning Explanation" in response.text
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
    assert any(item.relevance_reason for item in evidence)


def test_maintenance_label_endpoint_generates_training_labels():
    headers = auth_headers("reliability@plant.local")

    response = client.post("/api/equipment/RM-DRIVE-01/maintenance-labels", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["equipment_id"] == "RM-DRIVE-01"
    assert payload["labels"]
    assert any(label["usable_for_training"] for label in payload["labels"])


def test_document_intelligence_endpoint_returns_extracted_profiles():
    headers = auth_headers("reliability@plant.local")
    client.post(
        "/api/ingest/documents",
        json={
            "documents": [
                {
                    "id": "DOC-INTEL-TEST",
                    "source_type": "manual",
                    "equipment_id": "RM-DRIVE-01",
                    "title": "Drive Bearing Manual",
                    "content": "Bearing vibration above 7 mm/s requires lockout and inspection of coupling spares.",
                }
            ]
        },
        headers=headers,
    )

    response = client.get("/api/equipment/RM-DRIVE-01/document-intelligence", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert any(item["document_id"] == "DOC-INTEL-TEST" for item in payload)
    assert any("bearing" in item["components"] for item in payload)
