import httpx

from app.services.llm import MockLLMClient, OpenAIClient, OllamaClient


def test_mock_llm_returns_valid_context():
    context = MockLLMClient().complete_json("diagnose vibration")
    assert context.summary
    assert context.provider == "mock"
    assert context.used_live_provider is False


def test_openai_client_parses_structured_response(monkeypatch):
    def fake_post(*args, **kwargs):
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
    def fake_post(*args, **kwargs):
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
