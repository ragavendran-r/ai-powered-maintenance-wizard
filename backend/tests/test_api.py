import asyncio
import json
import os
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ["LLM_PROVIDER"] = "mock"
os.environ["LEARNING_ASYNC_ENABLED"] = "false"
os.environ["RAG_VECTOR_STORE"] = "sqlite"

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
from app.services.ai_client import active_llm_serving_config
from app.services.vector_store import VectorStoreHit
from app.services.learning_worker import process_learning_job_message


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
    assert status["schema_version"] == "12"
    assert status["counts"]["equipment"] == 5
    assert status["counts"]["asset_profiles"] == 5
    assert status["counts"]["asset_metric_snapshots"] == 15
    assert status["counts"]["asset_recommendations"] >= 10
    assert status["counts"]["asset_subsystems"] == 15
    assert status["counts"]["asset_reliability_metrics"] == 15
    assert status["counts"]["work_orders"] >= 5
    assert status["counts"]["documents"] >= 21
    assert status["counts"]["document_chunks"] >= 21
    assert "document_intelligence" in status["counts"]
    assert "maintenance_labels" in status["counts"]
    assert "streaming_messages" in status["counts"]
    assert "work_orders" in status["counts"]
    assert "work_order_logs" in status["counts"]
    assert status["counts"]["users"] == 8
    assert "learning_interactions" in status["counts"]
    assert "learning_examples" in status["counts"]
    assert status["counts"]["learning_model_versions"] >= 1
    assert status["counts"]["learning_prompt_versions"] >= 3
    assert "learning_jobs" in status["counts"]
    assert "learning_artifacts" in status["counts"]


