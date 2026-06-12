from abc import ABC, abstractmethod
import json
from collections.abc import Iterator
from typing import Callable, Optional, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError


T = TypeVar("T", bound=BaseModel)


class LLMContext(BaseModel):
    summary: str
    probable_root_causes: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    planned_actions: list[str] = Field(default_factory=list)
    confidence_adjustment: float = Field(default=0.0, ge=-0.2, le=0.2)
    used_live_provider: bool = False
    provider: str = "mock"


class LLMTextResponse(BaseModel):
    content: str
    used_live_provider: bool = False
    provider: str = "mock"


class LLMProviderError(RuntimeError):
    pass


class LLMClient(ABC):
    def complete_json(self, prompt: str) -> LLMContext:
        return self.complete_model(
            prompt,
            LLMContext,
            _system_prompt(),
            lambda provider, reason: _fallback_context(provider, reason),
        )

    def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> LLMTextResponse:
        return fallback_factory(self.provider_name, "text completion is not supported by this provider")

    def stream_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> Iterator[LLMTextResponse]:
        yield self.complete_text(prompt, system_prompt, fallback_factory, max_tokens=max_tokens)

    @property
    def provider_name(self) -> str:
        return "mock"

    @abstractmethod
    def complete_model(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        fallback_factory: Callable[[str, str], T],
    ) -> T:
        raise NotImplementedError


class MockLLMClient(LLMClient):
    def __init__(self, provider: str = "mock", reason: str = "no live LLM provider is configured"):
        self.provider = provider
        self.reason = reason

    @property
    def provider_name(self) -> str:
        return self.provider

    def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> LLMTextResponse:
        return fallback_factory(self.provider, self.reason)

    def complete_model(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        fallback_factory: Callable[[str, str], T],
    ) -> T:
        return fallback_factory(self.provider, self.reason)


class OpenAIClient(LLMClient):
    def __init__(
        self,
        api_key: Optional[str],
        model: str,
        base_url: str,
        timeout_seconds: float,
        structured_max_tokens: int = 300,
        text_max_tokens: int = 600,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.structured_max_tokens = structured_max_tokens
        self.text_max_tokens = text_max_tokens

    @property
    def provider_name(self) -> str:
        return "openai"

    def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> LLMTextResponse:
        if not self.api_key:
            return fallback_factory("openai", "OPENAI_API_KEY is not set")
        token_budget = min(max_tokens, self.text_max_tokens)
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": token_budget,
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return LLMTextResponse(content=content, used_live_provider=True, provider="openai")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            return fallback_factory("openai", f"OpenAI text call failed: {exc}")

    def stream_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> Iterator[LLMTextResponse]:
        if not self.api_key:
            yield fallback_factory("openai", "OPENAI_API_KEY is not set")
            return
        token_budget = min(max_tokens, self.text_max_tokens)
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": token_budget,
                    "stream": True,
                },
                timeout=self.timeout_seconds,
            ) as response:
                response.raise_for_status()
                yielded = False
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if not data or data == "[DONE]":
                        continue
                    payload = json.loads(data)
                    delta = payload["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        yielded = True
                        yield LLMTextResponse(content=delta, used_live_provider=True, provider="openai")
                if not yielded:
                    yield fallback_factory("openai", "OpenAI stream returned no content")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            yield fallback_factory("openai", f"OpenAI stream failed: {exc}")

    def complete_model(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        fallback_factory: Callable[[str, str], T],
    ) -> T:
        if not self.api_key:
            return fallback_factory("openai", "OPENAI_API_KEY is not set")
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": self.structured_max_tokens,
                    "response_format": _json_schema_response_format(response_model),
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return _parse_model(content, response_model, provider="openai")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            return fallback_factory("openai", f"OpenAI call failed or returned invalid JSON: {exc}")


class OllamaClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        structured_max_tokens: int = 300,
        text_max_tokens: int = 600,
    ):
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.structured_max_tokens = structured_max_tokens
        self.text_max_tokens = text_max_tokens

    @property
    def provider_name(self) -> str:
        return "ollama"

    def complete_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> LLMTextResponse:
        token_budget = min(max_tokens, self.text_max_tokens)
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "options": {"num_predict": token_budget},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return LLMTextResponse(content=content, used_live_provider=True, provider="ollama")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            return fallback_factory("ollama", f"Ollama text call failed: {exc}")

    def stream_text(
        self,
        prompt: str,
        system_prompt: str,
        fallback_factory: Callable[[str, str], LLMTextResponse],
        max_tokens: int = 600,
    ) -> Iterator[LLMTextResponse]:
        token_budget = min(max_tokens, self.text_max_tokens)
        try:
            with httpx.stream(
                "POST",
                f"{self.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": True,
                    "options": {"num_predict": token_budget},
                },
                timeout=self.timeout_seconds,
            ) as response:
                response.raise_for_status()
                yielded = False
                for line in response.iter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    delta = payload.get("message", {}).get("content", "")
                    if delta:
                        yielded = True
                        yield LLMTextResponse(content=delta, used_live_provider=True, provider="ollama")
                    if payload.get("done"):
                        break
                if not yielded:
                    yield fallback_factory("ollama", "Ollama stream returned no content")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            yield fallback_factory("ollama", f"Ollama stream failed: {exc}")

    def complete_model(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        fallback_factory: Callable[[str, str], T],
    ) -> T:
        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    "stream": False,
                    "format": "json",
                    "options": {"num_predict": self.structured_max_tokens},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            return _parse_model(content, response_model, provider="ollama")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, ValidationError) as exc:
            return fallback_factory("ollama", f"Ollama call failed or returned invalid JSON: {exc}")


def build_llm_client(
    provider: str,
    openai_api_key: Optional[str],
    ollama_base_url: str,
    ollama_model: str,
    openai_model: str = "gpt-4o-mini",
    openai_base_url: str = "https://api.openai.com/v1",
    timeout_seconds: float = 20.0,
    structured_max_tokens: int = 300,
    text_max_tokens: int = 600,
) -> LLMClient:
    if provider == "openai":
        return OpenAIClient(
            openai_api_key,
            openai_model,
            openai_base_url,
            timeout_seconds,
            structured_max_tokens,
            text_max_tokens,
        )
    if provider == "ollama":
        return OllamaClient(ollama_base_url, ollama_model, timeout_seconds, structured_max_tokens, text_max_tokens)
    return MockLLMClient(provider=provider)


def _system_prompt() -> str:
    return (
        "You are an industrial maintenance reasoning assistant for steel plant equipment. "
        "Return only valid JSON with keys summary, probable_root_causes, immediate_actions, "
        "planned_actions, and confidence_adjustment. Keep actions practical, safe, and traceable "
        "to the provided evidence. confidence_adjustment must be between -0.2 and 0.2."
    )


def _json_schema_response_format(response_model: type[BaseModel]) -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": response_model.__name__,
            "schema": response_model.model_json_schema(),
        },
    }


def _fallback_context(provider: str, reason: str) -> LLMContext:
    return LLMContext(
        summary=f"Deterministic maintenance reasoning was used because {reason}.",
        confidence_adjustment=0.0,
        used_live_provider=False,
        provider=provider,
    )


def _parse_model(content: str, response_model: type[T], provider: str) -> T:
    payload = json.loads(content)
    context = response_model.model_validate(payload)
    update_payload = {}
    if "used_live_provider" in response_model.model_fields:
        update_payload["used_live_provider"] = True
    if "provider" in response_model.model_fields:
        update_payload["provider"] = provider
    return context.model_copy(update=update_payload)
