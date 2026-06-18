import asyncio
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

TEST_DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "test_maintenance_wizard.db"

os.environ["DATABASE_PATH"] = str(TEST_DATABASE_PATH)
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LEARNING_ASYNC_ENABLED"] = "false"
os.environ["RAG_VECTOR_STORE"] = "sqlite"

from app.core.config import get_settings
from app.data import repository
from app.data.database import database_status, reset_database
from app.main import app
from app.services.iot_streaming import (
    InvalidIoTMessage,
    StreamingIngestionService,
    build_dead_letter_payload,
    process_iot_message,
)
from app.services.llm import LLMTextResponse
from app.services.retrieval import retrieve_evidence
from app.services.document_intelligence import document_intelligence
from app.services.maintenance_labeling import stored_labels
from app.services.ai_client import active_llm_serving_config
from app.services.artifact_store import (
    cleanup_expired_filesystem_artifacts,
    find_expired_filesystem_artifacts,
    artifact_store_status,
    store_learning_artifact_file,
    validate_learning_artifact_lifecycle_config,
)
from app.services.vector_store import VectorStoreHit, embedding_profile_status
from app.services.embeddings import embedding_profile_id
from app.services.learning_worker import process_learning_job_message
from app.services.learning import learning_stream_subjects


client = TestClient(app)
DEMO_PASSWORD = "DemoPass123!"


def auth_headers(email: str = "admin@plant.local", password: str = DEMO_PASSWORD) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def default_live_text_assistant(monkeypatch):
    import app.services.neo_assistant as neo_module
    import app.services.work_order_assistant as work_order_module

    class FakeLiveTextClient:
        @property
        def provider_name(self):
            return "openai"

        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            if _fake_no_live_response(prompt):
                return fallback_factory("mock", "no live LLM provider is configured for this test")
            return LLMTextResponse(
                content=_fake_live_text(prompt),
                used_live_provider=True,
                provider="openai",
            )

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            if _fake_no_live_response(prompt):
                yield fallback_factory("mock", "no live LLM provider is configured for this test")
                return
            yield LLMTextResponse(
                content=_fake_live_text(prompt),
                used_live_provider=True,
                provider="openai",
            )

        def complete_model(
            self,
            prompt,
            response_model,
            system_prompt,
            fallback_factory,
            max_tokens=None,
            timeout_seconds=None,
            response_format=None,
        ):
            return fallback_factory("mock", "no live structured LLM provider is configured for this test")

    fake_client = FakeLiveTextClient()
    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: fake_client)
    monkeypatch.setattr(work_order_module, "configured_llm_client", lambda: fake_client)


def _fake_live_text(prompt: str) -> str:
    if "WO-8297" in prompt:
        return "Trinity reviewed WO-8297 and recommends supervisor follow-up."
    if "WO-8304" in prompt:
        return "Trinity reviewed WO-8304 and recommends the next safe execution step."
    if "RM-DRIVE-01" in prompt:
        return "Ragav, RM-DRIVE-01 is the grounded asset context for the next maintenance decision."
    return "Neo answered using the live configured LLM and grounded application context."


def _fake_no_live_response(prompt: str) -> bool:
    lowered = prompt.lower()
    return "what is the time now" in lowered or "when is drive end bearing expected to be available" in lowered


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
    if get_settings().database_path != TEST_DATABASE_PATH:
        raise RuntimeError(f"Refusing to reset non-test database: {get_settings().database_path}")
    reset_database()


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_database_status_reports_seeded_tables():
    status = database_status()
    assert Path(status["database_path"]) == TEST_DATABASE_PATH
    assert status["schema_version"] == "20"
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
    assert "work_order_spares" in status["counts"]
    assert status["counts"]["work_order_spares"] >= 4
    assert "work_order_logs" in status["counts"]
    assert "rca_cases" in status["counts"]
    assert status["counts"]["rca_cases"] >= 1
    assert status["counts"]["pm_templates"] >= 3
    assert "pm_plans" in status["counts"]
    assert status["counts"]["users"] == 8
    assert "learning_interactions" in status["counts"]
    assert "learning_examples" in status["counts"]
    assert "assistant_sessions" in status["counts"]
    assert "assistant_messages" in status["counts"]
    assert status["counts"]["learning_model_versions"] >= 1
    assert status["counts"]["learning_prompt_versions"] >= 3
    assert "learning_jobs" in status["counts"]
    assert "learning_artifacts" in status["counts"]
    assert status["counts"]["rag_embedding_profiles"] >= 1


def test_rca_workspace_drafts_closes_and_feeds_learning():
    headers = auth_headers("reliability@plant.local")

    list_response = client.get("/api/rca-cases", headers=headers)
    assert list_response.status_code == 200
    seeded_case = list_response.json()[0]
    assert seeded_case["id"] == "RCA-9001"
    assert seeded_case["hypotheses"]
    assert seeded_case["evidence_timeline"]

    draft_response = client.post(
        "/api/rca-cases/morpheus-draft",
        headers=headers,
        json={
            "case_id": seeded_case["id"],
            "question": "Draft RCA with hypotheses, 5-Why, fishbone, and missing checks.",
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    assert draft["case"]["status"] == "investigating"
    assert draft["case"]["hypotheses"]
    assert draft["case"]["why_chain"]
    assert draft["case"]["fishbone"]
    assert draft["case"]["corrective_actions"]
    assert "morpheus_fishbone_text" in draft["case"]
    assert draft["evidence"]

    close_response = client.patch(
        f"/api/rca-cases/{seeded_case['id']}",
        headers=headers,
        json={
            "status": "closed",
            "probable_cause": draft["case"]["probable_cause"],
            "closure_review": {
                "reviewed_by": "reliability@plant.local",
                "reviewed_at": "2026-06-14T09:00:00+05:30",
                "accepted_for_learning": True,
                "final_root_cause": draft["case"]["probable_cause"],
                "recurrence_prevention": "Procure bearing and verify coupling alignment before restart.",
                "lessons_learned": "Material blockers must be separated from safe RCA evidence capture.",
            },
        },
    )
    assert close_response.status_code == 200, close_response.text
    closed = close_response.json()
    assert closed["status"] == "closed"
    assert closed["closure_review"]["accepted_for_learning"] is True
    assert closed["closed_at"]

    examples_response = client.get("/api/learning/examples?approved_only=true", headers=auth_headers())
    assert examples_response.status_code == 200
    examples = examples_response.json()
    assert any(example["source_type"] == "rca_case" and example["source_id"] == "RCA-9001" for example in examples)


def test_rca_stream_removes_repeated_fishbone_branches(monkeypatch):
    import app.services.rca as rca_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            assert "Limit Fishbone to 4 unique branches" in system_prompt
            yield LLMTextResponse(
                content=(
                    "### Probable Cause\n"
                    "- Inlet guide vane actuator response drift.\n"
                    "### Evidence\n"
                    "- Shift log shows outlet pressure oscillation.\n"
                    "### 5-Why\n"
                    "- Why did outlet pressure oscillate? Feedback lagged command.\n"
                    "- Why did outlet pressure oscillate? Feedback lagged command.\n"
                    "### Fishbone\n"
                    "- Inlet Guide Vane Feedback Lag\n"
                    "- Inlet Guide Vane Feedback Lagging Command\n"
                    "- Inlet Guide Vane Feedback Lagging Command Position Feedback Drift\n"
                    "- Inlet Guide Vane Feedback Lagging Command Position Feedback Drift Feedback Drift Feedback\n"
                    "### Corrective Actions\n"
                    "- Inspect actuator linkage.\n"
                    "### Missing Checks\n"
                    "- Verify position transmitter calibration.\n"
                ),
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(rca_module, "configured_llm_client", lambda: FakeClient())
    response = client.post(
        "/api/rca-cases/morpheus-draft/stream",
        headers=auth_headers("reliability@plant.local"),
        json={
            "case_id": "RCA-9001",
            "question": "Draft RCA with hypotheses, 5-Why, fishbone, and missing checks.",
        },
    )

    assert response.status_code == 200, response.text
    body = response.text
    token_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ") and json.loads(line.removeprefix("data: ")).get("type") == "token"
    ]
    streamed_text = "\n".join(str(event.get("content", "")) for event in token_payloads)
    assert "Inlet Guide Vane Feedback Lag" in body
    assert "Feedback Drift Feedback Drift Feedback" not in body
    assert streamed_text.count("Why did outlet pressure oscillate") == 1


def test_embedding_profile_id_changes_with_model_version_and_dimensions():
    first = embedding_profile_id("deterministic_hash", "maintenance-hash-v1", "1", 64, "Cosine")
    second = embedding_profile_id("deterministic_hash", "maintenance-hash-v2", "2", 64, "Cosine")
    third = embedding_profile_id("deterministic_hash", "maintenance-hash-v1", "1", 128, "Cosine")

    assert first.startswith("emb-")
    assert first != second
    assert first != third


def test_document_chunks_persist_embedding_profile_metadata():
    active_profile = repository.get_active_rag_embedding_profile()
    assert active_profile

    chunks = repository.list_document_chunks()
    assert chunks
    assert {chunk["embedding_profile_id"] for chunk in chunks} == {active_profile["id"]}
    assert {chunk["embedding_model"] for chunk in chunks} == {active_profile["model"]}
    assert {chunk["embedding_dimensions"] for chunk in chunks} == {active_profile["dimensions"]}


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
    assert drive["supervisor"] == "Dhruv"


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


def test_asset_reliability_prediction_stream_removes_repeated_drivers(monkeypatch):
    import app.services.assets as assets_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "Do not repeat the same driver" in system_prompt
            yield LLMTextResponse(
                content=(
                    "### Failure Prediction\n"
                    "- Probability 0.95, critical risk, RUL 4 days.\n"
                    "### Why\n"
                    "- High bearing temperature rolling-baseline anomaly contributes 49%.\n"
                    "- High bearing temperature rolling-baseline anomaly contributes 47%.\n"
                    "- High bearing temperature rolling-baseline anomaly contributes 49%.\n"
                    "- Bearing vibration is above baseline.\n"
                    "### Next Actions\n"
                    "- Inspect bearing housing temperature and vibration.\n"
                ),
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(assets_module, "configured_llm_client", lambda: FakeClient())
    response = client.get("/api/assets/RM-DRIVE-01/reliability/stream", headers=auth_headers())

    assert response.status_code == 200, response.text
    body = response.text
    token_payloads = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ") and json.loads(line.removeprefix("data: ")).get("type") == "token"
    ]
    streamed_text = "\n".join(str(event.get("content", "")) for event in token_payloads)
    assert "High bearing temperature rolling-baseline anomaly" in streamed_text
    assert streamed_text.count("High bearing temperature rolling-baseline anomaly") == 1
    assert "Bearing vibration is above baseline" in streamed_text
    assert '"type": "done"' in body


def test_asset_reliability_prediction_stream_emits_incremental_tokens(monkeypatch):
    import app.services.assets as assets_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            yield LLMTextResponse(
                content="### Failure Prediction\n",
                used_live_provider=True,
                provider="openai",
            )
            yield LLMTextResponse(
                content="- Critical bearing risk is rising.\n",
                used_live_provider=True,
                provider="openai",
            )
            yield LLMTextResponse(
                content="### Next Actions\n- Inspect bearing housing temperature.\n",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(assets_module, "configured_llm_client", lambda: FakeClient())
    response = client.get("/api/assets/RM-DRIVE-01/reliability/stream", headers=auth_headers())

    assert response.status_code == 200, response.text
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    event_types = [event["type"] for event in events]
    assert event_types[:4] == ["meta", "token", "token", "token"]
    assert event_types[-1] == "done"
    assert "".join(event["content"] for event in events if event["type"] == "token").startswith("### Failure Prediction")


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
    assert payload["user"]["display_name"] == "Ragav"
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


def test_supervisor_can_run_morpheus_diagnosis():
    headers = auth_headers("supervisor@plant.local")

    response = client.post("/api/diagnose", json={"equipment_id": "RM-DRIVE-01"}, headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["equipment_id"] == "RM-DRIVE-01"
    assert payload["diagnosis"]


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
    drive_order = next(item for item in payload if item["id"] == "WO-8304")
    assert drive_order["material_blocker_status"] == "blocked"
    assert drive_order["spare_reservations"][0]["spare_name"] == "Drive end spherical roller bearing"
    assert drive_order["spare_reservations"][0]["reorder_requested"] is True


def test_technician_sees_only_assigned_work_orders():
    headers = auth_headers("technician@plant.local")

    response = client.get("/api/work-orders", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert {item["id"] for item in payload} == {"WO-8304"}
    assert {item["assigned_to"] for item in payload} == {"Vinoth"}


def test_admin_and_supervisor_can_list_assignment_technicians():
    admin_response = client.get("/api/users/technicians", headers=auth_headers())
    supervisor_response = client.get("/api/users/technicians", headers=auth_headers("supervisor@plant.local"))
    planner_response = client.get("/api/users/technicians", headers=auth_headers("planner@plant.local"))
    technician_response = client.get("/api/users/technicians", headers=auth_headers("technician@plant.local"))

    assert admin_response.status_code == 200
    assert supervisor_response.status_code == 200
    assert planner_response.status_code == 200
    assert technician_response.status_code == 403
    assert [user["role"] for user in admin_response.json()] == ["maintenance_technician"]
    assert [user["display_name"] for user in supervisor_response.json()] == ["Vinoth"]
    assert [user["display_name"] for user in planner_response.json()] == ["Vinoth"]


def test_work_order_assignment_requires_active_user_or_blank():
    headers = auth_headers()

    unknown_create = client.post(
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
            "assigned_to": "Mani",
            "supervisor": "Blast Furnace Supervisor",
            "due_date": "2026-06-14T09:00:00+05:30",
            "recommended_action": "Stroke actuator and verify position feedback.",
        },
        headers=headers,
    )
    assert unknown_create.status_code == 400
    assert "not an active Maintenance Wizard user" in unknown_create.json()["detail"]

    unknown_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"assigned_to": "Mani"},
        headers=headers,
    )
    assert unknown_response.status_code == 400
    assert "not an active Maintenance Wizard user" in unknown_response.json()["detail"]

    email_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"assigned_to": "technician@plant.local"},
        headers=headers,
    )
    assert email_response.status_code == 200
    assert email_response.json()["assigned_to"] == "Vinoth"

    blank_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"assigned_to": ""},
        headers=headers,
    )
    assert blank_response.status_code == 200
    assert blank_response.json()["assigned_to"] == ""