def test_assets_api_returns_company_asset_table():
    response = client.get("/api/assets", headers=auth_headers("operator@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 5
    drive = next(item for item in payload if item["id"] == "RM-DRIVE-01")
    assert drive["asset_type"] == "AC main drive motor"
    assert drive["location_code"] == "HSM-FS-01"
    assert drive["health_score"] >= 0
    assert drive["open_work_orders"] >= 1
    assert drive["supervisor"] == "Maintenance Supervisor"


def test_assets_api_requires_authenticated_read_role():
    response = client.get("/api/assets")
    service_response = client.get("/api/assets", headers=auth_headers("iot-service@plant.local"))
    detail_response = client.get("/api/assets/RM-DRIVE-01", headers=auth_headers("iot-service@plant.local"))

    assert response.status_code == 401
    assert service_response.status_code == 403
    assert detail_response.status_code == 403


def test_asset_detail_api_is_seeded_and_data_backed():
    response = client.get("/api/assets/RM-DRIVE-01", headers=auth_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["name"] == "Hot Strip Mill Main Drive Motor"
    assert payload["profile"]["manufacturer"] == "Bharat Heavy Electricals"
    assert {metric["metric_key"] for metric in payload["metrics"]} >= {"health", "efficiency", "risk"}
    assert any(item["title"] == "Bearing housing inspection" for item in payload["recommendations"])
    assert any(item["name"] == "Drive train and coupling" for item in payload["subsystems"])
    assert any(item["metric_name"] == "MTBF" for item in payload["reliability_metrics"])
    assert any(chart["signal"] == "drive_end_vibration" for chart in payload["performance_charts"])
    assert any(document["source_type"] == "log" for document in payload["documents"])
    assert any(event["issue"] for event in payload["maintenance_events"])
    assert any(order["equipment_id"] == "RM-DRIVE-01" for order in payload["work_orders"])
    assert payload["knowledge"]
    assert payload["prediction"]["drivers"]


def test_all_asset_detail_tabs_have_seeded_data_for_each_company_asset():
    expected_sources = {"sop", "manual", "log", "history"}
    asset_ids = ["RM-DRIVE-01", "BF-BLOWER-02", "CC-PUMP-03", "HYD-SYS-04", "OH-CRANE-05"]

    for asset_id in asset_ids:
        response = client.get(
            f"/api/assets/{asset_id}?sections=maintenance,performance,reliability,documents,work_orders",
            headers=auth_headers("operator@plant.local"),
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["profile"]["equipment_id"] == asset_id
        assert payload["maintenance_events"], asset_id
        assert payload["work_orders"], asset_id
        assert payload["performance_charts"], asset_id
        assert payload["reliability_metrics"], asset_id
        assert {document["source_type"] for document in payload["documents"]} >= expected_sources
        assert payload["knowledge"], asset_id


def test_asset_detail_api_can_load_sections_independently():
    summary_response = client.get("/api/assets/RM-DRIVE-01?sections=summary", headers=auth_headers())

    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["profile"]["name"] == "Hot Strip Mill Main Drive Motor"
    assert any(item["title"] == "Bearing housing inspection" for item in summary["recommendations"])
    assert any(item["name"] == "Drive train and coupling" for item in summary["subsystems"])
    assert summary["maintenance_events"] == []
    assert summary["performance_charts"] == []
    assert summary["documents"] == []
    assert summary["knowledge"] == []
    assert summary["reliability_metrics"] == []
    assert summary["work_orders"] == []
    assert summary["prediction"] is None

    documents_response = client.get("/api/assets/RM-DRIVE-01?sections=documents", headers=auth_headers())

    assert documents_response.status_code == 200
    documents = documents_response.json()
    assert documents["recommendations"] == []
    assert any(document["source_type"] == "sop" for document in documents["documents"])
    assert len(documents["knowledge"]) > 0


def test_asset_reliability_prediction_stream_requires_live_llm():
    response = client.get("/api/assets/RM-DRIVE-01/reliability/stream", headers=auth_headers())

    assert response.status_code == 200
    assert '"type": "meta"' in response.text
    assert '"used_live_provider": false' in response.text
    assert '"type": "error"' in response.text
    assert '"type": "done"' not in response.text


def test_repository_initializes_once_under_concurrent_access(monkeypatch):
    calls = 0

    def fake_initialize_database(seed: bool = True):
        nonlocal calls
        calls += 1

    monkeypatch.setattr(repository, "_READY", False)
    monkeypatch.setattr(repository, "initialize_database", fake_initialize_database)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: repository.ensure_ready(), range(16)))

    assert calls == 1


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
    with client.stream("POST", "/api/diagnose/stream", json={"equipment_id": "RM-DRIVE-01"}, headers=headers) as stream_response:
        assert stream_response.status_code == 403
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


def test_work_orders_are_seeded_and_filter_by_asset():
    headers = auth_headers()

    response = client.get("/api/work-orders?equipment_id=RM-DRIVE-01", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert any(item["id"] == "WO-8304" for item in payload)
    assert all(item["equipment_id"] == "RM-DRIVE-01" for item in payload)
    assert payload[0]["logs"] == []


def test_technician_sees_only_assigned_work_orders():
    headers = auth_headers("technician@plant.local")

    response = client.get("/api/work-orders", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert {item["id"] for item in payload} == {"WO-8304"}
    assert {item["assigned_to"] for item in payload} == {"Maintenance Technician"}


def test_admin_and_supervisor_can_list_assignment_technicians():
    admin_response = client.get("/api/users/technicians", headers=auth_headers())
    supervisor_response = client.get("/api/users/technicians", headers=auth_headers("supervisor@plant.local"))
    technician_response = client.get("/api/users/technicians", headers=auth_headers("technician@plant.local"))

    assert admin_response.status_code == 200
    assert supervisor_response.status_code == 200
    assert technician_response.status_code == 403
    assert [user["role"] for user in admin_response.json()] == ["maintenance_technician"]
    assert [user["display_name"] for user in supervisor_response.json()] == ["Maintenance Technician"]


def test_assigned_technician_can_start_approved_or_material_waiting_work_order():
    technician_headers = auth_headers("technician@plant.local")
    admin_headers = auth_headers()

    approved_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"status": "INPRG"},
        headers=technician_headers,
    )
    assert approved_response.status_code == 200
    assert approved_response.json()["status"] == "INPRG"

    material_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"status": "WMATL"},
        headers=admin_headers,
    )
    assert material_response.status_code == 200

    started_from_material_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"status": "INPRG"},
        headers=technician_headers,
    )
    assert started_from_material_response.status_code == 200
    assert started_from_material_response.json()["status"] == "INPRG"


