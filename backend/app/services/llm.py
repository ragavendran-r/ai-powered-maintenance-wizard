from abc import ABC, abstractmethod
import json
from typing import Any, Optional

import httpx
from pydantic import BaseModel, Field, ValidationError


class LLMContext(BaseModel):
    summary: str
    probable_root_causes: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    planned_actions: list[str] = Field(default_factory=list)
    confidence_adjustment: float = Field(default=0.0, ge=-0.2, le=0.2)
    used_live_provider: bool = False
    provider: str = "mock"


class LLMProviderError(RuntimeError):
    pass


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, prompt: str) -> LLMContext:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    def __init__(self, provider: str = "mock", reason: str = "no live LLM provider is configured"):
        self.provider = provider
        self.reason = reason

    def complete_json(self, prompt: str) -> LLMContext:
        return LLMContext(
            summary=f"Deterministic maintenance reasoning was used because {self.reason}.",
            confidence_adjustment=0.0,
            used_live_provider=False,
            provider=self.provider,
        )


class OpenAIClient(LLMClient):
    def __init__(self, api_key: Optional[str], model: str, base_url: str, timeout_seconds: float):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def complete_json(self, prompt: str) -> LLMContext:
        if not self.api_key:
            return MockLLMClient("openai", "OPENAI_API_KEY is not set").complete_json(prompt)
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_context(content, provider="openai")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            return MockLLMClient("openai", f"OpenAI call failed or returned invalid JSON: {exc}").complete_json(prompt)


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str, timeout_seconds: float):
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds

    def complete_json(self, prompt: str) -> LLMContext:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": _system_prompt()},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return _parse_context(content, provider="ollama")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
            return MockLLMClient("ollama", f"Ollama call failed or returned invalid JSON: {exc}").complete_json(prompt)


def build_llm_client(
    provider: str,
    openai_api_key: Optional[str],
    ollama_base_url: str,
    ollama_model: str,
    openai_model: str = "gpt-4o-mini",
    openai_base_url: str = "https://api.openai.com/v1",
    timeout_seconds: float = 20.0,
) -> LLMClient:
    if provider == "openai":
        return OpenAIClient(openai_api_key, openai_model, openai_base_url, timeout_seconds)
    if provider == "ollama":
        return OllamaClient(ollama_base_url, ollama_model, timeout_seconds)
    return MockLLMClient(provider=provider)


def _system_prompt() -> str:
    return (
        "You are an industrial maintenance reasoning assistant for steel plant equipment. "
        "Return only valid JSON with keys summary, probable_root_causes, immediate_actions, "
        "planned_actions, and confidence_adjustment. Keep actions practical, safe, and traceable "
        "to the provided evidence. confidence_adjustment must be between -0.2 and 0.2."
    )


def _parse_context(content: str, provider: str) -> LLMContext:
    payload = json.loads(content)
    context = LLMContext.model_validate(payload)
    return context.model_copy(update={"used_live_provider": True, "provider": provider})