def test_planner_board_filters_open_scheduled_work_orders():
    headers = auth_headers("planner@plant.local")

    response = client.get("/api/work-orders/planning/board?planning_status=planned", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert {item["id"] for item in payload} == {"WO-8304", "WO-8275"}
    assert all(item["status"] not in {"COMP", "CLOSE"} for item in payload)
    assert all(item["planning_status"] == "planned" for item in payload)


def test_planner_board_page_returns_backend_pagination_metadata():
    headers = auth_headers("planner@plant.local")

    response = client.get("/api/work-orders/planning/board/page?limit=2&offset=0", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert payload["total"] >= len(payload["items"])
    assert len(payload["items"]) <= 2
    assert all(item["status"] not in {"COMP", "CLOSE"} for item in payload["items"])


def test_pm_plan_page_returns_backend_pagination_metadata():
    headers = auth_headers("planner@plant.local")

    response = client.get("/api/pm-plans/page?limit=2&offset=0", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 2
    assert payload["offset"] == 0
    assert payload["total"] >= len(payload["items"])
    assert len(payload["items"]) <= 2


def test_pm_plan_draft_and_conversion_to_planned_work_order():
    headers = auth_headers("planner@plant.local")

    templates_response = client.get("/api/pm-templates?equipment_id=HYD-SYS-04", headers=headers)
    assert templates_response.status_code == 200
    templates = templates_response.json()
    assert any(template["id"] == "PMT-HYD-TEMP-PULSATION" for template in templates)

    draft_response = client.post(
        "/api/pm-plans/morpheus-draft",
        headers=headers,
        json={
            "equipment_id": "HYD-SYS-04",
            "template_id": "PMT-HYD-TEMP-PULSATION",
            "convert_from_prediction": True,
            "requested_focus": "temperature rise and pressure pulsation",
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    plan = draft["plan"]
    assert plan["id"].startswith("PM-")
    assert plan["equipment_id"] == "HYD-SYS-04"
    assert plan["template_id"] == "PMT-HYD-TEMP-PULSATION"
    assert plan["trigger"]["type"] in {"condition", "risk_prediction"}
    assert plan["thresholds"]
    assert plan["tasks"]
    assert plan["smith_steps"]
    assert plan["evidence"]

    list_response = client.get("/api/pm-plans?equipment_id=HYD-SYS-04", headers=headers)
    assert list_response.status_code == 200
    assert any(item["id"] == plan["id"] for item in list_response.json())

    convert_response = client.post(f"/api/pm-plans/{plan['id']}/convert-work-order", headers=headers)
    assert convert_response.status_code == 200, convert_response.text
    work_order = convert_response.json()
    assert work_order["id"].startswith("WO-")
    assert work_order["equipment_id"] == "HYD-SYS-04"
    assert work_order["work_type"] == "PM"
    assert work_order["planning_status"] == "planned"
    assert "PM:" in work_order["title"]
    assert "preventive maintenance plan" in work_order["description"].lower()

    converted = repository.get_pm_plan(plan["id"])
    assert converted["status"] == "converted"
    assert converted["converted_work_order_id"] == work_order["id"]


def test_pm_plan_morpheus_draft_stream_persists_plan():
    headers = auth_headers("planner@plant.local")
    with client.stream(
        "POST",
        "/api/pm-plans/morpheus-draft/stream",
        headers=headers,
        json={"equipment_id": "RM-DRIVE-01", "template_id": "PMT-RM-DRIVE-BEARING", "convert_from_prediction": True},
    ) as response:
        assert response.status_code == 200, response.text
        content = "".join(response.iter_text())

    events = [
        json.loads(line.removeprefix("data: ").strip())
        for line in content.splitlines()
        if line.startswith("data:")
    ]
    assert events[0]["type"] == "meta"
    assert events[-1]["type"] == "done"
    plan = events[-1]["response"]["plan"]
    assert plan["id"].startswith("PM-")
    assert plan["equipment_id"] == "RM-DRIVE-01"
    assert repository.get_pm_plan(plan["id"]) is not None


def test_pm_plan_planning_roles_are_enforced():
    planner_response = client.get("/api/pm-plans", headers=auth_headers("planner@plant.local"))
    reliability_response = client.post(
        "/api/pm-plans/morpheus-draft",
        headers=auth_headers("reliability@plant.local"),
        json={"equipment_id": "RM-DRIVE-01", "convert_from_prediction": True},
    )
    technician_response = client.get("/api/pm-plans", headers=auth_headers("technician@plant.local"))
    operator_response = client.post(
        "/api/pm-plans/morpheus-draft",
        headers=auth_headers("operator@plant.local"),
        json={"equipment_id": "RM-DRIVE-01"},
    )

    assert planner_response.status_code == 200
    assert reliability_response.status_code == 200
    assert technician_response.status_code == 403
    assert operator_response.status_code == 403


def test_planner_can_schedule_and_dispatch_approved_work_order():
    headers = auth_headers("planner@plant.local")

    plan_response = client.patch(
        "/api/work-orders/WO-8311",
        json={
            "status": "APPR",
            "assigned_to": "Vinoth",
            "planning_status": "planned",
            "planned_start": "2026-06-13T08:00:00+05:30",
            "planned_end": "2026-06-13T10:00:00+05:30",
            "outage_window": "Blast furnace blower reduced-load window",
            "material_readiness": "ready",
            "material_blocker_status": "substitute_available",
            "material_blocker_note": "Actuator is on hand; calibration kit can be used if replacement is deferred.",
            "spare_reservations": [
                {
                    "spare_id": "SP-003",
                    "spare_name": "Blower inlet guide vane actuator",
                    "required_qty": 1,
                    "reserved_qty": 1,
                    "available_qty": 1,
                    "reorder_requested": False,
                    "procurement_status": "not_requested",
                    "procurement_lead_time_days": 12,
                    "expected_available_date": None,
                    "substitute_spare_id": None,
                    "substitute_name": "Actuator calibration kit",
                    "blocker_status": "substitute_available",
                    "blocker_note": "Use calibration kit before consuming the actuator.",
                }
            ],
            "dispatch_notes": "Carry actuator calibration kit and compare feedback trend.",
        },
        headers=headers,
    )
    assert plan_response.status_code == 200
    planned = plan_response.json()
    assert planned["status"] == "APPR"
    assert planned["planning_status"] == "planned"
    assert planned["assigned_to"] == "Vinoth"
    assert planned["planned_start"] == "2026-06-13T08:00:00+05:30"
    assert planned["material_readiness"] == "ready"
    assert planned["material_blocker_status"] == "substitute_available"
    assert planned["spare_reservations"][0]["spare_name"] == "Blower inlet guide vane actuator"
    assert planned["spare_reservations"][0]["reserved_qty"] == 1
    assert planned["spare_reservations"][0]["substitute_name"] == "Actuator calibration kit"

    dispatch_response = client.patch(
        "/api/work-orders/WO-8311",
        json={"planning_status": "dispatched"},
        headers=headers,
    )
    assert dispatch_response.status_code == 200
    dispatched = dispatch_response.json()
    assert dispatched["planning_status"] == "dispatched"
    assert dispatched["dispatched_at"]


def test_dispatch_requires_approval_schedule_and_unblocked_materials():
    headers = auth_headers("planner@plant.local")

    waiting_response = client.patch(
        "/api/work-orders/WO-8311",
        json={"planning_status": "dispatched"},
        headers=headers,
    )
    blocked_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"planning_status": "dispatched"},
        headers=headers,
    )

    assert waiting_response.status_code == 400
    assert waiting_response.json()["detail"] == "Approve work order before dispatch"
    assert blocked_response.status_code == 400
    assert blocked_response.json()["detail"] == "Resolve blocked materials before dispatch"

    procurement_response = client.patch(
        "/api/work-orders/WO-8275",
        json={"planning_status": "dispatched", "material_readiness": "pending"},
        headers=headers,
    )
    assert procurement_response.status_code == 400
    assert procurement_response.json()["detail"] == "Resolve material blocker before dispatch"


def test_technician_cannot_modify_planning_fields():
    response = client.patch(
        "/api/work-orders/WO-8304",
        json={"planned_start": "2026-06-12T15:00:00+05:30"},
        headers=auth_headers("technician@plant.local"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Technicians cannot plan or dispatch work orders"


def test_technician_cannot_start_material_blocked_work_order():
    technician_headers = auth_headers("technician@plant.local")

    before = repository.get_work_order("WO-8304")
    assert before["status"] == "WMATL"
    assert before["material_readiness"] == "blocked"

    response = client.patch(
        "/api/work-orders/WO-8304",
        json={"status": "INPRG"},
        headers=technician_headers,
    )

    assert response.status_code == 400
    assert "Resolve material blocker before starting work" in response.json()["detail"]
    assert repository.get_work_order("WO-8304")["status"] == "WMATL"


def test_assigned_technician_can_start_when_material_blocker_is_resolved():
    technician_headers = auth_headers("technician@plant.local")
    admin_headers = auth_headers()
    spare_reservation = repository.get_work_order("WO-8304")["spare_reservations"][0]
    spare_reservation.update(
        {
            "reserved_qty": 1,
            "available_qty": 1,
            "reorder_requested": False,
            "procurement_status": "received",
            "expected_available_date": None,
            "blocker_status": "reserved",
            "blocker_note": "Bearing reserved for execution.",
        }
    )

    material_resolved_response = client.patch(
        "/api/work-orders/WO-8304",
        json={
            "material_readiness": "ready",
            "material_blocker_status": "reserved",
            "material_blocker_note": "Bearing reserved for execution.",
            "spare_reservations": [spare_reservation],
        },
        headers=admin_headers,
    )
    assert material_resolved_response.status_code == 200
    assert material_resolved_response.json()["status"] == "APPR"

    started_response = client.patch(
        "/api/work-orders/WO-8304",
        json={"status": "INPRG"},
        headers=technician_headers,
    )
    assert started_response.status_code == 200
    assert started_response.json()["status"] == "INPRG"


def test_planning_material_ready_clears_waiting_material_status_and_stale_spare_blockers():
    planner_headers = auth_headers("planner@plant.local")

    response = client.patch(
        "/api/work-orders/WO-8304",
        json={
            "material_readiness": "ready",
            "material_blocker_status": "reserved",
            "material_blocker_note": None,
        },
        headers=planner_headers,
    )

    assert response.status_code == 200
    work_order = response.json()
    assert work_order["status"] == "APPR"
    assert work_order["material_readiness"] == "ready"
    assert work_order["material_blocker_status"] == "reserved"
    assert work_order["material_blocker_note"] is None
    assert work_order["spare_reservations"][0]["reserved_qty"] >= work_order["spare_reservations"][0]["required_qty"]
    assert work_order["spare_reservations"][0]["blocker_status"] == "reserved"
    assert work_order["spare_reservations"][0]["blocker_note"] is None


def test_supervisor_can_resolve_material_and_move_waiting_material_order_to_in_progress():
    supervisor_headers = auth_headers("supervisor@plant.local")

    response = client.patch(
        "/api/work-orders/WO-8304",
        json={
            "status": "INPRG",
            "material_readiness": "ready",
            "material_blocker_status": "reserved",
            "material_blocker_note": None,
        },
        headers=supervisor_headers,
    )

    assert response.status_code == 200
    work_order = response.json()
    assert work_order["status"] == "INPRG"
    assert work_order["material_readiness"] == "ready"
    assert work_order["spare_reservations"][0]["blocker_status"] == "reserved"


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
    assert material_response.json()["detail"] == "Resolve material blocker before approval"


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
            "assigned_to": "Guna",
            "supervisor": "Blast Furnace Supervisor",
            "due_date": "2026-06-14T09:00:00+05:30",
            "planning_status": "planned",
            "planned_start": "2026-06-14T07:00:00+05:30",
            "planned_end": "2026-06-14T09:00:00+05:30",
            "outage_window": "Blast furnace morning inspection window",
            "material_readiness": "ready",
            "dispatch_notes": "Coordinate with operations before actuator stroke test.",
            "recommended_action": "Stroke actuator and verify position feedback.",
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    work_order = create_response.json()
    assert work_order["id"].startswith("WO-")
    assert work_order["status"] == "WAPPR"
    assert work_order["planning_status"] == "planned"
    assert work_order["planned_start"] == "2026-06-14T07:00:00+05:30"
    assert work_order["material_readiness"] == "ready"

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
        json={"author": "Guna", "entry_type": "observation", "content": "Actuator linkage has minor play."},
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
            "assigned_to": "Guna",
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
    assert payload["suggested_problem_code"] == "BRGVIB"
    assert payload["live_directions"] == []
    assert payload["recommendations"] == []
    assert "Sorry, Trinity could not get a live LLM response" in payload["completion_summary"]
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
    events = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    evidence_calls = [
        event["tool_call"]
        for event in events
        if event["type"] == "tool_call" and event["tool_call"]["name"] == "load_evidence_context"
    ]
    evidence_results = [
        event["tool_result"]
        for event in events
        if event["type"] == "tool_result" and event["tool_result"]["name"] == "load_evidence_context"
    ]
    assert evidence_calls
    assert evidence_calls[0]["assistant_id"] == "trinity"
    assert evidence_results
    assert evidence_results[0]["artifact_type"] == "retrieval_evidence"
    assert "Trinity" in body
    assert '"provider": "openai"' in body
    assert '"used_live_provider": true' in body
    token_text = "".join(event.get("content", "") for event in events if event["type"] == "token")
    assert "LWTQCONNECT" not in token_text

    forbidden_response = client.post(
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "Connections are loose."},
        headers=auth_headers("supervisor@plant.local"),
    )
    assert forbidden_response.status_code == 403


def test_technician_assistant_stream_uses_stream_llm_timeout(monkeypatch):
    import app.services.work_order_assistant as assistant_module
    from app.services.llm import LLMTextResponse

    captured = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            captured["timeout_seconds"] = timeout_seconds
            yield LLMTextResponse(content="Trinity bounded guidance.", used_live_provider=True, provider="openai")

    monkeypatch.setattr(assistant_module, "configured_llm_client", lambda: FakeClient())
    with client.stream(
        "POST",
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "Connections 3 and 5 were loose."},
        headers=auth_headers("technician@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert captured["timeout_seconds"] == 60.0
    assert "Technician name: Vinoth" in captured["prompt"]
    assert "Address the technician by this name; do not address them by role." in captured["prompt"]
    assert "address them by name and not by role" in captured["system_prompt"]
    assert "Trinity bounded guidance" in body


def test_technician_assistant_stream_includes_persisted_session_history(monkeypatch):
    import app.services.work_order_assistant as assistant_module
    from app.services.llm import LLMTextResponse

    session_id = "TEST-TRINITY-TECH-HISTORY"
    repository.upsert_assistant_session(
        {
            "id": session_id,
            "assistant_id": "trinity",
            "user_id": "USER-TECH",
            "user_role": "maintenance_technician",
            "screen": "work_execution_technician",
            "status": "active",
            "metadata": {},
        }
    )
    repository.save_assistant_message(
        {
            "session_id": session_id,
            "assistant_id": "trinity",
            "role": "user",
            "content": "The previous observation was loose coupling bolts on RM-DRIVE-01.",
        }
    )
    repository.save_assistant_message(
        {
            "session_id": session_id,
            "assistant_id": "trinity",
            "role": "assistant",
            "content": "Trinity recommended checking coupling alignment before completion.",
        }
    )
    captured: dict[str, str] = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            yield LLMTextResponse(content="Vinoth, continue from the coupling alignment check.", used_live_provider=True, provider="openai")

    monkeypatch.setattr(assistant_module, "configured_llm_client", lambda: FakeClient())
    with client.stream(
        "POST",
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "what should I do next", "session_id": session_id},
        headers=auth_headers("technician@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Conversation continuity:" in captured["prompt"]
    assert "loose coupling bolts on RM-DRIVE-01" in captured["prompt"]
    assert "checking coupling alignment" in captured["prompt"]
    assert "continue from the coupling alignment check" in body


def test_technician_assistant_uses_apology_when_material_question_has_no_llm():
    headers = auth_headers("technician@plant.local")

    with client.stream(
        "POST",
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "when is Drive end bearing expected to be available"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Sorry, Trinity could not get a live LLM response" in body
    assert "Drive end spherical roller bearing" not in body
    assert "Safety:" not in body


def test_technician_assistant_uses_apology_for_off_topic_query_without_llm():
    with client.stream(
        "POST",
        "/api/work-orders/technician-assist/stream",
        json={"work_order_id": "WO-8304", "observation": "what is the time now"},
        headers=auth_headers("technician@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Sorry, Trinity could not get a live LLM response" in body
    assert "Verify the current load" not in body
    assert "Live LLM" not in body


def test_supervisor_assistant_reviews_follow_up_queue_and_drafts_order():
    headers = auth_headers("supervisor@plant.local")

    response = client.post(
        "/api/work-orders/supervisor-assist",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up", "question": "What needs follow-up?"},
        headers=headers,
    )

    assert response.status_code == 200
    payload = response.json()
    assert "Sorry, Trinity could not get a live LLM response" in payload["summary"]
    assert payload["follow_up_actions"] == []
    assert "WO-8297" in payload["referenced_work_orders"]
    assert payload["draft_work_order"] is None

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
    assert "Trinity" in body
    assert "WO-8297" in body

    forbidden_response = client.post(
        "/api/work-orders/supervisor-assist/stream",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up"},
        headers=auth_headers("technician@plant.local"),
    )
    assert forbidden_response.status_code == 403


def test_supervisor_assistant_stream_answers_waiting_approval_queue(monkeypatch):
    import app.services.work_order_assistant as assistant_module
    from app.services.llm import LLMTextResponse

    captured = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            yield LLMTextResponse(
                content="Waiting for approval: WO-8311 needs supervisor approval before execution.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(assistant_module, "configured_llm_client", lambda: FakeClient())
    headers = auth_headers("supervisor@plant.local")
    with client.stream(
        "POST",
        "/api/work-orders/supervisor-assist/stream",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up", "question": "what are the work orders pending for my approval"},
        headers=headers,
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Waiting for approval" in body
    assert "WO-8311" in body
    assert "WO-8297" not in body
    assert "Queue focus: waiting_approval" in captured["prompt"]
    assert "Supervisor name: Dhruv" in captured["prompt"]
    assert "Address the supervisor by this name; do not address them by role." in captured["prompt"]


def test_supervisor_assistant_uses_apology_for_off_topic_query_without_llm():
    with client.stream(
        "POST",
        "/api/work-orders/supervisor-assist/stream",
        json={"work_order_id": "WO-8297", "question": "what is the time now"},
        headers=auth_headers("supervisor@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Sorry, Trinity could not get a live LLM response" in body
    assert "supervisor review only" not in body


def test_supervisor_assistant_stream_uses_stream_llm_timeout(monkeypatch):
    import app.services.work_order_assistant as assistant_module
    from app.services.llm import LLMTextResponse

    captured = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            captured["timeout_seconds"] = timeout_seconds
            yield LLMTextResponse(content="Trinity supervisor bounded review.", used_live_provider=True, provider="openai")

    monkeypatch.setattr(assistant_module, "configured_llm_client", lambda: FakeClient())
    with client.stream(
        "POST",
        "/api/work-orders/supervisor-assist/stream",
        json={"work_order_id": "WO-8297", "queue_name": "follow_up", "question": "What needs follow-up?"},
        headers=auth_headers("supervisor@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert captured["timeout_seconds"] == 60.0
    assert "Supervisor name: Dhruv" in captured["prompt"]
    assert "address them by name and not by role" in captured["system_prompt"]
    assert "Trinity supervisor bounded review" in body


def test_supervisor_assistant_stream_includes_persisted_session_history(monkeypatch):
    import app.services.work_order_assistant as assistant_module
    from app.services.llm import LLMTextResponse

    session_id = "TEST-TRINITY-SUP-HISTORY"
    repository.upsert_assistant_session(
        {
            "id": session_id,
            "assistant_id": "trinity",
            "user_id": "USER-SUPERVISOR",
            "user_role": "maintenance_supervisor",
            "screen": "work_execution_supervisor",
            "status": "active",
            "metadata": {},
        }
    )
    repository.save_assistant_message(
        {
            "session_id": session_id,
            "assistant_id": "trinity",
            "role": "user",
            "content": "Earlier we discussed WO-8311 approval before handoff.",
        }
    )
    repository.save_assistant_message(
        {
            "session_id": session_id,
            "assistant_id": "trinity",
            "role": "assistant",
            "content": "Trinity said WO-8311 needs approval or scope send-back.",
        }
    )
    captured: dict[str, str] = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            yield LLMTextResponse(content="Dhruv, continue with WO-8311 approval before handoff.", used_live_provider=True, provider="openai")

    monkeypatch.setattr(assistant_module, "configured_llm_client", lambda: FakeClient())
    with client.stream(
        "POST",
        "/api/work-orders/supervisor-assist/stream",
        json={"queue_name": "waiting_approval", "question": "what was pending from earlier", "session_id": session_id},
        headers=auth_headers("supervisor@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Conversation continuity:" in captured["prompt"]
    assert "WO-8311 approval before handoff" in captured["prompt"]
    assert "approval or scope send-back" in captured["prompt"]
    assert "continue with WO-8311 approval" in body


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
    assert any(item["equipment_id"] == equipment_id for item in diagnosis["evidence"])

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


def test_neo_chat_does_not_use_generic_table_resolver_for_read_roles():
    response = client.post(
        "/api/neo/chat",
        json={"message": "Show work orders needing follow-up"},
        headers=auth_headers("operator@plant.local"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert "Neo" in payload["answer"] or payload["answer"]
    assert payload["table"] is None
    assert payload["provider"] == "openai"
    assert "Grounded app response" not in payload["answer"]
    assert "Rows:" not in payload["answer"]


def test_neo_chat_stream_returns_standardized_events_for_asset_decision():
    with client.stream(
        "POST",
        "/api/neo/chat/stream",
        json={
            "message": "since RM-DRIVE-01 is most critical, what should I do now as an admin",
            "history": [
                {
                    "role": "assistant",
                    "content": "Ragav, these are the lowest-health equipment items right now. CRITICAL: RM-DRIVE-01.",
                }
            ],
        },
        headers=auth_headers("admin@plant.local"),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert "data:" in body
    events = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    session_events = [event for event in events if event["type"] == "session"]
    assert session_events
    session_id = session_events[0]["session_id"]
    assert session_id
    assert session_events[0]["runtime"] == "legacy"
    tool_names = {tool["name"] for tool in session_events[0]["tools"]}
    assert "load_asset_context" in tool_names
    assert "load_plant_priority_context" in tool_names
    assert any(event["type"] == "meta" and event["runtime"] == "legacy" for event in events)
    tool_calls = [event["tool_call"] for event in events if event["type"] == "tool_call"]
    tool_results = [event["tool_result"] for event in events if event["type"] == "tool_result"]
    assert tool_calls
    assert tool_results
    assert tool_calls[0]["name"] == "asset_decision_guidance"
    assert tool_calls[0]["assistant_id"] == "neo"
    assert tool_calls[0]["arguments"]["target_id"] == "RM-DRIVE-01"
    assert tool_results[0]["name"] == "asset_decision_guidance"
    assert tool_results[0]["artifact_type"] == "assistant_action"
    assert tool_results[0]["content"]["action"]["type"] == "asset_decision_guidance"
    final_events = [event for event in events if event["type"] == "final"]
    assert final_events
    assert final_events[0]["response"]["session_id"] == session_id
    assert final_events[0]["response"]["assistant_id"] == "neo"
    assert final_events[0]["response"]["runtime"] == "legacy"
    assert '"type": "done"' in body
    assert "RM-DRIVE-01" in body
    assert "asset_decision_guidance" in body
    assert '"table": null' in body
    assert '"provider": "openai"' in body
    assert "Grounded app response" not in body
    assert "Rows:" not in body
    messages = repository.list_assistant_messages(session_id)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["final_response"]["assistant_id"] == "neo"
    assert messages[-1]["tool_calls"][0]["name"] == "asset_decision_guidance"
    assert messages[-1]["tool_results"][0]["artifact_type"] == "assistant_action"


def test_neo_chat_stream_uses_interactive_llm_timeout(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    captured = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["timeout_seconds"] = timeout_seconds
            yield LLMTextResponse(content="Neo dashboard bounded answer.", used_live_provider=True, provider="openai")

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    with client.stream(
        "POST",
        "/api/neo/chat/stream",
        json={"message": "how to inspect Blast Furnace Combustion Air Blower"},
        headers=auth_headers(),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert captured["timeout_seconds"] == 15.0
    assert "Neo dashboard bounded answer" in body


def test_neo_chat_stream_filters_prompt_label_leak_for_asset_decision(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    captured = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            yield LLMTextResponse(
                content=(
                    "Grounded app response:\n\nNone\n\nAnswer requirements:\n\n"
                    "Rows:\n{'Asset': 'RM-DRIVE-01'}"
                ),
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    with client.stream(
        "POST",
        "/api/neo/chat/stream",
        json={
            "message": "since RM-DRIVE-01 is most critical, what should I do now as an admin",
            "history": [
                {
                    "role": "assistant",
                    "content": "CRITICAL: RM-DRIVE-01 Hot Strip Mill Main Drive Motor.",
                }
            ],
        },
        headers=auth_headers("admin@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    assert "Grounded app response" not in captured["prompt"]
    assert "Rows:" not in captured["prompt"]
    assert "Grounded app response" not in body
    assert "Answer requirements" not in body
    assert "RM-DRIVE-01" in body
    assert "asset_decision_guidance" in body


def test_assistant_runtime_stream_prefers_pydantic_ai_when_configured(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime
    from app.services.llm import LLMTextResponse, MockLLMClient

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()
    monkeypatch.setattr(runtime, "pydantic_ai_available", lambda: True)
    monkeypatch.setattr(
        runtime,
        "_run_pydantic_ai_output",
        lambda **kwargs: runtime.AssistantRuntimeOutput(
            markdown="Ragav, Pydantic AI produced a validated assistant answer."
        ),
    )

    events = list(
        runtime.stream_assistant_markdown(
            assistant_id="morpheus",
            prompt="Which assets are at risk?",
            system_prompt="Answer as Neo.",
            fallback_client=MockLLMClient(provider="mock"),
            fallback_factory=lambda provider, reason: LLMTextResponse(
                content=f"fallback: {reason}",
                used_live_provider=False,
                provider=provider,
            ),
            max_tokens=200,
        )
    )

    get_settings.cache_clear()
    assert "".join(event.content for event in events) == "Ragav, Pydantic AI produced a validated assistant answer."
    assert all(event.provider == "pydantic_ai" for event in events)
    assert all(event.used_live_provider for event in events)


def test_pydantic_ai_runtime_uses_configured_openai_compatible_provider(monkeypatch):
    import app.services.assistant_runtime as runtime

    captured: dict[str, object] = {}

    class FakeProvider:
        def __init__(self, base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    class FakeModel:
        def __init__(self, model_name, *, provider):
            captured["model_name"] = model_name
            captured["provider"] = provider

    monkeypatch.setitem(sys.modules, "pydantic_ai.models.openai", SimpleNamespace(OpenAIChatModel=FakeModel))
    monkeypatch.setitem(sys.modules, "pydantic_ai.providers.openai", SimpleNamespace(OpenAIProvider=FakeProvider))

    model = runtime._pydantic_ai_model(
        SimpleNamespace(
            llm_provider="openai",
            openai_model="qwen2.5-7b-instruct",
            openai_base_url="http://127.0.0.1:8080/v1",
            openai_api_key="llama-cpp-local",
            ollama_model="unused",
        )
    )

    assert isinstance(model, FakeModel)
    assert captured["model_name"] == "qwen2.5-7b-instruct"
    assert captured["base_url"] == "http://127.0.0.1:8080/v1"
    assert captured["api_key"] == "llama-cpp-local"
    assert isinstance(captured["provider"], FakeProvider)


def test_assistant_tools_load_grounded_records():
    from app.services.assistant_tools import (
        add_work_order_log,
        assign_work_order,
        assistant_tool_functions,
        assistant_tool_specs,
        create_work_order,
        load_asset_context,
        load_evidence_context,
        load_plant_priority_context,
        load_work_order_context,
        update_work_order_material_ready,
        update_work_order_status,
    )

    neo_tools = {tool.name for tool in assistant_tool_specs("neo")}
    trinity_tools = {tool.name for tool in assistant_tool_specs("trinity")}
    assert "load_plant_priority_context" in neo_tools
    assert "create_work_order" in neo_tools
    assert "load_plant_priority_context" not in trinity_tools
    assert {"update_work_order_status", "assign_work_order", "create_work_order", "add_work_order_log"} <= trinity_tools

    repository.save_pm_plan(
        {
            "equipment_id": "HYD-SYS-04",
            "title": "HYD-SYS-04 hydraulic oil temperature PM",
            "status": "active",
            "cadence_days": 30,
            "next_due_date": "2026-06-25T08:00:00+05:30",
            "trigger": {"description": "Elevated hydraulic oil temperature"},
            "thresholds": [{"signal": "hydraulic_oil_temperature", "limit": 75}],
            "tasks": [{"description": "Inspect cooler fouling and return-line temperature"}],
            "source": "morpheus",
            "generated_by": "morpheus",
            "used_live_provider": True,
            "provider": "openai",
        }
    )

    asset_context = load_asset_context("RM-DRIVE-01")
    assert asset_context["status"] == "completed"
    assert asset_context["equipment"]["id"] == "RM-DRIVE-01"
    assert asset_context["work_orders"]

    hydraulic_context = load_asset_context("HYD-SYS-04")
    assert hydraulic_context["status"] == "completed"
    assert any(plan["title"] == "HYD-SYS-04 hydraulic oil temperature PM" for plan in hydraulic_context["pm_plans"])

    work_order_context = load_work_order_context("WO-8304")
    assert work_order_context["status"] == "completed"
    assert work_order_context["work_order"]["id"] == "WO-8304"
    assert work_order_context["equipment"]["id"] == "RM-DRIVE-01"

    evidence_context = load_evidence_context("bearing vibration", equipment_id="RM-DRIVE-01", limit=2)
    assert evidence_context["status"] == "completed"
    assert len(evidence_context["evidence"]) <= 2

    plant_context = load_plant_priority_context()
    assert plant_context["status"] == "completed"
    assert plant_context["assets_at_risk"]

    neo_functions = assistant_tool_functions("neo", current_user=SimpleNamespace(role="admin", display_name="Ragav"))
    trinity_functions = assistant_tool_functions("trinity", current_user=SimpleNamespace(role="maintenance_technician", display_name="Vinoth"))
    assert "assign_work_order" in neo_functions
    assert "create_work_order" in neo_functions
    assert "update_work_order_status" in neo_functions
    assert "assign_work_order" in trinity_functions
    assert "update_work_order_status" in trinity_functions
    assert "add_work_order_log" in trinity_functions

    created = create_work_order("RM-DRIVE-01", assignee="Vinoth", current_user=SimpleNamespace(role="admin", display_name="Ragav"))
    assert created["status"] == "completed"
    assert created["work_order"]["equipment_id"] == "RM-DRIVE-01"
    assert created["work_order"]["assigned_to"] == "Vinoth"

    unassigned = create_work_order("HYD-SYS-04", current_user=SimpleNamespace(role="admin", display_name="Ragav"))
    assert unassigned["status"] == "completed"
    assert unassigned["work_order"]["equipment_id"] == "HYD-SYS-04"
    assert unassigned["work_order"]["assigned_to"] == ""
    assert "assignment is blank" in unassigned["detail"]

    assigned = assign_work_order("WO-8304", "Vinoth", current_user=SimpleNamespace(role="admin", display_name="Ragav"))
    assert assigned["status"] == "completed"
    assert assigned["work_order"]["assigned_to"] == "Vinoth"

    email_assigned = assign_work_order(
        "WO-8304",
        "technician@plant.local",
        current_user=SimpleNamespace(role="admin", display_name="Ragav"),
    )
    assert email_assigned["status"] == "completed"
    assert email_assigned["work_order"]["assigned_to"] == "Vinoth"

    unknown_assignment = assign_work_order(
        "WO-8304",
        "Mani",
        current_user=SimpleNamespace(role="admin", display_name="Ragav"),
    )
    assert unknown_assignment["status"] == "blocked"
    assert "not an active Maintenance Wizard user" in unknown_assignment["detail"]
    assert any(user["display_name"] == "Vinoth" for user in unknown_assignment["valid_assignees"])

    unknown_create = create_work_order(
        "HYD-SYS-04",
        assignee="Mani",
        current_user=SimpleNamespace(role="admin", display_name="Ragav"),
    )
    assert unknown_create["status"] == "blocked"
    assert "not an active Maintenance Wizard user" in unknown_create["detail"]

    blocked_assignment = assign_work_order(
        "WO-8304",
        "Lokesh",
        current_user=SimpleNamespace(role="maintenance_technician", display_name="Vinoth"),
    )
    assert blocked_assignment["status"] == "not_allowed"

    approved = update_work_order_status("WO-8311", "APPR", current_user=SimpleNamespace(role="maintenance_supervisor", display_name="Dhruv"))
    assert approved["status"] == "completed"
    assert approved["to_status"] == "APPR"

    blocked_start = update_work_order_status("WO-8304", "INPRG", current_user=SimpleNamespace(role="maintenance_technician", display_name="Vinoth"))
    assert blocked_start["status"] == "not_allowed"
    assert "bearing" in blocked_start["detail"].lower() or "material" in blocked_start["detail"].lower()

    material_ready = update_work_order_material_ready("WO-8304", current_user=SimpleNamespace(role="planner", display_name="Priya"))
    assert material_ready["status"] == "completed"
    assert material_ready["work_order"]["material_readiness"] == "ready"

    log_result = add_work_order_log(
        "WO-8304",
        "Checked bearing housing after material readiness update.",
        current_user=SimpleNamespace(role="maintenance_technician", display_name="Vinoth"),
    )
    assert log_result["status"] == "completed"
    assert log_result["work_order"]["logs"][-1]["content"] == "Checked bearing housing after material readiness update."

    blocked_log = add_work_order_log(
        "WO-8304",
        "Trying to update another technician's work.",
        current_user=SimpleNamespace(role="maintenance_technician", display_name="Lokesh"),
    )
    assert blocked_log["status"] == "not_allowed"


def test_neo_creates_and_assigns_work_order_from_session_task_context(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeLiveClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            return LLMTextResponse(
                content="Created work order WO-9999 for CC-PUMP-03 and assigned it to Kumar.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeLiveClient())

    response = client.post(
        "/api/neo/chat",
        json={
            "message": "Create a work order and assign this task to Vinoth",
            "history": [
                {
                    "role": "assistant",
                    "content": (
                        "The next step for RM-DRIVE-01 is to inspect bearing housing temperature, "
                        "lubrication condition, coupling alignment, foundation bolts, and load changes."
                    ),
                }
            ],
        },
        headers=auth_headers(),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["action"]["type"] == "create_work_order"
    assert body["action"]["status"] == "completed"
    assert "Vinoth" in body["answer"]
    assert "RM-DRIVE-01" in body["answer"]
    assert "CC-PUMP-03" not in body["answer"]
    assert "Kumar" not in body["answer"]
    created = repository.get_work_order(body["action"]["target_id"])
    assert created is not None
    assert created["equipment_id"] == "RM-DRIVE-01"
    assert created["assigned_to"] == "Vinoth"
    assert created["status"] == "WAPPR"


def test_pydantic_ai_runtime_registers_assistant_tools(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime

    captured: dict[str, object] = {}

    class FakeResult:
        output = runtime.AssistantRuntimeOutput(markdown="Ragav, registered tools are available.")

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.registered_tools: list[str] = []
            captured["agent_kwargs"] = kwargs

        def tool_plain(self, func):
            self.registered_tools.append(func.__name__)
            return func

        def run_sync(self, prompt, message_history=None, model_settings=None):
            captured["registered_tools"] = self.registered_tools
            captured["message_history"] = message_history
            captured["model_settings"] = model_settings
            return FakeResult()

    monkeypatch.setitem(
        sys.modules,
        "pydantic_ai",
        SimpleNamespace(Agent=FakeAgent, PromptedOutput=lambda output_type, **kwargs: output_type),
    )
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()

    markdown = runtime._run_pydantic_ai_markdown(
        assistant_id="neo",
        prompt="Which plant risks matter now?",
        system_prompt="Answer as Neo.",
        max_tokens=200,
    )

    get_settings.cache_clear()
    assert markdown == "Ragav, registered tools are available."
    assert "load_asset_context" in captured["registered_tools"]
    assert "load_work_order_context" in captured["registered_tools"]
    assert "load_evidence_context" in captured["registered_tools"]
    assert "load_plant_priority_context" in captured["registered_tools"]
    assert "assign_work_order" in captured["registered_tools"]
    assert "create_work_order" in captured["registered_tools"]
    assert "update_work_order_status" in captured["registered_tools"]
    assert "update_work_order_material_ready" in captured["registered_tools"]
    assert captured["message_history"] == []
    assert captured["model_settings"]["max_tokens"] == 200


def test_pydantic_ai_runtime_passes_native_message_history(monkeypatch):
    from app.core.config import get_settings
    from app.models.schemas import ChatMessage
    import app.services.assistant_runtime as runtime

    captured: dict[str, object] = {}

    class FakeUserPromptPart:
        def __init__(self, content):
            self.content = content

    class FakeTextPart:
        def __init__(self, content):
            self.content = content

    class FakeModelRequest:
        def __init__(self, parts):
            self.parts = parts

    class FakeModelResponse:
        def __init__(self, parts):
            self.parts = parts

    class FakeResult:
        output = runtime.AssistantRuntimeOutput(markdown="Ragav, continuing from the previous RM-DRIVE-01 task.")

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            pass

        def tool_plain(self, func):
            return func

        def run_sync(self, prompt, message_history=None, model_settings=None):
            captured["prompt"] = prompt
            captured["message_history"] = message_history
            captured["model_settings"] = model_settings
            return FakeResult()

    monkeypatch.setitem(
        sys.modules,
        "pydantic_ai",
        SimpleNamespace(Agent=FakeAgent, PromptedOutput=lambda output_type, **kwargs: output_type),
    )
    monkeypatch.setitem(
        sys.modules,
        "pydantic_ai.messages",
        SimpleNamespace(
            ModelRequest=FakeModelRequest,
            ModelResponse=FakeModelResponse,
            TextPart=FakeTextPart,
            UserPromptPart=FakeUserPromptPart,
        ),
    )
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()

    markdown = runtime._run_pydantic_ai_markdown(
        assistant_id="neo",
        prompt="Can I assign this task to a technician?",
        system_prompt="Answer as Neo.",
        max_tokens=200,
        history=[
            ChatMessage(role="user", content="What should I do now for RM-DRIVE-01?"),
            ChatMessage(role="assistant", content="Inspect bearing housing temperature and coupling alignment."),
            ChatMessage(
                role="assistant",
                content="Sorry, Neo could not get a live LLM response right now. Please retry after confirming the LLM service is responding.",
            ),
        ],
    )

    get_settings.cache_clear()
    assert markdown == "Ragav, continuing from the previous RM-DRIVE-01 task."
    message_history = captured["message_history"]
    assert len(message_history) == 2
    assert isinstance(message_history[0], FakeModelRequest)
    assert message_history[0].parts[0].content == "What should I do now for RM-DRIVE-01?"
    assert isinstance(message_history[1], FakeModelResponse)
    assert message_history[1].parts[0].content == "Inspect bearing housing temperature and coupling alignment."
    assert captured["prompt"] == "Can I assign this task to a technician?"


def test_standardized_stream_captures_pydantic_ai_tool_events(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime
    from app.models.schemas import UserPublic
    from app.services.llm import LLMTextResponse, MockLLMClient

    class FakeResult:
        output = runtime.AssistantRuntimeOutput(markdown="Ragav, RM-DRIVE-01 context was loaded.")

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.registered_tools: dict[str, object] = {}

        def tool_plain(self, func):
            self.registered_tools[func.__name__] = func
            return func

        def run_sync(self, prompt, message_history=None, model_settings=None):
            self.registered_tools["load_asset_context"](equipment_id="RM-DRIVE-01")
            return FakeResult()

    monkeypatch.setitem(
        sys.modules,
        "pydantic_ai",
        SimpleNamespace(Agent=FakeAgent, PromptedOutput=lambda output_type, **kwargs: output_type),
    )
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()
    user = UserPublic.model_validate(repository.get_user_by_email("admin@plant.local"))

    def legacy_events(session_id, history):
        yield {"type": "meta", "provider": "pydantic_ai", "used_live_provider": True}
        markdown = ""
        for chunk in runtime.stream_assistant_markdown(
            assistant_id="morpheus",
            prompt="Load RM-DRIVE-01 context.",
            system_prompt="Answer as Neo.",
            fallback_client=MockLLMClient(provider="mock"),
            fallback_factory=lambda provider, reason: LLMTextResponse(
                content=f"fallback: {reason}",
                used_live_provider=False,
                provider=provider,
            ),
            max_tokens=200,
            current_user=user,
        ):
            markdown += chunk.content
            yield {"type": "token", "content": chunk.content}
        yield {
            "type": "done",
            "response": {
                "answer": markdown,
                "provider": "pydantic_ai",
                "used_live_provider": True,
            },
        }

    events = list(
        runtime.standardized_assistant_stream(
            assistant_id="neo",
            screen="command_center",
            current_user=user,
            session_id="TEST-PYDANTIC-TOOL-CAPTURE",
            user_content="Load RM-DRIVE-01 context.",
            legacy_events=legacy_events,
        )
    )

    get_settings.cache_clear()
    assert any(event["type"] == "tool_call" and event["tool_call"]["name"] == "load_asset_context" for event in events)
    assert any(event["type"] == "tool_result" and event["tool_result"]["name"] == "load_asset_context" for event in events)
    saved_messages = repository.list_assistant_messages(session_id="TEST-PYDANTIC-TOOL-CAPTURE")
    assistant_message = next(message for message in saved_messages if message["role"] == "assistant")
    assert assistant_message["tool_calls"][0]["name"] == "load_asset_context"
    assert assistant_message["tool_results"][0]["content"]["equipment"]["id"] == "RM-DRIVE-01"


def test_standardized_stream_rejects_cross_user_session_history():
    import app.services.assistant_runtime as runtime
    from app.models.schemas import UserPublic

    admin = UserPublic.model_validate(repository.get_user_by_email("admin@plant.local"))
    operator = UserPublic.model_validate(repository.get_user_by_email("operator@plant.local"))
    original_session = repository.upsert_assistant_session(
        {
            "id": "TEST-CROSS-USER-SESSION",
            "assistant_id": "neo",
            "user_id": admin.id,
            "user_role": admin.role,
            "screen": "command_center",
        }
    )
    repository.save_assistant_message(
        {
            "session_id": original_session["id"],
            "assistant_id": "neo",
            "role": "user",
            "content": "Sensitive admin context from prior session.",
        }
    )
    captured_history: list[object] = []

    def legacy_events(session_id, history):
        captured_history.extend(history)
        yield {"type": "meta", "provider": "openai", "used_live_provider": True}
        yield {
            "type": "done",
            "response": {
                "answer": "Operator receives a fresh assistant session.",
                "provider": "openai",
                "used_live_provider": True,
            },
        }

    events = list(
        runtime.standardized_assistant_stream(
            assistant_id="neo",
            screen="command_center",
            current_user=operator,
            session_id=original_session["id"],
            user_content="Start a new operator chat.",
            legacy_events=legacy_events,
        )
    )

    session_event = next(event for event in events if event["type"] == "session")
    assert session_event["session_id"] != original_session["id"]
    assert captured_history == []
    assert repository.get_assistant_session(original_session["id"])["user_id"] == admin.id
    assert repository.get_assistant_session(session_event["session_id"])["user_id"] == operator.id


def test_pydantic_ai_runtime_registers_trinity_action_tools(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime
    from app.models.schemas import UserPublic

    captured: dict[str, object] = {}

    class FakeResult:
        output = runtime.AssistantRuntimeOutput(markdown="Vinoth, Trinity action tools are available.")

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            self.registered_tools: list[str] = []

        def tool_plain(self, func):
            self.registered_tools.append(func.__name__)
            return func

        def run_sync(self, prompt, message_history=None, model_settings=None):
            captured["registered_tools"] = self.registered_tools
            captured["message_history"] = message_history
            return FakeResult()

    monkeypatch.setitem(
        sys.modules,
        "pydantic_ai",
        SimpleNamespace(Agent=FakeAgent, PromptedOutput=lambda output_type, **kwargs: output_type),
    )
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()
    user = UserPublic.model_validate(repository.get_user_by_email("technician@plant.local"))

    markdown = runtime._run_pydantic_ai_markdown(
        assistant_id="trinity",
        prompt="Start my assigned work order.",
        system_prompt="Answer as Trinity.",
        max_tokens=200,
        current_user=user,
    )

    get_settings.cache_clear()
    assert markdown == "Vinoth, Trinity action tools are available."
    assert "load_work_order_context" in captured["registered_tools"]
    assert "update_work_order_status" in captured["registered_tools"]
    assert "assign_work_order" in captured["registered_tools"]
    assert "create_work_order" in captured["registered_tools"]
    assert "add_work_order_log" in captured["registered_tools"]
    assert captured["message_history"] == []


def test_assistant_runtime_stream_returns_structured_failure_when_pydantic_ai_unavailable(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime
    from app.services.llm import LLMTextResponse, MockLLMClient

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()
    monkeypatch.setattr(
        runtime,
        "_run_pydantic_ai_output",
        lambda **kwargs: (_ for _ in ()).throw(runtime.AssistantRuntimeFailure("not installed")),
    )

    events = list(
        runtime.stream_assistant_markdown(
            assistant_id="morpheus",
            prompt="Which assets are at risk?",
            system_prompt="Answer as Neo.",
            fallback_client=MockLLMClient(provider="mock"),
            fallback_factory=lambda provider, reason: LLMTextResponse(
                content=f"fallback: {reason}",
                used_live_provider=False,
                provider=provider,
            ),
            max_tokens=200,
        )
    )

    get_settings.cache_clear()
    assert len(events) == 1
    assert events[0].provider == "pydantic_ai"
    assert events[0].used_live_provider is False
    assert events[0].runtime == "pydantic_ai"
    assert events[0].runtime_fallback is True
    assert events[0].runtime_fallback_reason == "not installed"
    assert events[0].content == ""


def test_neo_stream_bypasses_pydantic_validation_and_caps_live_text_tokens(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()
    monkeypatch.setattr(
        runtime,
        "_run_pydantic_ai_output",
        lambda **kwargs: (_ for _ in ()).throw(runtime.AssistantRuntimeFailure("pydantic runtime unavailable")),
    )
    captured: dict[str, object] = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["max_tokens"] = max_tokens
            yield LLMTextResponse(
                content="Ragav, RM-DRIVE-01 is the immediate plant-risk focus.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())

    with client.stream(
        "POST",
        "/api/neo/chat/stream",
        json={"message": "Explain current plant risk in one paragraph"},
        headers=auth_headers("admin@plant.local"),
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    get_settings.cache_clear()
    events = [
        json.loads(line.removeprefix("data: "))
        for line in body.splitlines()
        if line.startswith("data: ")
    ]
    meta = next(event for event in events if event["type"] == "meta")
    final = next(event for event in events if event["type"] == "final")
    done = next(event for event in events if event["type"] == "done")
    assert captured["max_tokens"] == 250
    assert meta["runtime"] == "pydantic_ai"
    assert meta["provider"] == "openai"
    assert meta["used_live_provider"] is True
    assert meta["runtime_fallback"] is False
    assert final["response"]["markdown"] == "Ragav, RM-DRIVE-01 is the immediate plant-risk focus."
    assert done["response"]["answer"] == "Ragav, RM-DRIVE-01 is the immediate plant-risk focus."
    assert not any(event["type"] == "error" for event in events)


def test_trinity_runtime_bypasses_pydantic_validation_and_caps_live_text_tokens(monkeypatch):
    from app.core.config import get_settings
    import app.services.assistant_runtime as runtime
    from app.services.llm import LLMTextResponse

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ASSISTANT_RUNTIME", "pydantic_ai")
    get_settings.cache_clear()
    monkeypatch.setattr(
        runtime,
        "_run_pydantic_ai_output",
        lambda **kwargs: (_ for _ in ()).throw(runtime.AssistantRuntimeFailure("pydantic runtime unavailable")),
    )
    captured: dict[str, object] = {}

    class FakeClient:
        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["max_tokens"] = max_tokens
            yield LLMTextResponse(
                content="Vinoth, WO-8304 is blocked by material readiness.",
                used_live_provider=True,
                provider="openai",
            )

    events = list(
        runtime.stream_assistant_markdown(
            assistant_id="trinity",
            prompt="What should I do next?",
            system_prompt="Answer as Trinity.",
            fallback_client=FakeClient(),
            fallback_factory=lambda provider, reason: LLMTextResponse(
                content="",
                used_live_provider=False,
                provider=provider,
            ),
            max_tokens=900,
        )
    )

    get_settings.cache_clear()
    assert captured["max_tokens"] == 250
    assert "".join(event.content for event in events) == "Vinoth, WO-8304 is blocked by material readiness."
    assert all(event.provider == "openai" for event in events)
    assert all(event.used_live_provider for event in events)


def test_neo_welcome_streams_llm_context_and_done_event(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    captured = {}

    class FakeClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            captured["timeout_seconds"] = timeout_seconds
            yield LLMTextResponse(
                content="Plant priorities focus on risk and production impact.\n1. P1: Assets at risk: 4 critical/high-risk assets: review highest-risk diagnosis first.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    with client.stream(
        "GET",
        "/api/neo/welcome/stream",
        headers=auth_headers("supervisor@plant.local"),
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())

    assert captured["timeout_seconds"] == 15.0
    assert "Plant Priority Updates" in captured["prompt"]
    assert "Command Center plant priority updates" in captured["prompt"]
    assert "Final answer:" in captured["prompt"]
    assert "Sentence 1" not in captured["prompt"]
    assert '"type": "meta"' in body
    assert "Assets at risk" in body
    assert "WO-8311 and WO-8321 need approval" not in body
    assert '"type": "done"' in body
    assert '"title": "Plant Priority Updates"' in body
    assert '"provider": "openai"' in body


def test_neo_chat_avoids_generic_asset_table_resolver():
    response = client.post(
        "/api/neo/chat",
        json={"message": "Show assets"},
        headers=auth_headers("operator@plant.local"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"] is None
    assert payload["provider"] == "openai"
    assert "Grounded app response" not in payload["answer"]


def test_neo_resolves_previous_asset_context_from_session_history():
    response = client.post(
        "/api/neo/chat",
        json={
            "message": "which asset are you talking about",
            "history": [
                {
                    "role": "assistant",
                    "content": "P1: Assets at risk\n- Signal: RM-DRIVE-01 Hot Strip Mill Main Drive Motor has critical risk.",
                }
            ],
        },
        headers=auth_headers("supervisor@plant.local"),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["action"]["type"] == "session_context_lookup"
    assert payload["action"]["status"] == "completed"
    assert payload["table"]["title"] == "Previous Answer Asset Context"
    assert payload["table"]["rows"][0]["Asset"] == "RM-DRIVE-01"
    assert "RM-DRIVE-01" in payload["answer"]


def test_neo_user_table_is_role_limited():
    operator_response = client.post(
        "/api/neo/chat",
        json={"message": "Show users and roles"},
        headers=auth_headers("operator@plant.local"),
    )
    assert operator_response.status_code == 200
    operator_payload = operator_response.json()
    assert operator_payload["table"] is None
    assert operator_payload["provider"] == "openai"

    admin_response = client.post(
        "/api/neo/chat",
        json={"message": "Show users and roles"},
        headers=auth_headers(),
    )
    assert admin_response.status_code == 200
    admin_payload = admin_response.json()
    assert admin_payload["table"] is None
    assert admin_payload["provider"] == "openai"


def test_neo_user_table_supports_role_filters_with_llm_answer():
    response = client.post(
        "/api/neo/chat",
        json={"message": "list all supervisors"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"] is None
    assert payload["used_live_provider"] is True
    assert payload["provider"] == "openai"


def test_neo_welcome_highlights_assigned_technician_work(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "WO-8304" in prompt
            return LLMTextResponse(
                content="Ragav, WO-8304 is assigned to you and is waiting on blocked material before field work can start.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.get("/api/neo/welcome?context=work_execution", headers=auth_headers("technician@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "neo_welcome"
    assert payload["action"]["target_id"] == "WO-8304"
    assert "WO-8304" in payload["answer"]
    assert payload["table"]["title"] == "Your Assigned Work"
    assert {row["Work order"] for row in payload["table"]["rows"]} == {"WO-8304"}


def test_neo_command_center_prioritizes_plant_risk_categories(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "Command Center plant priority updates" in prompt
            assert "Assets at risk" in prompt
            assert "Overdue emergency work" in prompt
            assert "Do not list work orders" in system_prompt
            return LLMTextResponse(
                content="Plant priorities focus on production exposure.\n1. P1: Assets at risk: 4 critical/high-risk assets: review highest-risk diagnosis first.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.get("/api/neo/welcome", headers=auth_headers("technician@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["table"]["title"] == "Plant Priority Updates"
    assert payload["action"]["target_id"] == "Assets at risk"
    assert "Assets at risk" in payload["answer"]
    assert "WO-8304" not in payload["answer"]
    assert {row["Focus"] for row in payload["table"]["rows"]} >= {"Assets at risk", "Overdue emergency work", "Production impact"}


def test_neo_command_center_replaces_malformed_live_priority_text(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            return LLMTextResponse(
                content="P1\n- RM-DRIVE-01\n- Confirm spare ETA; reason\n- Drive end bearing is out of stock; P2",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.get("/api/neo/welcome", headers=auth_headers("technician@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert "Assets at risk" in payload["answer"]
    assert "Impact:" in payload["answer"]
    assert "P1:" in payload["answer"]
    assert "WO-8304" not in payload["answer"]
    assert "; reason" not in payload["answer"]
    assert payload["table"]["title"] == "Plant Priority Updates"


def test_neo_welcome_highlights_supervisor_approvals_and_followups(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "WO-8311" in prompt
            return LLMTextResponse(
                content="Dhruv, review WO-8311 first because it is waiting for approval.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.get("/api/neo/welcome?context=work_execution", headers=auth_headers("supervisor@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["table"]["title"] == "Supervisor Attention"
    assert "waiting for approval" in payload["answer"]
    assert any(row["Work order"] == "WO-8311" for row in payload["table"]["rows"])


def test_neo_pending_tasks_request_returns_role_aware_queue(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "show my pending tasks" in prompt
            assert "Role-aware queue" in prompt
            assert "Final answer:" in prompt
            assert "Relevant work-order context" not in prompt
            assert "WO-8311" in prompt
            return LLMTextResponse(
                content="Your pending queue starts with WO-8311 for approval, then WO-8321 and the blocked WO-8304 material follow-up.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.post(
        "/api/neo/chat",
        json={"message": "show my pending tasks"},
        headers=auth_headers("supervisor@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "neo_welcome"
    assert "WO-8311" in payload["answer"]
    assert payload["table"]["title"] == "Supervisor Attention"
    assert any(row["Work order"] == "WO-8311" for row in payload["table"]["rows"])


def test_neo_welcome_is_read_only_for_operator_attention(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "read-only" in prompt
            return LLMTextResponse(
                    content="Jan, read-only operator attention starts with RM-DRIVE-01 because it is high risk; monitor indications and report field observations.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.get("/api/neo/welcome?context=work_execution", headers=auth_headers("operator@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
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
    assert payload["provider"] == "openai"
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
    assert payload["provider"] == "openai"
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
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "work_order_next_steps"
    assert payload["action"]["target_id"] == "WO-8304"
    assert payload["table"]["rows"][0]["Work order"] == "WO-8304"
    assert payload["used_live_provider"] is True


def test_neo_technician_material_question_does_not_start_blocked_work_order():
    before = repository.get_work_order("WO-8304")
    assert before["status"] == "WMATL"
    assert before["material_readiness"] == "blocked"

    response = client.post(
        "/api/neo/chat",
        json={"message": "when is Drive end bearing available and how to start work"},
        headers=auth_headers("technician@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "work_order_material_status"
    assert payload["action"]["target_id"] == "WO-8304"
    assert payload["table"]["rows"][0]["Work order"] == "WO-8304"
    assert payload["used_live_provider"] is True
    assert repository.get_work_order("WO-8304")["status"] == "WMATL"


def test_neo_blocks_explicit_start_when_material_is_not_ready():
    response = client.post(
        "/api/neo/chat",
        json={"message": "start WO-8304"},
        headers=auth_headers("technician@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "update_work_order_status"
    assert payload["action"]["status"] == "not_allowed"
    assert "Drive end bearing is out of stock" in payload["answer"]
    assert repository.get_work_order("WO-8304")["status"] == "WMATL"


def test_neo_can_clear_material_blocker_with_tool_action(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    before = repository.get_work_order("WO-8275")
    assert before["status"] == "WMATL"
    assert before["material_readiness"] == "pending"

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "WO-8275 material readiness was updated to ready" in prompt
            return LLMTextResponse(
                content="WO-8275 material is now ready, blockers are cleared, and the work order can move forward for approval.",
                used_live_provider=True,
                provider="openai",
            )

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.post(
        "/api/neo/chat",
        json={"message": "Update WO-8275 as material received and no blockers"},
        headers=auth_headers("supervisor@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "update_work_order_material"
    assert payload["action"]["status"] == "completed"
    updated = repository.get_work_order("WO-8275")
    assert updated["material_readiness"] == "ready"
    assert updated["material_blocker_status"] == "reserved"
    assert updated["material_blocker_note"] is None
    assert updated["status"] == "APPR"


def test_neo_blocks_material_tool_for_operator():
    response = client.post(
        "/api/neo/chat",
        json={"message": "Update WO-8275 as material received and no blockers"},
        headers=auth_headers("operator@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action"]["type"] == "update_work_order_material"
    assert payload["action"]["status"] == "not_allowed"


def test_neo_can_assign_work_order_with_tool_action(monkeypatch):
    import app.services.neo_assistant as neo_module
    from app.services.llm import LLMTextResponse

    class FakeClient:
        def complete_text(self, prompt, system_prompt, fallback_factory, max_tokens=600):
            assert "WO-8311 was assigned to Vinoth" in prompt
            return LLMTextResponse(content="WO-8311 is now assigned to Vinoth.", used_live_provider=True, provider="openai")

    monkeypatch.setattr(neo_module, "_neo_llm_client", lambda: FakeClient())
    response = client.post(
        "/api/neo/chat",
        json={"message": "Assign WO-8311 to Vinoth"},
        headers=auth_headers("supervisor@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
    assert payload["action"]["type"] == "assign_work_order"
    assert repository.get_work_order("WO-8311")["assigned_to"] == "Vinoth"


def test_neo_can_create_work_order_for_critical_asset_when_role_allows():
    response = client.post(
        "/api/neo/chat",
        json={"message": "create work order for critical asset"},
        headers=auth_headers("planner@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "openai"
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
    assert payload["provider"] == "openai"
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


def test_neo_general_maintenance_query_uses_live_llm_text():
    response = client.post(
        "/api/neo/chat",
        json={"message": "how to inspect Blast Furnace Combustion Air Blower"},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["table"] is None
    assert payload["used_live_provider"] is True
    assert payload["provider"] == "openai"
    assert "live configured LLM" in payload["answer"]
    assert "### Safety Checks" not in payload["answer"]
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
    assert '"provider": "openai"' in body
    assert "Safety Checks" not in body


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


def test_retrieval_uses_qdrant_learning_example_hits(monkeypatch):
    monkeypatch.setattr("app.services.retrieval.configured_vector_store_name", lambda: "qdrant")
    monkeypatch.setattr("app.services.retrieval.search_document_chunks", lambda query, equipment_id, limit: [])
    monkeypatch.setattr(
        "app.services.retrieval.search_learning_examples",
        lambda query, equipment_id, limit: [
            VectorStoreHit(
                source_id="LEX-QDRANT",
                title="Approved learning: feedback",
                content="Root cause: loose foundation bolts. Action: retorque and recheck alignment.",
                source_type="learning_example",
                equipment_id="RM-DRIVE-01",
                score=0.93,
            )
        ],
    )

    evidence = retrieve_evidence("loose foundation bolts", "RM-DRIVE-01", limit=1, use_reranker=False)

    assert evidence[0].source_type == "learning_example"
    assert evidence[0].source_id == "LEX-QDRANT"
    assert evidence[0].relevance_reason == "Matched by qdrant approved learning example search."


def test_learning_model_registration_rejects_active_status():
    headers = auth_headers()
    response = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-unsafe-active",
            "base_model": "qwen2.5-7b-instruct",
            "adapter_path": "file:///models/unsafe-active",
            "status": "active",
        },
        headers=headers,
    )

    assert response.status_code == 422


def test_rag_embedding_profile_and_migration_controls_are_audited():
    operator_response = client.get(
        "/api/learning/rag/embedding-profiles",
        headers=auth_headers("operator@plant.local"),
    )
    assert operator_response.status_code == 403

    headers = auth_headers()
    profiles_response = client.get("/api/learning/rag/embedding-profiles", headers=headers)
    assert profiles_response.status_code == 200
    active_profile = next(profile for profile in profiles_response.json() if profile["status"] == "active")
    assert active_profile["model"] == "maintenance-hash-v1"

    create_response = client.post(
        "/api/learning/rag/embedding-profiles",
        json={
            "provider": "deterministic_hash",
            "model": "maintenance-hash-v2",
            "version": "2",
            "dimensions": 64,
            "distance": "Cosine",
            "notes": "Regression-test candidate profile.",
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    candidate = create_response.json()
    assert candidate["status"] == "candidate"
    assert candidate["id"] != active_profile["id"]

    preview_response = client.post(
        "/api/learning/rag/migration/preview",
        json={"profile_id": candidate["id"], "target_collection": "maintenance_wizard_documents_v2"},
        headers=headers,
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["dry_run"] is True
    assert preview["will_activate_profile"] is True
    assert preview["target_profile"]["id"] == candidate["id"]
    assert any("differs from active profile" in reason for reason in preview["reasons"])
    assert repository.get_active_rag_embedding_profile()["id"] == active_profile["id"]

    activate_response = client.post(
        f"/api/learning/rag/embedding-profiles/{candidate['id']}/activate",
        headers=headers,
    )
    assert activate_response.status_code == 200
    assert activate_response.json()["job_type"] == "rag_embedding_profile"
    assert repository.get_active_rag_embedding_profile()["id"] == candidate["id"]

    migration_response = client.post(
        "/api/learning/rag/migration",
        json={
            "profile_id": candidate["id"],
            "target_collection": "maintenance_wizard_documents_v2",
            "recreate_collection": False,
            "activate_profile": True,
            "notes": "Apply test migration.",
        },
        headers=headers,
    )
    assert migration_response.status_code == 200
    migration_job = migration_response.json()
    assert migration_job["job_type"] == "rag_migration"
    assert migration_job["output_refs"]["result"]["chunk_count"] >= 1
    migrated_chunks = repository.list_document_chunks(current_profile_only=True)
    assert migrated_chunks
    assert {chunk["embedding_profile_id"] for chunk in migrated_chunks} == {candidate["id"]}

    reindex_response = client.post(
        "/api/learning/rag/reindex",
        json={"target_collection": "maintenance_wizard_documents_v2", "recreate_collection": False},
        headers=headers,
    )
    assert reindex_response.status_code == 200
    reindex_job = reindex_response.json()
    assert reindex_job["job_type"] == "rag_reindex"
    assert reindex_job["input_refs"]["target_collection"] == "maintenance_wizard_documents_v2"


def test_rag_reindex_syncs_approved_learning_examples(monkeypatch):
    headers = auth_headers("maintenance@plant.local")
    client.post(
        "/api/recommendations/rec-qdrant-learning-sync/feedback",
        json={
            "equipment_id": "RM-DRIVE-01",
            "status": "accepted",
            "actual_root_cause": "Loose foundation bolt resonance",
            "action_taken": "Retorque foundation bolts and recheck alignment",
            "outcome": "Vibration normalized after bolt retorque",
        },
        headers=headers,
    )
    captured: dict[str, object] = {}

    def fake_index_document_chunks(chunks, *, collection_name=None, recreate_collection=False):
        return {
            "store": "qdrant",
            "collection": collection_name,
            "embedding_profile_id": "test-profile",
            "indexed": len(chunks),
            "state": "indexed",
        }

    def fake_sync_learning_examples(examples, *, collection_name=None, min_judge_score=0.65):
        captured["collection_name"] = collection_name
        captured["examples"] = examples
        captured["min_judge_score"] = min_judge_score
        return {
            "store": "qdrant",
            "collection": collection_name,
            "embedding_profile_id": "test-profile",
            "eligible": len(examples),
            "indexed": len(examples),
            "deleted": 0,
            "state": "synced",
        }

    monkeypatch.setattr(repository, "index_document_chunks", fake_index_document_chunks)
    monkeypatch.setattr(repository, "sync_learning_examples_index", fake_sync_learning_examples)

    response = client.post(
        "/api/learning/rag/reindex",
        json={"target_collection": "maintenance_wizard_documents_learning", "recreate_collection": False},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_type"] == "rag_reindex"
    assert payload["output_refs"]["learning_index_result"]["state"] == "synced"
    assert captured["collection_name"] == "maintenance_wizard_documents_learning"
    examples = captured["examples"]
    assert isinstance(examples, list)
    assert any(example["source_type"] == "feedback" and example["approved"] for example in examples)


def test_feedback_statuses_sync_plant_rag_records(monkeypatch):
    captured_records: list[dict[str, object]] = []

    def fake_sync_plant_records(records, *, collection_name=None):
        captured_records.extend(records)
        return {"store": "qdrant", "collection": collection_name, "indexed": len(records), "state": "synced"}

    monkeypatch.setattr(repository, "sync_plant_records_index", fake_sync_plant_records)

    for status in ["accepted", "corrected", "rejected"]:
        result = repository.save_feedback(
            f"rec-rag-feedback-{status}",
            {
                "equipment_id": "RM-DRIVE-01",
                "status": status,
                "actual_root_cause": f"{status} bearing root cause",
                "action_taken": "Adjusted operating procedure",
                "outcome": "Risk reduced",
                "notes": "RAG sync regression.",
            },
        )
        assert result["state"] == "synced"

    assert [record["source_type"] for record in captured_records] == ["feedback", "feedback", "feedback"]
    assert [record["equipment_id"] for record in captured_records] == ["RM-DRIVE-01", "RM-DRIVE-01", "RM-DRIVE-01"]
    assert all("status" in str(record["content"]) for record in captured_records)


def test_plant_rag_records_cover_persisted_operational_and_learning_tables(monkeypatch):
    repository.save_auth_audit_event(
        "login",
        True,
        email="admin@plant.local",
        user_id="USER-ADMIN",
        role="admin",
        detail="Coverage test login.",
    )
    repository.save_pm_plan(
        {
            "equipment_id": "RM-DRIVE-01",
            "title": "RM drive bearing thermal PM",
            "status": "active",
            "cadence_days": 14,
            "next_due_date": "2026-06-20T08:00:00+05:30",
            "trigger": {"description": "High bearing temperature and vibration risk"},
            "thresholds": [{"signal": "bearing_temperature", "limit": 85}],
            "tasks": [{"description": "Inspect drive end bearing lubrication and alignment"}],
            "source": "morpheus",
            "generated_by": "morpheus",
            "used_live_provider": True,
            "provider": "openai",
        }
    )
    repository.save_document_intelligence(
        {
            "document_id": "DOC-RM-SOP-01",
            "summary": "Drive SOP mentions bearing temperature and vibration response.",
            "asset_ids": ["RM-DRIVE-01"],
            "components": ["Drive end bearing"],
            "failure_modes": ["Bearing overheating"],
            "symptoms": ["High vibration"],
            "safety_constraints": ["Lockout required"],
            "spares": ["Drive end bearing"],
            "thresholds": ["Bearing temperature high"],
            "used_live_provider": True,
            "provider": "openai",
        }
    )
    repository.save_feedback(
        "rec-rag-coverage",
        {
            "equipment_id": "RM-DRIVE-01",
            "status": "accepted",
            "actual_root_cause": "Bearing lubrication starvation",
            "action_taken": "Lubricated bearing and verified vibration",
            "outcome": "Risk reduced",
            "notes": "Useful for future diagnosis.",
        },
    )
    repository.save_maintenance_label(
        {
            "source_type": "work_order",
            "source_id": "WO-8304",
            "equipment_id": "RM-DRIVE-01",
            "failure_mode": "bearing overheating",
            "component": "drive end bearing",
            "root_cause": "lubrication starvation",
            "action_class": "inspection",
            "outcome_status": "training_worthy",
            "signal_hints": ["bearing_temperature", "vibration"],
            "usable_for_training": True,
            "used_live_provider": True,
            "provider": "openai",
        }
    )
    repository.save_streaming_message(
        "MSG-RAG-COVERAGE-1",
        "iot-gateway",
        "sensor_reading",
        "plant.rm-drive-01.sensor",
        "processed",
    )
    repository.save_learning_interaction(
        {
            "assistant": "neo",
            "interaction_type": "chat",
            "user_id": "USER-SUPERVISOR",
            "user_role": "maintenance_supervisor",
            "equipment_id": "RM-DRIVE-01",
            "work_order_id": "WO-8304",
            "prompt": "Explain active alerts.",
            "response": "RM-DRIVE-01 has bearing temperature and vibration risk.",
            "provider": "openai",
            "used_live_provider": True,
            "approved_for_learning": True,
            "outcome_status": "accepted",
        }
    )
    repository.upsert_learning_example(
        {
            "source_type": "assistant_interaction",
            "source_id": "rag-coverage-interaction",
            "equipment_id": "RM-DRIVE-01",
            "work_order_id": "WO-8304",
            "instruction": "Prioritize plant risk.",
            "input_text": "Active alert context",
            "expected_output": "Escalate bearing temperature risk.",
            "approved": True,
            "judge_score": 0.95,
            "judge_label": "Training Worthy",
            "judge_rationale": "Grounded and actionable.",
            "judge_provider": "openai",
            "judge_used_live_provider": True,
        }
    )
    snapshot = repository.create_learning_dataset_snapshot(
        {
            "name": "rag-coverage-snapshot",
            "description": "Coverage test snapshot",
            "example_count": 1,
            "approved_only": True,
            "jsonl_content": "{}\n",
            "created_by": "admin@plant.local",
        }
    )
    model = repository.save_learning_model_version(
        {
            "provider": "llama.cpp",
            "model_name": "qwen2.5-7b-instruct",
            "base_model": "Qwen2.5-7B-Instruct",
            "adapter_path": "/tmp/adapter",
            "status": "candidate",
            "notes": "Coverage test adapter.",
        }
    )
    evaluation = repository.save_learning_evaluation_run(
        {
            "dataset_id": snapshot["id"],
            "model_version_id": model["id"],
            "prompt_version_id": "neo/default",
            "metrics": {"pass_rate": 1.0},
            "notes": "Coverage test evaluation.",
            "passed": True,
        }
    )
    repository.save_learning_model_promotion(
        {
            "model_version_id": model["id"],
            "previous_active_model_id": "model-local-qwen2.5-current",
            "evaluation_run_id": evaluation["id"],
            "dataset_id": snapshot["id"],
            "prompt_version_id": "neo/default",
            "action": "promoted",
            "reviewer_email": "admin@plant.local",
            "notes": "Coverage test promotion.",
        }
    )
    deployment = repository.save_learning_model_deployment(
        {
            "model_version_id": model["id"],
            "job_id": None,
            "runtime_provider": "llama.cpp",
            "serving_provider": "openai",
            "served_model_name": "qwen2.5-7b-instruct",
            "base_url": "http://localhost:8080/v1",
            "artifact_uri": "/tmp/adapter",
            "artifact_hash": "hash",
            "status": "verified",
            "health_status": "healthy",
            "health_checked_at": "2026-06-17T08:00:00+05:30",
            "metadata": {"adapter": "loaded"},
        }
    )
    job = repository.save_learning_job(
        {
            "job_type": "peft_tuning",
            "subject": "maintenance.learning.peft.requested",
            "status": "completed",
            "requested_by": "admin@plant.local",
            "input_refs": {"dataset_id": snapshot["id"]},
            "output_refs": {"deployment_id": deployment["id"]},
        }
    )
    repository.save_learning_artifact(
        {
            "job_id": job["id"],
            "artifact_type": "adapter",
            "uri": "/tmp/adapter",
            "content_hash": "hash",
            "metadata": {"model_version_id": model["id"]},
        }
    )

    records = repository.list_plant_rag_records()
    source_types = {record["source_type"] for record in records}
    user_records = [record for record in records if record["source_type"] == "user"]
    assert any("Vinoth" in record["content"] and "maintenance_technician" in record["content"] for record in user_records)
    assert all("password" not in record["content"].lower() for record in user_records)
    expected_source_types = {
        "equipment",
        "asset_profile",
        "asset_metric_snapshot",
        "asset_recommendation",
        "asset_subsystem",
        "asset_reliability_metric",
        "alert",
        "sensor_reading",
        "spare",
        "work_order",
        "work_order_spare",
        "work_order_log",
        "maintenance_event",
        "pm_template",
        "pm_plan",
        "rca_case",
        "document",
        "document_intelligence",
        "feedback",
        "maintenance_label",
        "streaming_message",
        "user",
        "auth_audit_event",
        "assistant_interaction",
        "learning_example",
        "learning_dataset_snapshot",
        "learning_model_version",
        "learning_prompt_version",
        "learning_evaluation_run",
        "learning_model_promotion",
        "learning_model_deployment",
        "learning_job",
        "learning_artifact",
        "rag_embedding_profile",
    }
    assert expected_source_types <= source_types

    captured: dict[str, object] = {}

    def fake_index_document_chunks(chunks, *, collection_name=None, recreate_collection=False):
        return {"store": "qdrant", "collection": collection_name, "indexed": len(chunks), "state": "indexed"}

    def fake_sync_learning_examples(examples, *, collection_name=None, min_judge_score=0.65):
        return {"store": "qdrant", "collection": collection_name, "eligible": len(examples), "indexed": len(examples), "state": "synced"}

    def fake_sync_plant_records(records, *, collection_name=None):
        if collection_name:
            captured["collection_name"] = collection_name
            captured["records"] = records
        return {"store": "qdrant", "collection": collection_name, "indexed": len(records), "state": "synced"}

    monkeypatch.setattr(repository, "index_document_chunks", fake_index_document_chunks)
    monkeypatch.setattr(repository, "sync_learning_examples_index", fake_sync_learning_examples)
    monkeypatch.setattr(repository, "sync_plant_records_index", fake_sync_plant_records)

    response = client.post(
        "/api/learning/rag/reindex",
        json={"target_collection": "maintenance_wizard_documents_all_records", "recreate_collection": False},
        headers=auth_headers(),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["output_refs"]["plant_index_result"]["state"] == "synced"
    assert captured["collection_name"] == "maintenance_wizard_documents_all_records"
    indexed_source_types = {record["source_type"] for record in captured["records"]}
    assert expected_source_types <= indexed_source_types


def test_work_order_spare_replacement_deletes_stale_plant_records(monkeypatch):
    deleted_source_ids: list[str] = []

    def fake_delete_plant_records(source_ids, *, collection_name=None):
        deleted_source_ids.extend(source_ids)
        return {"store": "qdrant", "collection": collection_name, "deleted": len(source_ids), "state": "deleted"}

    monkeypatch.setattr(repository, "delete_plant_records_index", fake_delete_plant_records)

    work_order = repository.get_work_order("WO-8304")
    assert work_order["spare_reservations"]
    stale_source_ids = [f"work_order_spare:{item['id']}" for item in work_order["spare_reservations"]]

    updated = repository.update_work_order(
        "WO-8304",
        {
            "spare_reservations": [
                {
                    "spare_id": "BRG-22",
                    "spare_name": "Drive End Bearing Cartridge",
                    "required_qty": 1,
                    "reserved_qty": 1,
                    "available_qty": 1,
                    "reorder_requested": False,
                    "procurement_status": "reserved",
                    "procurement_lead_time_days": 0,
                    "expected_available_date": None,
                    "substitute_spare_id": None,
                    "substitute_name": None,
                    "blocker_status": "reserved",
                    "blocker_note": None,
                }
            ]
        },
    )

    assert updated is not None
    assert deleted_source_ids == stale_source_ids
    assert [f"work_order_spare:{item['id']}" for item in updated["spare_reservations"]] != stale_source_ids


def test_learning_review_endpoints_are_role_gated_and_export_jsonl(monkeypatch):
    monkeypatch.setenv("LEARNING_ARTIFACT_RETENTION_DAYS", "0")
    monkeypatch.setenv("LEARNING_ARTIFACT_CLEANUP_ENABLED", "false")
    monkeypatch.setenv("LEARNING_PEFT_TRAINER_COMMAND", "")
    monkeypatch.setenv("LEARNING_ADAPTER_DEPLOYER_COMMAND", "")
    get_settings.cache_clear()
    operator_response = client.get("/api/learning/summary", headers=auth_headers("operator@plant.local"))
    assert operator_response.status_code == 403
    reliability_response = client.get("/api/learning/summary", headers=auth_headers("reliability@plant.local"))
    assert reliability_response.status_code == 403

    headers = auth_headers()
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
    assert summary["vector_store"]["embedding_profile"]["model"] == "maintenance-hash-v1"
    assert summary["vector_store"]["embedding_profile"]["version"] == "1"
    assert summary["vector_store"]["migration_required"] is False
    assert summary["artifact_store"]["store"] == "filesystem"
    assert summary["artifact_store"]["state"] == "ready"
    assert summary["artifact_store"]["retention"] == {
        "state": "disabled",
        "enabled": False,
        "retention_days": 0,
        "cleanup_enabled": False,
        "dry_run_default": True,
        "scope": "local_filesystem",
        "errors": [],
    }
    assert summary["peft_trainer"]["mode"] == "prepared_artifacts"
    assert summary["peft_trainer"]["configured"] is False

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
    assert promotion_response.status_code == 400
    assert "runtime-loaded deployment" in promotion_response.json()["detail"]

    manual_deployment_response = client.post(
        f"/api/learning/model-versions/{model['id']}/deploy",
        json={
            "runtime_provider": "manual",
            "served_model_name": "qwen2.5-7b-instruct-lora-served",
            "base_url": "http://127.0.0.1:8080/v1",
            "artifact_uri": model["adapter_path"],
            "notes": "Manual runtime deployment verified by reviewer.",
        },
        headers=headers,
    )
    assert manual_deployment_response.status_code == 200
    manual_deployment_job = manual_deployment_response.json()
    with pytest.raises(RuntimeError, match="Manual deployment records cannot prove"):
        process_learning_job_message(
            {
                "schema_version": "1",
                "job_id": manual_deployment_job["id"],
                "job_type": "adapter_deployment",
                "requested_by": "admin@plant.local",
                "correlation_id": manual_deployment_job["correlation_id"],
                "input_refs": manual_deployment_job["input_refs"],
            },
            manual_deployment_job["subject"],
        )

    class RuntimeProbeResponse:
        def raise_for_status(self):
            return None

        @property
        def status_code(self):
            return 200

    monkeypatch.setattr("app.services.adapter_runtime.httpx.post", lambda *args, **kwargs: RuntimeProbeResponse())

    deployment_response = client.post(
        f"/api/learning/model-versions/{model['id']}/deploy",
        json={
            "runtime_provider": "llama_cpp",
            "served_model_name": "qwen2.5-7b-instruct-lora-served",
            "base_url": "http://127.0.0.1:8080/v1",
            "artifact_uri": model["adapter_path"],
            "notes": "llama.cpp deployment verified by runtime probe.",
        },
        headers=headers,
    )
    assert deployment_response.status_code == 200
    deployment_job = deployment_response.json()
    assert deployment_job["job_type"] == "adapter_deployment"
    assert deployment_job["subject"] == "maintenance.learning.adapter.deployment.requested"
    assert deployment_job["status"] == "queued"
    assert deployment_job["output_refs"]["dispatch"] == "disabled"

    processed_deployment_job = process_learning_job_message(
        {
            "schema_version": "1",
            "job_id": deployment_job["id"],
            "job_type": "adapter_deployment",
            "requested_by": "admin@plant.local",
            "correlation_id": deployment_job["correlation_id"],
            "input_refs": deployment_job["input_refs"],
        },
        deployment_job["subject"],
    )
    assert processed_deployment_job.status == "completed"

    deployments_response = client.get("/api/learning/model-deployments", headers=headers)
    assert deployments_response.status_code == 200
    deployments = deployments_response.json()
    deployment = next(item for item in deployments if item["model_version_id"] == model["id"] and item["status"] == "verified")
    assert deployment["status"] == "verified"
    assert deployment["health_status"] == "healthy"
    assert deployment["served_model_name"] == "qwen2.5-7b-instruct-lora-served"
    assert deployment["base_url"] == "http://127.0.0.1:8080/v1"
    assert deployment["artifact_uri"] == model["adapter_path"]

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
            openai_base_url="http://127.0.0.1:8080/v1",
            ollama_model="env-ollama",
            ollama_base_url="http://localhost:11434",
            llm_use_active_learning_model=True,
            learning_runtime_deployment_required=True,
        )
    )
    assert serving.source == "learning_verified_deployment"
    assert serving.provider == "openai"
    assert serving.openai_model == deployment["served_model_name"]
    assert serving.openai_base_url == deployment["base_url"]
    assert serving.active_model_version_id == model["id"]
    assert serving.deployment_id == deployment["id"]
    assert serving.runtime_provider == "llama_cpp"
    assert serving.health_status == "healthy"
    assert serving.adapter_path == model["adapter_path"]

    mock_serving = active_llm_serving_config(
        SimpleNamespace(
            llm_provider="mock",
            openai_model="env-model",
            openai_api_key=None,
            openai_base_url="http://127.0.0.1:8080/v1",
            ollama_model="env-ollama",
            ollama_base_url="http://localhost:11434",
            llm_use_active_learning_model=True,
            learning_runtime_deployment_required=True,
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

    paged_examples = client.get("/api/learning/examples/page?limit=1&offset=0", headers=headers)
    assert paged_examples.status_code == 200
    assert paged_examples.json()["total"] >= 1
    assert len(paged_examples.json()["items"]) == 1

    paged_evaluations = client.get("/api/learning/evaluations/page?limit=1&offset=0", headers=headers)
    assert paged_evaluations.status_code == 200
    assert paged_evaluations.json()["total"] >= 1
    assert len(paged_evaluations.json()["items"]) == 1

    paged_jobs = client.get("/api/learning/jobs/page?limit=1&offset=0", headers=headers)
    assert paged_jobs.status_code == 200
    assert paged_jobs.json()["total"] >= 1
    assert len(paged_jobs.json()["items"]) == 1

    paged_deployments = client.get("/api/learning/model-deployments/page?limit=1&offset=0", headers=headers)
    assert paged_deployments.status_code == 200
    assert paged_deployments.json()["total"] >= 1
    assert len(paged_deployments.json()["items"]) == 1

    paged_promotions = client.get("/api/learning/model-promotions/page?limit=1&offset=0", headers=headers)
    assert paged_promotions.status_code == 200
    assert paged_promotions.json()["total"] >= 1
    assert len(paged_promotions.json()["items"]) == 1

    paged_artifacts = client.get("/api/learning/artifacts/page?limit=1&offset=0", headers=headers)
    assert paged_artifacts.status_code == 200
    assert "items" in paged_artifacts.json()
    assert "total" in paged_artifacts.json()


def test_learning_review_can_reindex_rag_vectors():
    operator_response = client.post("/api/learning/rag/reindex", headers=auth_headers("operator@plant.local"))
    assert operator_response.status_code == 403

    headers = auth_headers()
    response = client.post("/api/learning/rag/reindex", headers=headers)
    assert response.status_code == 200
    job = response.json()
    assert job["job_type"] == "rag_reindex"
    assert job["status"] == "completed"
    assert job["output_refs"]["document_count"] >= 1
    assert job["output_refs"]["chunk_count"] >= 1
    assert job["output_refs"]["index_result"]["store"] == "sqlite"


def test_embedding_profile_reports_unsupported_provider_and_dimension_mismatch():
    unsupported = embedding_profile_status(
        SimpleNamespace(
            rag_embedding_provider="bge",
            rag_embedding_model="bge-small-en-v1.5",
            rag_embedding_version="2026-06",
            rag_embedding_dimensions=384,
            rag_embedding_distance="Cosine",
        )
    )
    mismatch = embedding_profile_status(
        SimpleNamespace(
            rag_embedding_provider="deterministic_hash",
            rag_embedding_model="maintenance-hash-v1",
            rag_embedding_version="2",
            rag_embedding_dimensions=128,
            rag_embedding_distance="Cosine",
        )
    )

    assert unsupported["state"] == "unsupported_provider_fallback"
    assert "external embedding worker" in unsupported["warning"]
    assert mismatch["state"] == "dimension_mismatch"
    assert "Configured dimensions 128" in mismatch["warning"]


def test_peft_learning_job_publishes_when_async_learning_is_enabled(monkeypatch):
    headers = auth_headers()
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


def test_learning_stream_subjects_do_not_overlap_dlq_subject():
    subjects = learning_stream_subjects("maintenance.learning")

    assert subjects == ["maintenance.learning.>"]
    assert "maintenance.learning.dlq" not in subjects


def test_learning_worker_prepares_peft_artifacts(monkeypatch, tmp_path):
    headers = auth_headers()
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
            "requested_by": "admin@plant.local",
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
        assert artifact["metadata"]["storage_backend"] == "filesystem"
        assert artifact["metadata"]["content_hash_algorithm"] == "sha256"


def test_learning_worker_runs_configured_peft_trainer_and_registers_candidate(monkeypatch, tmp_path):
    headers = auth_headers()
    client.post("/api/learning/examples/refresh", headers=headers)
    dataset = client.post(
        "/api/learning/datasets",
        json={"name": "trainer-learning-snapshot", "approved_only": True, "min_judge_score": 0.65},
        headers=headers,
    ).json()
    model = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-trainer-source",
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
            "adapter_name": "maintenance-wizard-external-lora",
            "training_config": {"method": "lora", "epochs": 1},
        },
        headers=headers,
    ).json()

    def fake_trainer_run(command_args, cwd, env, text, capture_output, timeout, check):
        assert command_args == ["fake-peft-trainer"]
        assert text is True
        assert capture_output is True
        assert check is False
        assert timeout == 45
        assert env["MW_PEFT_ADAPTER_NAME"] == "maintenance-wizard-external-lora"
        assert env["MW_PEFT_BASE_MODEL"] == "qwen2.5-7b-instruct"
        assert os.path.exists(env["MW_PEFT_DATASET_PATH"])
        assert os.path.exists(env["MW_PEFT_MANIFEST_PATH"])
        output_dir = env["MW_PEFT_OUTPUT_DIR"]
        os.makedirs(output_dir, exist_ok=True)
        manifest_path = os.path.join(output_dir, "adapter_manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "provider": "openai",
                    "model_name": "maintenance-wizard-qwen-peft-trained",
                    "base_model": "qwen2.5-7b-instruct",
                    "adapter_path": "file:///models/maintenance-wizard-qwen-peft-trained",
                    "notes": "Fake trainer completed for regression coverage.",
                },
                handle,
            )
        return SimpleNamespace(returncode=0, stdout="trainer completed", stderr="")

    monkeypatch.setattr(
        "app.services.learning.get_settings",
        lambda: SimpleNamespace(
            learning_artifact_dir=tmp_path / "artifacts",
            learning_peft_trainer_command="fake-peft-trainer",
            learning_peft_trainer_timeout_seconds=45,
            learning_peft_output_dir=tmp_path / "adapters",
        ),
    )
    monkeypatch.setattr("app.services.learning.subprocess.run", fake_trainer_run)

    processed = process_learning_job_message(
        {
            "schema_version": "1",
            "job_id": peft_job["id"],
            "job_type": "peft_tuning",
            "requested_by": "admin@plant.local",
            "correlation_id": peft_job["correlation_id"],
            "input_refs": peft_job["input_refs"],
        },
        peft_job["subject"],
    )

    assert processed.status == "completed"
    completed_job = repository.get_learning_job(peft_job["id"])
    assert completed_job["output_refs"]["trainer_mode"] == "external_command"
    assert completed_job["output_refs"]["training_status"] == "adapter_candidate_registered"
    registered_model = repository.get_learning_model_version(completed_job["output_refs"]["registered_model_version_id"])
    assert registered_model
    assert registered_model["status"] == "candidate"
    assert registered_model["model_name"] == "maintenance-wizard-qwen-peft-trained"
    assert registered_model["adapter_path"] == "file:///models/maintenance-wizard-qwen-peft-trained"
    artifacts = repository.list_learning_artifacts(job_id=peft_job["id"])
    assert {artifact["artifact_type"] for artifact in artifacts} == {
        "peft_dataset_jsonl",
        "peft_training_manifest",
        "peft_training_log",
        "peft_adapter_registry",
        "peft_adapter_manifest",
    }


def test_learning_worker_rejects_successful_peft_trainer_without_manifest(monkeypatch, tmp_path):
    headers = auth_headers()
    client.post("/api/learning/examples/refresh", headers=headers)
    dataset = client.post(
        "/api/learning/datasets",
        json={"name": "missing-manifest-learning-snapshot", "approved_only": True, "min_judge_score": 0.65},
        headers=headers,
    ).json()
    model = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-missing-manifest",
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
            "adapter_name": "maintenance-wizard-missing-manifest-lora",
            "training_config": {"method": "lora", "epochs": 1},
        },
        headers=headers,
    ).json()

    def fake_trainer_run(command_args, cwd, env, text, capture_output, timeout, check):
        os.makedirs(env["MW_PEFT_OUTPUT_DIR"], exist_ok=True)
        return SimpleNamespace(returncode=0, stdout="trainer completed without manifest", stderr="")

    monkeypatch.setattr(
        "app.services.learning.get_settings",
        lambda: SimpleNamespace(
            learning_artifact_dir=tmp_path / "artifacts",
            learning_peft_trainer_command="fake-peft-trainer",
            learning_peft_trainer_timeout_seconds=45,
            learning_peft_output_dir=tmp_path / "adapters",
        ),
    )
    monkeypatch.setattr("app.services.learning.subprocess.run", fake_trainer_run)

    with pytest.raises(ValueError, match="adapter_manifest.json"):
        process_learning_job_message(
            {
                "schema_version": "1",
                "job_id": peft_job["id"],
                "job_type": "peft_tuning",
                "requested_by": "admin@plant.local",
                "correlation_id": peft_job["correlation_id"],
                "input_refs": peft_job["input_refs"],
            },
            peft_job["subject"],
        )

    failed_job = repository.get_learning_job(peft_job["id"])
    assert failed_job["status"] == "failed"
    assert "adapter_manifest.json" in failed_job["error"]
    assert repository.list_learning_artifacts(job_id=peft_job["id"])


def test_learning_artifact_store_supports_s3_uri_registration(monkeypatch, tmp_path):
    artifact_path = tmp_path / "dataset.jsonl"
    artifact_path.write_text('{"messages":[]}\n', encoding="utf-8")
    uploads = []

    class FakeS3Client:
        def upload_file(self, filename, bucket, key, ExtraArgs=None):
            uploads.append(
                {
                    "filename": filename,
                    "bucket": bucket,
                    "key": key,
                    "extra_args": ExtraArgs or {},
                }
            )

    settings = SimpleNamespace(
        learning_artifact_store="s3",
        learning_artifact_dir=tmp_path,
        learning_artifact_s3_bucket="mw-learning",
        learning_artifact_s3_prefix="peft",
        learning_artifact_s3_endpoint_url="http://minio:9000",
        learning_artifact_s3_region="us-east-1",
    )
    monkeypatch.setattr("app.services.artifact_store._s3_client", lambda _: FakeS3Client())

    status = artifact_store_status(settings)
    stored = store_learning_artifact_file(
        job_id="LJOB-S3",
        artifact_type="peft_dataset_jsonl",
        path=artifact_path,
        content_hash="abc123",
        metadata={"dataset_id": "LDS-1"},
        settings=settings,
    )

    assert status["state"] == "configured"
    assert stored.uri == "s3://mw-learning/peft/LJOB-S3/peft_dataset_jsonl/dataset.jsonl"
    assert stored.metadata["storage_backend"] == "s3"
    assert stored.metadata["bucket"] == "mw-learning"
    assert stored.metadata["object_key"] == "peft/LJOB-S3/peft_dataset_jsonl/dataset.jsonl"
    assert stored.metadata["local_retained"] is True
    assert uploads == [
        {
            "filename": str(artifact_path),
            "bucket": "mw-learning",
            "key": "peft/LJOB-S3/peft_dataset_jsonl/dataset.jsonl",
            "extra_args": {"Metadata": {"job-id": "LJOB-S3", "artifact-type": "peft_dataset_jsonl", "sha256": "abc123"}},
        }
    ]


def test_learning_artifact_lifecycle_finds_expired_files_without_deleting_by_default(tmp_path):
    reference_time = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)
    old_artifact = tmp_path / "LJOB-OLD" / "dataset.jsonl"
    fresh_artifact = tmp_path / "LJOB-FRESH" / "dataset.jsonl"
    old_artifact.parent.mkdir(parents=True)
    fresh_artifact.parent.mkdir(parents=True)
    old_artifact.write_text('{"messages":["old"]}\n', encoding="utf-8")
    fresh_artifact.write_text('{"messages":["fresh"]}\n', encoding="utf-8")
    old_time = (reference_time - timedelta(days=10)).timestamp()
    fresh_time = (reference_time - timedelta(days=2)).timestamp()
    os.utime(old_artifact, (old_time, old_time))
    os.utime(fresh_artifact, (fresh_time, fresh_time))
    settings = SimpleNamespace(
        learning_artifact_store="filesystem",
        learning_artifact_dir=tmp_path,
        learning_artifact_retention_days=7,
        learning_artifact_cleanup_enabled=False,
    )

    status = artifact_store_status(settings)
    expired = find_expired_filesystem_artifacts(settings=settings, reference_time=reference_time)
    cleanup = cleanup_expired_filesystem_artifacts(settings=settings, reference_time=reference_time)
    delete_requested = cleanup_expired_filesystem_artifacts(
        settings=settings,
        reference_time=reference_time,
        dry_run=False,
    )

    assert status["retention"]["state"] == "ready"
    assert status["retention"]["retention_days"] == 7
    assert status["retention"]["cleanup_enabled"] is False
    assert [candidate["relative_path"] for candidate in expired] == ["LJOB-OLD/dataset.jsonl"]
    assert expired[0]["age_days"] == 10
    assert cleanup["dry_run"] is True
    assert cleanup["expired_count"] == 1
    assert cleanup["deleted_count"] == 0
    assert delete_requested["dry_run"] is False
    assert delete_requested["deletion_allowed"] is False
    assert delete_requested["deleted_count"] == 0
    assert old_artifact.exists()
    assert fresh_artifact.exists()


def test_learning_artifact_lifecycle_reports_invalid_config(tmp_path):
    settings = SimpleNamespace(
        learning_artifact_store="filesystem",
        learning_artifact_dir=tmp_path,
        learning_artifact_retention_days="forever",
        learning_artifact_cleanup_enabled="sometimes",
    )

    status = artifact_store_status(settings)

    assert status["retention"]["state"] == "invalid_config"
    assert status["retention"]["enabled"] is False
    assert validate_learning_artifact_lifecycle_config(settings) == [
        "LEARNING_ARTIFACT_RETENTION_DAYS must be an integer number of days",
        "LEARNING_ARTIFACT_CLEANUP_ENABLED must be a boolean value",
    ]
    with pytest.raises(ValueError, match="Invalid learning artifact lifecycle config"):
        find_expired_filesystem_artifacts(settings=settings)


def test_learning_artifact_cleanup_api_is_db_backed_audited_and_role_guarded(monkeypatch, tmp_path):
    reference_time = datetime.now(timezone.utc) - timedelta(days=1)
    expired_file = tmp_path / "LJOB-CLEAN" / "dataset.jsonl"
    protected_file = tmp_path / "LJOB-PROTECTED" / "adapter.bin"
    fresh_file = tmp_path / "LJOB-FRESH" / "manifest.json"
    for artifact_file in [expired_file, protected_file, fresh_file]:
        artifact_file.parent.mkdir(parents=True, exist_ok=True)
        artifact_file.write_text(artifact_file.name, encoding="utf-8")
    expired_time = (reference_time - timedelta(days=10)).timestamp()
    fresh_time = (reference_time - timedelta(days=2)).timestamp()
    os.utime(expired_file, (expired_time, expired_time))
    os.utime(protected_file, (expired_time, expired_time))
    os.utime(fresh_file, (fresh_time, fresh_time))
    expired_artifact = repository.save_learning_artifact(
        {
            "job_id": "LJOB-CLEAN",
            "artifact_type": "peft_dataset_jsonl",
            "uri": str(expired_file),
            "content_hash": "hash-clean",
            "metadata": {"storage_backend": "filesystem", "local_path": str(expired_file)},
        }
    )
    protected_artifact = repository.save_learning_artifact(
        {
            "job_id": "LJOB-PROTECTED",
            "artifact_type": "peft_adapter_manifest",
            "uri": str(protected_file),
            "content_hash": "hash-protected",
            "metadata": {"storage_backend": "filesystem", "local_path": str(protected_file)},
        }
    )
    repository.save_learning_artifact(
        {
            "job_id": "LJOB-FRESH",
            "artifact_type": "peft_training_manifest",
            "uri": str(fresh_file),
            "content_hash": "hash-fresh",
            "metadata": {"storage_backend": "filesystem", "local_path": str(fresh_file)},
        }
    )
    repository.save_learning_model_version(
        {
            "id": "model-protected-artifact",
            "provider": "openai",
            "model_name": "protected-adapter",
            "base_model": "qwen2.5",
            "adapter_path": str(protected_file),
            "status": "candidate",
            "notes": "Protect cleanup candidate.",
        }
    )
    settings = SimpleNamespace(
        learning_artifact_store="filesystem",
        learning_artifact_dir=tmp_path,
        learning_artifact_retention_days=7,
        learning_artifact_cleanup_enabled=False,
    )
    monkeypatch.setattr("app.services.artifact_store.get_settings", lambda: settings)

    forbidden = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": True},
        headers=auth_headers("operator@plant.local"),
    )
    assert forbidden.status_code == 403

    artifacts_response = client.get("/api/learning/artifacts", headers=auth_headers())
    assert artifacts_response.status_code == 200
    assert any(item["id"] == expired_artifact["id"] for item in artifacts_response.json())

    preview = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": True, "notes": "preview cleanup"},
        headers=auth_headers(),
    )
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["dry_run"] is True
    assert preview_payload["deletion_allowed"] is False
    assert preview_payload["expired_count"] == 1
    assert preview_payload["protected_count"] == 1
    assert preview_payload["candidates"][0]["artifact_id"] == expired_artifact["id"]
    assert preview_payload["protected"][0]["artifact_id"] == protected_artifact["id"]
    assert "active/candidate/promoted model" in preview_payload["protected"][0]["protected_reason"]
    assert expired_file.exists()
    assert protected_file.exists()

    apply_forbidden = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": False},
        headers=auth_headers("maintenance@plant.local"),
    )
    assert apply_forbidden.status_code == 403

    disabled_apply = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": False},
        headers=auth_headers(),
    )
    assert disabled_apply.status_code == 200
    assert disabled_apply.json()["deletion_allowed"] is False
    assert expired_file.exists()

    settings.learning_artifact_cleanup_enabled = True
    applied = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": False},
        headers=auth_headers("admin@plant.local"),
    )
    assert applied.status_code == 200
    applied_payload = applied.json()
    assert applied_payload["deletion_allowed"] is True
    assert applied_payload["deleted_count"] == 1
    assert applied_payload["deleted_paths"] == ["LJOB-CLEAN/dataset.jsonl"]
    assert not expired_file.exists()
    assert protected_file.exists()
    assert fresh_file.exists()
    jobs = client.get("/api/learning/jobs", headers=auth_headers()).json()
    cleanup_jobs = [job for job in jobs if job["job_type"] == "artifact_cleanup"]
    assert cleanup_jobs
    assert any(job["output_refs"].get("deleted_count") == 1 for job in cleanup_jobs)


def test_learning_artifact_cleanup_api_reports_invalid_and_unsupported_store(monkeypatch, tmp_path):
    invalid_settings = SimpleNamespace(
        learning_artifact_store="filesystem",
        learning_artifact_dir=tmp_path,
        learning_artifact_retention_days="forever",
        learning_artifact_cleanup_enabled="sometimes",
    )
    monkeypatch.setattr("app.services.artifact_store.get_settings", lambda: invalid_settings)
    invalid = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": True},
        headers=auth_headers(),
    )
    assert invalid.status_code == 400
    assert "Invalid learning artifact lifecycle config" in invalid.json()["detail"]

    s3_settings = SimpleNamespace(
        learning_artifact_store="s3",
        learning_artifact_dir=tmp_path,
        learning_artifact_retention_days=7,
        learning_artifact_cleanup_enabled=True,
    )
    monkeypatch.setattr("app.services.artifact_store.get_settings", lambda: s3_settings)
    unsupported = client.post(
        "/api/learning/artifacts/cleanup",
        json={"dry_run": True},
        headers=auth_headers(),
    )
    assert unsupported.status_code == 200
    assert unsupported.json()["store"] == "s3"
    assert unsupported.json()["errors"] == ["Registered artifact cleanup is read-only for non-filesystem stores"]


def test_adapter_deployment_rejects_mismatched_artifact_hash(tmp_path):
    headers = auth_headers()
    artifact_path = tmp_path / "adapter.bin"
    artifact_path.write_text("adapter", encoding="utf-8")
    repository.save_learning_artifact(
        {
            "job_id": "LJOB-ADAPTER",
            "artifact_type": "peft_adapter_manifest",
            "uri": str(artifact_path),
            "content_hash": "correct-hash",
            "metadata": {"storage_backend": "filesystem", "local_path": str(artifact_path)},
        }
    )
    model = client.post(
        "/api/learning/model-versions",
        json={
            "provider": "openai",
            "model_name": "qwen2.5-7b-instruct-lora-mismatch",
            "base_model": "qwen2.5-7b-instruct",
            "adapter_path": str(artifact_path),
            "status": "candidate",
        },
        headers=headers,
    ).json()

    response = client.post(
        f"/api/learning/model-versions/{model['id']}/deploy",
        json={
            "runtime_provider": "manual",
            "served_model_name": model["model_name"],
            "artifact_uri": str(artifact_path),
            "artifact_hash": "wrong-hash",
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert "artifact hash" in response.json()["detail"]


def test_learning_example_can_be_scored_by_judge_endpoint():
    headers = auth_headers()
    refresh_response = client.post("/api/learning/examples/refresh", headers=headers)
    example = refresh_response.json()[0]

    response = client.post(f"/api/learning/examples/{example['id']}/judge", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["judge_score"] >= 0
    assert payload["judge_label"] in {"training_worthy", "review", "reject"}
    assert payload["judge_rationale"]


def test_learning_example_approval_can_be_changed_by_admin():
    headers = auth_headers()
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
    assert payload["model_version"]["id"] == "rul-risk-heuristic-v2"
    assert payload["model_evaluation"]["backtest_window_days"] == 180
    assert payload["model_evaluation"]["sample_count"] > 0
    assert payload["confidence_interval"]["lower_probability"] < payload["failure_probability"]
    assert payload["confidence_interval"]["upper_probability"] > payload["failure_probability"]
    assert payload["prediction_evidence"]
    assert payload["degradation_trend"]
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
    assert "Recurring high vibration on drive end" in response.text


def test_structured_maintenance_insights_include_alerts_decisions_and_logs():
    response = client.get("/api/reports/maintenance-insights", headers=auth_headers("maintenance@plant.local"))

    assert response.status_code == 200
    payload = response.json()
    assert payload["assets_reviewed"] == 5
    assert payload["structured_reports"]
    assert payload["abnormal_alert_reports"]
    assert payload["maintenance_log_entries"]
    assert {summary["audience"] for summary in payload["decision_summaries"]} == {"engineer", "supervisor"}
    drive_report = next(item for item in payload["structured_reports"] if item["equipment_id"] == "RM-DRIVE-01")
    assert drive_report["probable_causes"]
    assert drive_report["immediate_actions"]
    assert drive_report["spares_strategy"]


def test_structured_maintenance_insights_can_scope_asset_and_allow_supervisor():
    response = client.get(
        "/api/reports/maintenance-insights?equipment_id=BF-BLOWER-02",
        headers=auth_headers("supervisor@plant.local"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["scope_equipment_id"] == "BF-BLOWER-02"
    assert payload["assets_reviewed"] == 1
    assert [item["equipment_id"] for item in payload["structured_reports"]] == ["BF-BLOWER-02"]


def test_structured_maintenance_insight_sections_load_independently():
    headers = auth_headers("planner@plant.local")
    routes = {
        "summary": "/api/reports/maintenance-insights/summary?equipment_id=RM-DRIVE-01",
        "structured": "/api/reports/maintenance-insights/structured-reports?equipment_id=RM-DRIVE-01",
        "alerts": "/api/reports/maintenance-insights/abnormal-alerts?equipment_id=RM-DRIVE-01",
        "decisions": "/api/reports/maintenance-insights/decision-summaries?equipment_id=RM-DRIVE-01",
        "logs": "/api/reports/maintenance-insights/maintenance-log-entries?equipment_id=RM-DRIVE-01",
    }

    responses = {name: client.get(route, headers=headers) for name, route in routes.items()}

    assert all(response.status_code == 200 for response in responses.values())
    assert responses["summary"].json()["structured_report_count"] == 1
    assert [item["equipment_id"] for item in responses["structured"].json()] == ["RM-DRIVE-01"]
    assert all(item["equipment_id"] == "RM-DRIVE-01" for item in responses["alerts"].json())
    assert {item["audience"] for item in responses["decisions"].json()} == {"engineer", "supervisor"}
    assert [item["equipment_id"] for item in responses["logs"].json()] == ["RM-DRIVE-01"]


def test_structured_maintenance_insights_markdown_export():
    response = client.get("/api/reports/maintenance-insights/markdown", headers=auth_headers("planner@plant.local"))

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# Structured Maintenance Insights" in response.text
    assert "## Abnormal Alert Reports" in response.text
    assert "## Decision Summaries" in response.text


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
