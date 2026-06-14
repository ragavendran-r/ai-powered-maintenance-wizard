import httpx

from app.models.schemas import DocumentIntelligence
from app.services.rca import _draft_with_streaming
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

    draft = _draft_with_streaming(FakeStreamingClient(), {"symptoms": []}, "prompt", 700)

    assert captured["max_tokens"] == 700
    assert captured["timeout_seconds"] is None
    assert "Return JSON only" in captured["system_prompt"]
    assert draft.used_live_provider is True
    assert draft.provider == "openai"
    assert draft.probable_cause == "Bearing looseness"
    assert draft.hypotheses[0].cause == "Bearing looseness"


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
