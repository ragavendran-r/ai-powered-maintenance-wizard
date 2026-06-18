from types import SimpleNamespace

import httpx

from app.models.schemas import DocumentIntelligence, PmPlanDraftRequest, RcaMorpheusDraftRequest, UserPublic
from app.services import pm_plans as pm_plans_service
from app.services import rca as rca_service
from app.services.rca import _draft_with_streaming, stream_draft_case
from app.services.llm import LLMContext, LLMTextResponse, MockLLMClient, OpenAIClient, OllamaClient


def test_mock_llm_returns_valid_context():
    context = MockLLMClient().complete_json("diagnose vibration")
    assert context.summary
    assert context.provider == "mock"
    assert context.used_live_provider is False


def test_openai_client_parses_structured_response(monkeypatch):
    captured_request = {}

    def fake_post(*args, **kwargs):
        captured_request.update(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"summary":"Inspect bearing and alignment.",'
                                '"probable_root_causes":["Bearing wear"],'
                                '"immediate_actions":["Reduce load"],'
                                '"planned_actions":["Schedule bearing replacement"],'
                                '"confidence_adjustment":0.1}'
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    context = OpenAIClient("test-key", "test-model", "https://example.test/v1", 2.0).complete_json("prompt")

    assert context.used_live_provider is True
    assert context.provider == "openai"
    assert context.probable_root_causes == ["Bearing wear"]
    assert context.immediate_actions == ["Reduce load"]
    assert context.confidence_adjustment == 0.1
    assert captured_request["max_tokens"] == 300
    assert captured_request["response_format"]["type"] == "json_schema"
    assert captured_request["response_format"]["json_schema"]["name"] == "LLMContext"
    assert "summary" in captured_request["response_format"]["json_schema"]["schema"]["properties"]


def test_openai_structured_completion_supports_call_overrides(monkeypatch):
    captured_request = {}
    captured_timeout = {}

    def fake_post(*args, **kwargs):
        captured_request.update(kwargs["json"])
        captured_timeout["timeout"] = kwargs["timeout"]
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            json={"choices": [{"message": {"content": '{"summary":"RCA drafted."}'}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    context = OpenAIClient("test-key", "test-model", "https://example.test/v1", 2.0).complete_model(
        "prompt",
        LLMContext,
        "Return JSON only.",
        lambda provider, reason: LLMContext(summary=reason, provider=provider),
        max_tokens=700,
        timeout_seconds=45,
        response_format="json_object",
    )

    assert context.used_live_provider is True
    assert context.provider == "openai"
    assert captured_request["max_tokens"] == 700
    assert captured_request["response_format"] == {"type": "json_object"}
    assert captured_timeout["timeout"] == 45


def test_rca_streaming_draft_accumulates_and_validates_json():
    captured = {}

    class FakeStreamingClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            captured["max_tokens"] = max_tokens
            captured["timeout_seconds"] = timeout_seconds
            yield LLMTextResponse(
                content='{"summary":"Streamed RCA draft.", "probable_cause":"Bearing looseness", ',
                used_live_provider=True,
                provider="openai",
            )
            yield LLMTextResponse(
                content='"confidence":0.72, "hypotheses":[{"cause":"Bearing looseness","confidence":0.72}], "missing_checks":["Verify alignment"]}',
                used_live_provider=True,
                provider="openai",
            )

    draft = _draft_with_streaming(FakeStreamingClient(), {"symptoms": []}, "prompt", 700, 45)

    assert captured["max_tokens"] == 700
    assert captured["timeout_seconds"] == 45
    assert "Return JSON only" in captured["system_prompt"]
    assert draft.used_live_provider is True
    assert draft.provider == "openai"
    assert draft.probable_cause == "Bearing looseness"
    assert draft.hypotheses[0].cause == "Bearing looseness"


def test_rca_streaming_draft_emits_progress_before_context_resolution(monkeypatch):
    class FakeStreamingClient:
        @property
        def provider_name(self):
            return "openai"

    def fail_context_resolution(request):
        raise AssertionError("context resolution should happen after initial stream feedback")

    monkeypatch.setattr(rca_service, "configured_llm_client", lambda: FakeStreamingClient())
    monkeypatch.setattr(
        rca_service,
        "get_settings",
        lambda: SimpleNamespace(
            llm_rca_draft_stream_enabled=True,
            llm_rca_draft_max_tokens=700,
            llm_rca_draft_timeout_seconds=45,
        ),
    )
    monkeypatch.setattr(rca_service, "_resolve_context", fail_context_resolution)

    events = stream_draft_case(
        RcaMorpheusDraftRequest(case_id="RCA-9001"),
        UserPublic(
            id="user-1",
            email="reliability@plant.local",
            display_name="Reliability Engineer",
            role="reliability_engineer",
        ),
    )

    assert next(events)["type"] == "meta"
    progress = next(events)
    assert progress["type"] == "token"
    assert "collecting RCA context" in progress["content"]


def test_rca_streaming_draft_uses_scoped_timeout(monkeypatch):
    captured = {}

    class FakeStreamingClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            captured["max_tokens"] = max_tokens
            captured["timeout_seconds"] = timeout_seconds
            yield LLMTextResponse(content="## Summary\nLive draft", used_live_provider=True, provider="openai")

    monkeypatch.setattr(rca_service, "configured_llm_client", lambda: FakeStreamingClient())
    monkeypatch.setattr(
        rca_service,
        "get_settings",
        lambda: SimpleNamespace(
            llm_rca_draft_stream_enabled=True,
            llm_rca_draft_max_tokens=700,
            llm_rca_draft_timeout_seconds=45,
        ),
    )
    monkeypatch.setattr(rca_service, "_resolve_context", lambda request: {"symptoms": []})
    monkeypatch.setattr(rca_service, "_build_prompt", lambda context: "prompt")

    events = stream_draft_case(
        RcaMorpheusDraftRequest(case_id="RCA-9001"),
        UserPublic(
            id="user-1",
            email="reliability@plant.local",
            display_name="Reliability Engineer",
            role="reliability_engineer",
        ),
    )
    next(events)
    next(events)
    assert next(events)["type"] == "token"

    assert captured["max_tokens"] == 700
    assert captured["timeout_seconds"] == 45


def test_pm_plan_streaming_draft_emits_status_before_context_resolution(monkeypatch):
    class FakeStreamingClient:
        @property
        def provider_name(self):
            return "openai"

    def fail_context_resolution(request):
        raise AssertionError("context resolution should happen after initial stream feedback")

    monkeypatch.setattr(pm_plans_service, "configured_llm_client", lambda: FakeStreamingClient())
    monkeypatch.setattr(pm_plans_service, "_resolve_pm_context", fail_context_resolution)

    events = pm_plans_service.stream_draft_plan(
        PmPlanDraftRequest(equipment_id="RM-DRIVE-01"),
        UserPublic(
            id="user-1",
            email="planner@plant.local",
            display_name="Planner",
            role="planner",
        ),
    )

    assert next(events)["type"] == "meta"
    progress = next(events)
    assert progress["type"] == "status"
    assert "Preparing live PM draft context" in progress["message"]


def test_pm_plan_streaming_draft_rejects_non_live_provider_without_static_plan(monkeypatch):
    class FakeStreamingClient:
        @property
        def provider_name(self):
            return "mock"

    def fail_context_resolution(request):
        raise AssertionError("mock provider should not resolve context or create a deterministic PM plan")

    monkeypatch.setattr(pm_plans_service, "configured_llm_client", lambda: FakeStreamingClient())
    monkeypatch.setattr(pm_plans_service, "_resolve_pm_context", fail_context_resolution)

    events = pm_plans_service.stream_draft_plan(
        PmPlanDraftRequest(equipment_id="RM-DRIVE-01"),
        UserPublic(
            id="user-1",
            email="planner@plant.local",
            display_name="Planner",
            role="planner",
        ),
    )

    assert next(events)["type"] == "meta"
    assert next(events)["type"] == "status"
    error = next(events)
    assert error["type"] == "error"
    assert "requires a live LLM provider" in error["message"]


def test_pm_plan_streaming_draft_uses_live_markdown_stream(monkeypatch):
    captured = {}

    class FakeStreamingClient:
        @property
        def provider_name(self):
            return "openai"

        def stream_text(self, prompt, system_prompt, fallback_factory, max_tokens=600, timeout_seconds=None):
            if "Write concise technician-ready numbered steps" in prompt:
                captured["smith_prompt"] = prompt
                captured["smith_system_prompt"] = system_prompt
                yield LLMTextResponse(content="### Smith Execution Steps\n", used_live_provider=True, provider="openai")
                yield LLMTextResponse(content="1. Inspect bearing condition safely.\n", used_live_provider=True, provider="openai")
                return
            captured["prompt"] = prompt
            captured["system_prompt"] = system_prompt
            captured["max_tokens"] = max_tokens
            yield LLMTextResponse(content="### PM Plan\n", used_live_provider=True, provider="openai")
            yield LLMTextResponse(content="Main drive proactive PM plan\n", used_live_provider=True, provider="openai")

    def fake_draft_from_stream(context, answer, provider, used_live_provider):
        captured["answer"] = answer
        captured["provider"] = provider
        captured["used_live_provider"] = used_live_provider
        return pm_plans_service._PmPlanDraft(
            title="Main drive proactive PM plan",
            trigger=pm_plans_service._PmTriggerDraft(description="Inspect drive vibration weekly."),
            thresholds=["drive_end_vibration >= 7.1 mm/s"],
            tasks=[pm_plans_service._PmTaskDraft(task="Inspect bearing condition and coupling alignment.")],
        )

    def fake_save_base(context, request, draft):
        captured["stored_title"] = draft.title
        return {
            "id": "PM-9001",
            "equipment_id": request.equipment_id,
            "template_id": None,
            "title": draft.title,
            "cadence_days": 30,
            "next_due_date": "2026-06-25T00:00:00+00:00",
            "trigger": draft.trigger.model_dump(mode="json"),
            "thresholds": draft.thresholds,
            "tasks": [
                {
                    "id": "TASK-1",
                    "sequence": 1,
                    "task": "Inspect bearing condition and coupling alignment.",
                    "owner_role": "Maintenance Technician",
                    "estimated_minutes": 30,
                    "safety_note": None,
                }
            ],
            "smith_steps": [],
            "spares_strategy": [],
            "evidence": [],
            "adjustment_notes": [],
            "status": "draft",
            "converted_work_order_id": None,
            "source": "llm",
            "generated_by": "morpheus",
            "used_live_provider": True,
            "provider": "openai",
            "created_at": "2026-06-18T00:00:00+00:00",
            "updated_at": "2026-06-18T00:00:00+00:00",
        }

    def fake_finalize_response(context, request, current_user, saved, smith_steps):
        captured["smith_steps"] = smith_steps
        return SimpleNamespace(
            model_dump=lambda mode="json": {
                    "plan": {
                        "id": "PM-9001",
                        "equipment_id": request.equipment_id,
                        "title": saved["title"],
                        "used_live_provider": True,
                        "provider": "openai",
                    },
                "templates": [],
                "message": "stored",
            }
        )

    monkeypatch.setattr(pm_plans_service, "configured_llm_client", lambda: FakeStreamingClient())
    monkeypatch.setattr(
        pm_plans_service,
        "_resolve_pm_context",
        lambda request: {
            "prompt": "pm prompt",
            "equipment": {"id": request.equipment_id, "name": "Main Drive Motor"},
            "evidence": [],
        },
    )
    monkeypatch.setattr(pm_plans_service, "_draft_from_streamed_pm_answer", fake_draft_from_stream)
    monkeypatch.setattr(pm_plans_service, "_save_pm_plan_base", fake_save_base)
    monkeypatch.setattr(pm_plans_service, "_finalize_pm_plan_response", fake_finalize_response)

    events = pm_plans_service.stream_draft_plan(
        PmPlanDraftRequest(equipment_id="RM-DRIVE-01"),
        UserPublic(
            id="user-1",
            email="planner@plant.local",
            display_name="Planner",
            role="planner",
        ),
    )

    assert next(events)["type"] == "meta"
    assert next(events)["type"] == "status"
    assert next(events)["type"] == "status"
    first_delta = next(events)
    assert first_delta["type"] == "token"
    assert first_delta["content"] == "### PM Plan"
    second_delta = next(events)
    assert second_delta["content"] == "\nMain drive proactive PM plan"
    assert next(events)["type"] == "status"
    assert next(events)["content"] == "### Smith Execution Steps\n"
    assert next(events)["content"] == "1. Inspect bearing condition safely.\n"
    done = next(events)
    assert done["type"] == "done"
    assert captured["prompt"] == "pm prompt"
    assert "Stream the final PM plan" in captured["system_prompt"]
    assert captured["max_tokens"] == 1200
    assert captured["answer"] == "### PM Plan\nMain drive proactive PM plan"
    assert captured["provider"] == "openai"
    assert captured["used_live_provider"] is True
    assert captured["stored_title"] == "Main drive proactive PM plan"
    assert captured["smith_steps"] == ["1. Inspect bearing condition safely."]


def test_pm_plan_context_uses_non_llm_retrieval_path(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        pm_plans_service.repository,
        "get_equipment",
        lambda equipment_id: {
            "id": equipment_id,
            "name": "Main Drive Motor",
            "area": "Hot Rolling Mill",
        },
    )
    monkeypatch.setattr(
        pm_plans_service,
        "_select_template",
        lambda equipment_id, template_id=None: {
            "title": "Drive inspection PM",
            "description": "Inspect drive vibration and bearing temperature.",
            "task_list": ["Inspect bearing housing"],
            "thresholds": ["drive_end_vibration >= 7.1 mm/s"],
            "cadence_days": 30,
        },
    )
    monkeypatch.setattr(
        pm_plans_service,
        "prediction_features",
        lambda equipment_id: SimpleNamespace(
            risk_level="high",
            failure_probability=0.82,
            remaining_useful_life_days=14,
            drivers=["drive_end_vibration >= 7.1 mm/s"],
        ),
    )

    def fake_retrieve_evidence(query, equipment_id, limit=6, use_reranker=True):
        captured["limit"] = limit
        captured["use_reranker"] = use_reranker
        return []

    monkeypatch.setattr(pm_plans_service, "retrieve_evidence", fake_retrieve_evidence)
    monkeypatch.setattr(pm_plans_service.repository, "list_feedback", lambda equipment_id: [])
    monkeypatch.setattr(pm_plans_service.repository, "list_maintenance_events", lambda equipment_id: [])
    monkeypatch.setattr(pm_plans_service.repository, "list_spares", lambda equipment_id: [])

    context = pm_plans_service._resolve_pm_context(PmPlanDraftRequest(equipment_id="RM-DRIVE-01"))

    assert captured == {"limit": 6, "use_reranker": False}
    assert context["prediction"].risk_level == "high"
    assert "Prediction: risk=high" in context["prompt"]


def test_openai_text_completion_respects_local_token_cap(monkeypatch):
    captured_request = {}

    def fake_post(*args, **kwargs):
        captured_request.update(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            json={"choices": [{"message": {"content": "Use lockout/tagout and inspect the actuator."}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    context = OpenAIClient(
        "test-key",
        "test-model",
        "https://example.test/v1",
        2.0,
        structured_max_tokens=300,
        text_max_tokens=250,
    ).complete_text(
        "prompt",
        "system",
        lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
        max_tokens=900,
    )

    assert context.used_live_provider is True
    assert context.provider == "openai"
    assert captured_request["max_tokens"] == 250


def test_openai_text_stream_uses_sse_and_token_cap(monkeypatch):
    captured_request = {}
    captured_timeout = {}

    class FakeStreamResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Use lockout/tagout "}}]}'
            yield 'data: {"choices":[{"delta":{"content":"before inspection."}}]}'
            yield "data: [DONE]"

    class FakeStream:
        def __enter__(self):
            return FakeStreamResponse()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_stream(*args, **kwargs):
        captured_request.update(kwargs["json"])
        captured_timeout["timeout"] = kwargs["timeout"]
        return FakeStream()

    monkeypatch.setattr(httpx, "stream", fake_stream)
    chunks = list(
        OpenAIClient(
            "test-key",
            "test-model",
            "https://example.test/v1",
            2.0,
            structured_max_tokens=300,
            text_max_tokens=250,
            stream_timeout_seconds=45,
        ).stream_text(
            "prompt",
            "system",
            lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
            max_tokens=900,
        )
    )

    assert captured_request["stream"] is True
    assert captured_request["max_tokens"] == 250
    assert captured_timeout["timeout"].read == 45
    assert captured_timeout["timeout"].connect == 2.0
    assert [chunk.content for chunk in chunks] == ["Use lockout/tagout ", "before inspection."]
    assert all(chunk.used_live_provider for chunk in chunks)


def test_openai_text_stream_allows_per_call_timeout_override(monkeypatch):
    captured_timeout = {}

    class FakeStreamResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Short bounded response."}}]}'
            yield "data: [DONE]"

    class FakeStream:
        def __enter__(self):
            return FakeStreamResponse()

        def __exit__(self, exc_type, exc, traceback):
            return False

    def fake_stream(*args, **kwargs):
        captured_timeout["timeout"] = kwargs["timeout"]
        return FakeStream()

    monkeypatch.setattr(httpx, "stream", fake_stream)
    chunks = list(
        OpenAIClient(
            "test-key",
            "test-model",
            "https://example.test/v1",
            15.0,
            structured_max_tokens=300,
            text_max_tokens=250,
            stream_timeout_seconds=60.0,
        ).stream_text(
            "prompt",
            "system",
            lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
            max_tokens=250,
            timeout_seconds=15.0,
        )
    )

    assert captured_timeout["timeout"].read == 15.0
    assert captured_timeout["timeout"].connect == 15.0
    assert [chunk.content for chunk in chunks] == ["Short bounded response."]


def test_openai_text_stream_stops_repeated_lines(monkeypatch):
    class FakeStreamResponse:
        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"### Monitoring Thresholds\\n"}}]}'
            for _ in range(20):
                yield 'data: {"choices":[{"delta":{"content":"Hydraulic oil temperature:\\n"}}]}'
            yield "data: [DONE]"

    class FakeStream:
        def __enter__(self):
            return FakeStreamResponse()

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(httpx, "stream", lambda *args, **kwargs: FakeStream())
    chunks = list(
        OpenAIClient(
            "test-key",
            "test-model",
            "https://example.test/v1",
            2.0,
            structured_max_tokens=300,
            text_max_tokens=250,
            stream_timeout_seconds=45,
        ).stream_text(
            "prompt",
            "system",
            lambda provider, reason: LLMTextResponse(content=reason, provider=provider),
            max_tokens=900,
        )
    )

    assert "".join(chunk.content for chunk in chunks).count("Hydraulic oil temperature:") == 2
    assert all(chunk.used_live_provider for chunk in chunks)


def test_openai_client_parses_generic_structured_response(monkeypatch):
    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            json={
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"document_id":"DOC-1",'
                                '"summary":"Bearing inspection SOP.",'
                                '"asset_ids":["RM-DRIVE-01"],'
                                '"components":["bearing"],'
                                '"failure_modes":["wear"],'
                                '"symptoms":["vibration"],'
                                '"safety_constraints":["lockout"],'
                                '"spares":["bearing"],'
                                '"thresholds":["above 7 mm/s"]}'
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    context = OpenAIClient("test-key", "test-model", "https://example.test/v1", 2.0).complete_model(
        "prompt",
        DocumentIntelligence,
        "Return document intelligence.",
        lambda provider, reason: DocumentIntelligence(document_id="fallback", summary=reason),
    )

    assert context.used_live_provider is True
    assert context.provider == "openai"
    assert context.document_id == "DOC-1"
    assert context.components == ["bearing"]


def test_openai_client_falls_back_on_invalid_json(monkeypatch):
    def fake_post(*args, **kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("POST", "https://example.test/v1/chat/completions"),
            json={"choices": [{"message": {"content": "not-json"}}]},
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    context = OpenAIClient("test-key", "test-model", "https://example.test/v1", 2.0).complete_json("prompt")

    assert context.used_live_provider is False
    assert context.provider == "openai"
    assert "OpenAI call failed" in context.summary


def test_ollama_client_parses_structured_response(monkeypatch):
    captured_request = {}

    def fake_post(*args, **kwargs):
        captured_request.update(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", "http://localhost:11434/api/chat"),
            json={
                "message": {
                    "content": (
                        '{"summary":"Check guide vane actuator.",'
                        '"probable_root_causes":["Sticky actuator"],'
                        '"immediate_actions":["Inspect actuator linkage"],'
                        '"planned_actions":["Calibrate actuator"],'
                        '"confidence_adjustment":0.05}'
                    )
                }
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    context = OllamaClient("http://localhost:11434", "llama3.1", 2.0).complete_json("prompt")

    assert context.used_live_provider is True
    assert context.provider == "ollama"
    assert context.probable_root_causes == ["Sticky actuator"]
    assert context.planned_actions == ["Calibrate actuator"]
    assert captured_request["options"]["num_predict"] == 300