def test_technician_cannot_start_unassigned_work_order():
    response = client.patch(
        "/api/work-orders/WO-8311",
        json={"status": "INPRG"},
        headers=auth_headers("technician@plant.local"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Technician can update only assigned work orders"


def test_only_waiting_approval_work_orders_can_be_approved():
    headers = auth_headers()

    approve_response = client.patch("/api/work-orders/WO-8311", json={"status": "APPR"}, headers=headers)
    material_response = client.patch("/api/work-orders/WO-8275", json={"status": "APPR"}, headers=headers)

    assert approve_response.status_code == 200
    assert approve_response.json()["status"] == "APPR"
    assert material_response.status_code == 400
    assert material_response.json()["detail"] == "Only WAPPR work orders can be approved"


def test_create_update_and_log_work_order():
    headers = auth_headers("planner@plant.local")

    create_response = client.post(
        "/api/work-orders",
        json={
            "equipment_id": "BF-BLOWER-02",
            "title": "Inspect blower actuator linkage",
            "description": "Inspect inlet guide vane actuator linkage after pressure variance trend.",
            "priority": 2,
            "work_type": "CM",
            "failure_class": "CTRL",
            "problem_code": "IGVACT",
            "classification": "Control actuator",
            "assigned_to": "Reliability Engineer",
            "supervisor": "Blast Furnace Supervisor",
            "due_date": "2026-06-14T09:00:00+05:30",
            "recommended_action": "Stroke actuator and verify position feedback.",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    work_order = create_response.json()
    assert work_order["id"].startswith("WO-")
    assert work_order["status"] == "WAPPR"

    update_response = client.patch(
        f"/api/work-orders/{work_order['id']}",
        json={"status": "INPRG", "problem_code": "LWTQCONNECT"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "INPRG"
    assert update_response.json()["problem_code"] == "LWTQCONNECT"

    log_response = client.post(
        f"/api/work-orders/{work_order['id']}/logs",
        json={"author": "Reliability Engineer", "entry_type": "observation", "content": "Actuator linkage has minor play."},
        headers=headers,
    )
    assert log_response.status_code == 200
    assert any("minor play" in item["content"] for item in log_response.json()["logs"])


def test_operator_cannot_create_work_order():
    response = client.post(
        "/api/work-orders",
        json={
            "equipment_id": "BF-BLOWER-02",
            "title": "Inspect blower actuator linkage",
            "description": "Inspect inlet guide vane actuator linkage after pressure variance trend.",
            "priority": 2,
            "work_type": "CM",
            "failure_class": "CTRL",
            "problem_code": "IGVACT",
            "classification": "Control actuator",
            "assigned_to": "Reliability Engineer",
            "supervisor": "Blast Furnace Supervisor",
            "due_date": "2026-06-14T09:00:00+05:30",
            "recommended_action": "Stroke actuator and verify position feedback.",
        },
        headers=auth_headers("operator@plant.local"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role permissions"


def test_technician_assistant_suggests_problem_code_from_observation():
    headers = auth_headers("technician@plant.local")

    response = client.post(
        "/api/work-orders/technician-assist",
        json={"work_order_id": "WO-8304", "observation": "Connections 3 and 5 were loose; insulation has hotspots."},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["work_order_id"] == "WO-8304"
    assert payload["suggested_problem_code"] in {"LWTQCONNECT", "INSUL"}
    assert payload["live_directions"]
    assert payload["completion_summary"]
    assert payload["evidence"]

    forbidden_response = client.post(
        "/api/work-orders/technician-assist",
        json={"work_order_id": "WO-8304", "observation": "Connections are loose."},
        headers=auth_headers("supervisor@plant.local"),
    )
    assert forbidden_response.status_code == 403


def test_technician_assistant_streams_sse_response():
    headers = auth_headers("technician@plant.local")

    with client.stream(
        "POST",
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "Connections 3 and 5 were loose."},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert '"type": "meta"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body
    assert "Neo" in body
    assert "LWTQCONNECT" in body

    forbidden_response = client.post(
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "Connections are loose."},
        headers=auth_headers("supervisor@plant.local"),
    )
    assert forbidden_response.status_code == 403


def test_supervisor_assistant_reviews_follow_up_queue_and_drafts_order():
    headers = auth_headers("supervisor@plant.local")

    response = client.post(
        "/api/work-orders/supervisor-assist",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up", "question": "What needs follow-up?"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "work order" in payload["summary"].lower()
    assert payload["follow_up_actions"]
    assert "WO-8297" in payload["referenced_work_orders"]
    assert payload["draft_work_order"]["equipment_id"] == "OH-CRANE-05"

    forbidden_response = client.post(
        "/api/work-orders/supervisor-assist",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up"},
        headers=auth_headers("technician@plant.local"),
    )
    assert forbidden_response.status_code == 403


def test_supervisor_assistant_streams_sse_response():
    headers = auth_headers("supervisor@plant.local")

    with client.stream(
        "POST",
        "/api/work-orders/supervisor-assist/stream",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up", "question": "What needs follow-up?"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert '"type": "meta"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body
    assert "Neo" in body
    assert "WO-8297" in body

    forbidden_response = client.post(
        "/api/work-orders/supervisor-assist/stream",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up"},
        headers=auth_headers("technician@plant.local"),
    )
    assert forbidden_response.status_code == 403


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


def test_diagnosis_stream_returns_morpheus_progress_and_recommendation():
    with client.stream(
        "POST",
        "/api/diagnose/stream",
        json={"equipment_id": "RM-DRIVE-01", "alert_id": "ALT-1001"},
        headers=auth_headers(),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "Morpheus is reviewing asset health" in body
    assert '"type": "done"' in body
    assert '"recommendation"' in body
    assert "RM-DRIVE-01" in body


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


def test_neo_chat_returns_dashboard_table_for_read_roles():
    response = client.post(
        "/api/neo/chat",
        json={"message": "Show work orders needing follow-up"},
        headers=auth_headers("operator@plant.local"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Neo" in payload["answer"] or payload["answer"]
    assert payload["table"]["title"] == "Work Orders"
    assert "Work order" in payload["table"]["columns"]
    assert payload["table"]["rows"]
    assert payload["used_live_provider"] is False
    assert payload["provider"] == "deterministic"
    assert all(row["Follow-up"] == "Yes" for row in payload["table"]["rows"])


def test_neo_chat_stream_returns_sse_done_event_for_table_query():
    with client.stream(
        "POST",
        "/api/neo/chat/stream",
        json={"message": "Show work orders needing follow-up"},
        headers=auth_headers("operator@plant.local"),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "data:" in body
    assert '"type": "done"' in body
    assert '"title": "Work Orders"' in body
    assert '"provider": "deterministic"' in body


def test_neo_chat_returns_asset_table_without_llm():
    response = client.post(
        "/api/neo/chat",
        json={"message": "Show assets"},
        headers=auth_headers("operator@plant.local"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"]["title"] == "Assets"
    assert "Asset" in payload["table"]["columns"]
    assert payload["table"]["rows"]
    assert payload["used_live_provider"] is False
    assert payload["provider"] == "deterministic"


def test_neo_user_table_is_role_limited():
    operator_response = client.post(
        "/api/neo/chat",
        json={"message": "Show users and roles"},
        headers=auth_headers("operator@plant.local"),
    )
    assert operator_response.status_code == 200
    operator_payload = operator_response.json()
    assert operator_payload["table"]["title"] == "Current User"
    assert operator_payload["provider"] == "deterministic"

    admin_response = client.post(
        "/api/neo/chat",
        json={"message": "Show users and roles"},
        headers=auth_headers(),
    )
    assert admin_response.status_code == 200
    admin_payload = admin_response.json()
    assert admin_payload["table"]["title"] == "Users"
    assert admin_payload["provider"] == "deterministic"


def test_neo_user_table_supports_role_filters_without_llm():
    response = client.post(
        "/api/neo/chat",
        json={"message": "list all supervisors"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"]["title"] == "Supervisors"
    assert payload["table"]["rows"]
    assert {row["Role"] for row in payload["table"]["rows"]} == {"maintenance_supervisor"}
    assert payload["used_live_provider"] is False
    assert payload["provider"] == "deterministic"


def test_neo_welcome_highlights_assigned_technician_work():
    response = client.get("/api/neo/welcome", headers=auth_headers("technician@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["action"]["type"] == "neo_welcome"
    assert payload["action"]["target_id"] == "WO-8304"
    assert "Immediate attention" in payload["answer"]
    assert "Primary Work Order: WO-8304" in payload["answer"]
    assert "Closeout" in payload["answer"]
    assert payload["table"]["title"] == "Your Assigned Work"
    assert {row["Work order"] for row in payload["table"]["rows"]} == {"WO-8304"}


def test_neo_welcome_highlights_supervisor_approvals_and_followups():
    response = client.get("/api/neo/welcome", headers=auth_headers("supervisor@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["table"]["title"] == "Supervisor Attention"
    assert "waiting for approval" in payload["answer"]
    assert any(row["Work order"] == "WO-8311" for row in payload["table"]["rows"])


def test_neo_welcome_is_read_only_for_operator_attention():
    response = client.get("/api/neo/welcome", headers=auth_headers("operator@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["table"]["title"] == "Operator Attention"
    assert "read-only" in payload["answer"]
    assert payload["action"]["status"] == "completed"


def test_neo_returns_asset_performance_summary_from_backend_data():
    response = client.post(
        "/api/neo/chat",
        json={"message": "performance summary for BF-BLOWER-02"},
        headers=auth_headers("operator@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["table"]["title"] == "BF-BLOWER-02 Performance"
    assert payload["action"]["type"] == "asset_performance"
    assert payload["action"]["status"] == "completed"
    assert {row["Metric"] for row in payload["table"]["rows"]} >= {"Health", "Efficiency", "Risk"}


def test_neo_returns_asset_documents_from_backend_data():
    response = client.post(
        "/api/neo/chat",
        json={"message": "show documents for BF-BLOWER-02"},
        headers=auth_headers("operator@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["table"]["title"] == "BF-BLOWER-02 Documents"
    assert any(row["Source"] in {"manual", "sop", "log", "history"} for row in payload["table"]["rows"])


def test_neo_technician_next_steps_use_assigned_work_order_only():
    response = client.post(
        "/api/neo/chat",
        json={"message": "what are next steps for my assigned work order"},
        headers=auth_headers("technician@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["action"]["type"] == "work_order_next_steps"
    assert payload["action"]["target_id"] == "WO-8304"
    assert payload["table"]["rows"][0]["Work order"] == "WO-8304"
    assert "assigned to you" in payload["answer"].lower()


def test_neo_can_create_work_order_for_critical_asset_when_role_allows():
    response = client.post(
        "/api/neo/chat",
        json={"message": "create work order for critical asset"},
        headers=auth_headers("planner@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["action"]["type"] == "create_work_order"
    assert payload["action"]["status"] == "completed"
    assert payload["action"]["target_id"].startswith("WO-")
    assert payload["table"]["title"] == "Created Work Order"
    created = repository.get_work_order(payload["action"]["target_id"])
    assert created
    assert created["status"] == "WAPPR"
    assert created["priority"] == 1


def test_neo_blocks_work_order_creation_for_operator():
    response = client.post(
        "/api/neo/chat",
        json={"message": "create work order for BF-BLOWER-02"},
        headers=auth_headers("operator@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "deterministic"
    assert payload["action"]["status"] == "not_allowed"
    assert payload["table"] is None


def test_neo_can_manage_user_data_for_admin_only():
    admin_response = client.post(
        "/api/neo/chat",
        json={"message": "deactivate user operator@plant.local"},
        headers=auth_headers(),
    )

    assert admin_response.status_code == 200
    admin_payload = admin_response.json()
    assert admin_payload["action"]["type"] == "manage_user"
    assert admin_payload["action"]["status"] == "completed"
    assert admin_payload["table"]["rows"][0]["Status"] == "Inactive"
    assert repository.get_user_by_email("operator@plant.local")["is_active"] is False

    reset_database()
    operator_response = client.post(
        "/api/neo/chat",
        json={"message": "deactivate user technician@plant.local"},
        headers=auth_headers("operator@plant.local"),
    )
    assert operator_response.status_code == 200
    operator_payload = operator_response.json()
    assert operator_payload["action"]["status"] == "not_allowed"


def test_neo_general_maintenance_query_uses_evidence_fallback_when_llm_is_slow():
    response = client.post(
        "/api/neo/chat",
        json={"message": "how to inspect Blast Furnace Combustion Air Blower"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"] is None
    assert payload["used_live_provider"] is False
    assert payload["provider"] == "mock"
    assert "BF-BLOWER-02" in payload["answer"]
    assert "### Safety Checks" in payload["answer"]
    assert "### Inspection Steps" in payload["answer"]
    assert "### Evidence Used" in payload["answer"]
    assert "inlet guide vane" in payload["answer"].lower()
    assert "Ask me to show assets" not in payload["answer"]


def test_neo_chat_stream_returns_token_events_for_general_queries():
    with client.stream(
        "POST",
        "/api/neo/chat/stream",
        json={"message": "how to inspect Blast Furnace Combustion Air Blower"},
        headers=auth_headers(),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert '"type": "meta"' in body
    assert '"type": "token"' in body
    assert '"type": "done"' in body
    assert "BF-BLOWER-02" in body
    assert "Safety Checks" in body


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


def test_feedback_refreshes_approved_learning_examples_and_retrieval():
    headers = auth_headers("maintenance@plant.local")
    client.post(
        "/api/recommendations/rec-learning-retrieval/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "accepted",
            "actual_root_cause": "Loose foundation bolt resonance",
            "action_taken": "Retorque foundation bolts and recheck alignment",
            "outcome": "Vibration normalized after bolt retorque",
        },
        headers=headers,
    )

    examples = repository.list_learning_examples(approved_only=True, equipment_id="RM-DRIVE-01")
    assert any(example["source_type"] == "feedback" for example in examples)
    feedback_example = next(example for example in examples if example["source_type"] == "feedback")
    assert feedback_example["judge_score"] >= 0.65
    assert feedback_example["judge_label"] == "training_worthy"
    evidence = retrieve_evidence("Loose foundation bolt resonance retorque", "RM-DRIVE-01", limit=6)
    assert any(item.source_type == "learning_example" for item in evidence)


def test_retrieval_uses_vector_store_hits(monkeypatch):
    monkeypatch.setattr("app.services.retrieval.configured_vector_store_name", lambda: "qdrant")
    monkeypatch.setattr(
        "app.services.retrieval.search_document_chunks",
        lambda query, equipment_id, limit: [
            VectorStoreHit(
                source_id="DOC-QDRANT::chunk-000",
                title="Qdrant indexed SOP",
                content="Vector database evidence for blast furnace blower actuator inspection.",
                source_type="sop",
                equipment_id="BF-BLOWER-02",
                score=0.91,
            )
        ],
    )

    evidence = retrieve_evidence("blower actuator inspection", "BF-BLOWER-02", limit=1, use_reranker=False)

    assert evidence[0].source_id == "DOC-QDRANT::chunk-000"
    assert evidence[0].relevance_reason == "Matched by qdrant vector search."


def test_learning_review_endpoints_are_role_gated_and_export_jsonl():
    operator_response = client.get("/api/learning/summary", headers=auth_headers("operator@plant.local"))
    assert operator_response.status_code == 403

    headers = auth_headers("reliability@plant.local")
    refresh_response = client.post("/api/learning/examples/refresh", headers=headers)
    assert refresh_response.status_code == 200
    assert any(example["approved"] for example in refresh_response.json())

    summary_response = client.get("/api/learning/summary", headers=headers)
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["counts"]["examples"] >= 1
    assert summary["model_versions"]
    assert summary["prompt_versions"]
    assert any(example["judge_score"] > 0 for example in summary["recent_examples"])
    assert "recent_jobs" in summary
    assert summary["vector_store"]["store"] == "sqlite"

    dataset_response = client.post(
        "/api/learning/datasets",
        json={"name": "test-learning-snapshot", "approved_only": True, "min_judge_score": 0.65},
        headers=headers,
    )
    assert dataset_response.status_code == 200
    dataset = dataset_response.json()
    assert dataset["example_count"] >= 1
    assert '"messages"' in dataset["jsonl_content"]

    export_response = client.get(f"/api/learning/datasets/{dataset['id']}/jsonl", headers=headers)
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("application/jsonl")
    first_line = export_response.text.splitlines()[0]
    assert json.loads(first_line)["messages"][0]["role"] == "system"

    model_response = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-lora-candidate",
            "base_model": "qwen2.5-7b-instruct",
            "adapter_path": "file:///models/qwen2.5-lora",
            "status": "candidate",
            "notes": "Local PEFT adapter candidate.",
        },
        headers=headers,
    )
    assert model_response.status_code == 200
    model = model_response.json()
    assert model["adapter_path"] == "file:///models/qwen2.5-lora"

    evaluation_response = client.post(
        "/api/learning/evaluations",
        json={
            "dataset_id": dataset["id"],
            "model_version_id": model["id"],
            "prompt_version_id": "prompt-neo-default",
            "min_quality_score": 0.6,
        },
        headers=headers,
    )
    assert evaluation_response.status_code == 200
    evaluation = evaluation_response.json()
    assert evaluation["dataset_id"] == dataset["id"]
    assert evaluation["model_version_id"] == model["id"]
    assert evaluation["metrics"]["example_count"] == dataset["example_count"]
    assert evaluation["metrics"]["average_judge_score"] >= 0.65
    assert evaluation["passed"] is True

    evaluations_response = client.get("/api/learning/evaluations", headers=headers)
    assert evaluations_response.status_code == 200
    assert any(item["id"] == evaluation["id"] for item in evaluations_response.json())

    promotion_response = client.post(
        "/api/learning/model-versions/promote",
        json={
            "model_version_id": model["id"],
            "evaluation_run_id": evaluation["id"],
            "notes": "Promote after passed local evaluation.",
        },
        headers=headers,
    )
    assert promotion_response.status_code == 200
    promotion = promotion_response.json()
    assert promotion["model_version_id"] == model["id"]
    assert promotion["action"] == "promote"

    serving = active_llm_serving_config(
        SimpleNamespace(
            llm_provider="openai",
            openai_model="env-model",
            openai_api_key="unused",
            openai_base_url="http://localhost:1234/v1",
            ollama_model="env-ollama",
            ollama_base_url="http://localhost:11434",
            llm_use_active_learning_model=True,
        )
    )
    assert serving.source == "learning_active_model"
    assert serving.provider == "openai"
    assert serving.openai_model == model["model_name"]
    assert serving.active_model_version_id == model["id"]
    assert serving.adapter_path == model["adapter_path"]

    mock_serving = active_llm_serving_config(
        SimpleNamespace(
            llm_provider="mock",
            openai_model="env-model",
            openai_api_key=None,
            openai_base_url="http://localhost:1234/v1",
            ollama_model="env-ollama",
            ollama_base_url="http://localhost:11434",
            llm_use_active_learning_model=True,
        )
    )
    assert mock_serving.source == "environment"
    assert mock_serving.provider == "mock"
    assert "disabled for mock provider" in mock_serving.warning

    peft_job_response = client.post(
        "/api/learning/jobs/peft",
        json={
            "dataset_id": dataset["id"],
            "model_version_id": model["id"],
            "prompt_version_id": "prompt-neo-default",
            "adapter_name": "maintenance-wizard-qwen-lora",
            "base_model": "qwen2.5-7b-instruct",
            "training_config": {"method": "lora", "max_examples": dataset["example_count"]},
        },
        headers=headers,
    )
    assert peft_job_response.status_code == 200
    peft_job = peft_job_response.json()
    assert peft_job["job_type"] == "peft_tuning"
    assert peft_job["subject"] == "maintenance.learning.peft.requested"
    assert peft_job["status"] == "queued"
    assert peft_job["input_refs"]["dataset_id"] == dataset["id"]
    assert peft_job["output_refs"]["dispatch"] == "disabled"

    jobs_response = client.get("/api/learning/jobs", headers=headers)
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()
    assert any(job["id"] == peft_job["id"] for job in jobs)
    assert any(job["job_type"] == "dataset_snapshot" and job["status"] == "completed" for job in jobs)


def test_peft_learning_job_publishes_when_async_learning_is_enabled(monkeypatch):
    headers = auth_headers("reliability@plant.local")
    client.post("/api/learning/examples/refresh", headers=headers)
    dataset = client.post(
        "/api/learning/datasets",
        json={"name": "async-learning-snapshot", "approved_only": True, "min_judge_score": 0.65},
        headers=headers,
    ).json()
    model = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-lora-async",
            "base_model": "qwen2.5-7b-instruct",
            "adapter_path": "file:///models/qwen2.5-lora-async",
            "status": "candidate",
        },
        headers=headers,
    ).json()
    published_jobs = []

    async def fake_publish(job):
        published_jobs.append(job)

    monkeypatch.setattr(
        "app.services.learning.get_settings",
        lambda: SimpleNamespace(
            learning_async_enabled=True,
            learning_nats_subject_prefix="maintenance.learning",
            learning_nats_stream="MW_LEARNING",
        ),
    )
    monkeypatch.setattr("app.services.learning._publish_learning_job", fake_publish)

    response = client.post(
        "/api/learning/jobs/peft",
        json={
            "dataset_id": dataset["id"],
            "model_version_id": model["id"],
            "prompt_version_id": "prompt-neo-default",
            "adapter_name": "maintenance-wizard-qwen-lora",
        },
        headers=headers,
    )

    assert response.status_code == 200
    job = response.json()
    assert job["status"] == "published"
    assert job["subject"] == "maintenance.learning.peft.requested"
    assert job["output_refs"]["stream"] == "MW_LEARNING"
    assert published_jobs[0]["id"] == job["id"]


def test_learning_worker_prepares_peft_artifacts(monkeypatch, tmp_path):
    headers = auth_headers("reliability@plant.local")
    client.post("/api/learning/examples/refresh", headers=headers)
    dataset = client.post(
        "/api/learning/datasets",
        json={"name": "worker-learning-snapshot", "approved_only": True, "min_judge_score": 0.65},
        headers=headers,
    ).json()
    model = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-worker",
            "base_model": "qwen2.5-7b-instruct",
            "adapter_path": None,
            "status": "candidate",
        },
        headers=headers,
    ).json()
    peft_job = client.post(
        "/api/learning/jobs/peft",
        json={
            "dataset_id": dataset["id"],
            "model_version_id": model["id"],
            "prompt_version_id": "prompt-neo-default",
            "adapter_name": "maintenance-wizard-worker-lora",
            "training_config": {"method": "lora", "epochs": 1},
        },
        headers=headers,
    ).json()
    monkeypatch.setattr(
        "app.services.learning.get_settings",
        lambda: SimpleNamespace(learning_artifact_dir=tmp_path),
    )

    processed = process_learning_job_message(
        {
            "schema_version": "1",
            "job_id": peft_job["id"],
            "job_type": "peft_tuning",
            "requested_by": "reliability@plant.local",
            "correlation_id": peft_job["correlation_id"],
            "input_refs": peft_job["input_refs"],
        },
        peft_job["subject"],
    )

    assert processed.status == "completed"
    completed_job = repository.get_learning_job(peft_job["id"])
    assert completed_job["status"] == "completed"
    assert completed_job["output_refs"]["training_status"] == "awaiting_external_peft_trainer"
    artifacts = repository.list_learning_artifacts(job_id=peft_job["id"])
    assert {artifact["artifact_type"] for artifact in artifacts} == {
        "peft_dataset_jsonl",
        "peft_training_manifest",
    }
    for artifact in artifacts:
        assert artifact["content_hash"]
        assert artifact["uri"].startswith(str(tmp_path))


def test_learning_example_can_be_scored_by_judge_endpoint():
    headers = auth_headers("reliability@plant.local")
    refresh_response = client.post("/api/learning/examples/refresh", headers=headers)
    example = refresh_response.json()[0]

    response = client.post(f"/api/learning/examples/{example['id']}/judge", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["judge_score"] >= 0
    assert payload["judge_label"] in {"training_worthy", "review", "reject"}
    assert payload["judge_rationale"]


def test_learning_example_approval_can_be_changed_by_engineer():
    headers = auth_headers("reliability@plant.local")
    refresh_response = client.post("/api/learning/examples/refresh", headers=headers)
    example = next(item for item in refresh_response.json() if item["source_type"] == "document")

    response = client.patch(
        f"/api/learning/examples/{example['id']}",
        json={"approved": True},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["approved"] is True


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
