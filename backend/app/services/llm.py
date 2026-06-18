from abc import ABC, abstractmethod
import json
import re
from collections.abc import Iterator
from typing import Any, Callable, Optional, TypeVar

import httpx
from pydantic import BaseModel, Field, ValidationError


T = TypeVar("T", bound=BaseModel)

STREAM_REPEAT_LINE_LIMIT = 3
STREAM_REPEAT_PHRASE_LIMIT = 12
STREAM_REPEAT_PHRASE_MIN_LENGTH = 8


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
    runtime: Optional[str] = None
    runtime_fallback: bool = False
    runtime_fallback_reason: Optional[str] = None
    referenced_records: list[dict[str, Any]] = Field(default_factory=list)


class LLMProviderError(RuntimeError):
    pass


class _StreamRepetitionGuard:
    def __init__(self):
        self._buffer = ""
        self._line_counts: dict[str, int] = {}
        self._phrase_counts: dict[str, int] = {}
        self.triggered = False

    def accept(self, delta: str) -> bool:
        self._buffer += delta
        for line in self._completed_lines():
            normalized = _normalize_repetition_text(line)
            if not normalized:
                continue
            self._line_counts[normalized] = self._line_counts.get(normalized, 0) + 1
            if self._line_counts[normalized] >= STREAM_REPEAT_LINE_LIMIT:
                self.triggered = True
                return False

        phrase = _normalize_repetition_text(self._recent_phrase())
        if len(phrase) >= STREAM_REPEAT_PHRASE_MIN_LENGTH:
            self._phrase_counts[phrase] = self._phrase_counts.get(phrase, 0) + 1
            if self._phrase_counts[phrase] >= STREAM_REPEAT_PHRASE_LIMIT:
                self.triggered = True
                return False
        return True

    def _completed_lines(self) -> list[str]:
        if "\n" not in self._buffer:
            return []
        parts = self._buffer.split("\n")
        self._buffer = parts[-1]
        return parts[:-1]

    def _recent_phrase(self) -> str:
        words = re.findall(r"\w+", self._buffer.lower())
        return " ".join(words[-6:])


def _normalize_repetition_text(value: str) -> str:
    normalized = re.sub(r"\s+", " ", value.strip().lower())
    normalized = normalized.strip("-:*# ")
    return normalized


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
        timeout_seconds: Optional[float] = None,
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
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        response_format: Optional[str] = None,
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
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        response_format: Optional[str] = None,
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
        stream_timeout_seconds: Optional[float] = None,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.structured_max_tokens = structured_max_tokens
        self.text_max_tokens = text_max_tokens
        self.stream_timeout_seconds = stream_timeout_seconds or timeout_seconds

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
        timeout_seconds: Optional[float] = None,
    ) -> Iterator[LLMTextResponse]:
        if not self.api_key:
            yield fallback_factory("openai", "OPENAI_API_KEY is not set")
            return
        token_budget = min(max_tokens, self.text_max_tokens)
        read_timeout = timeout_seconds or self.stream_timeout_seconds
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
                timeout=self._stream_timeout(read_timeout),
            ) as response:
                response.raise_for_status()
                yielded = False
                repetition_guard = _StreamRepetitionGuard()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if not data or data == "[DONE]":
                        continue
                    payload = json.loads(data)
                    delta = payload["choices"][0].get("delta", {}).get("content", "")
                    if delta:
                        if not repetition_guard.accept(delta):
                            break
                        yielded = True
                        yield LLMTextResponse(content=delta, used_live_provider=True, provider="openai")
                if not yielded:
                    yield fallback_factory("openai", "OpenAI stream returned no content")
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            yield fallback_factory("openai", f"OpenAI stream failed: {exc}")

    def _stream_timeout(self, read_timeout: Optional[float] = None) -> httpx.Timeout:
        return httpx.Timeout(
            read_timeout or self.stream_timeout_seconds,
            connect=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=self.timeout_seconds,
        )

    def complete_model(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        fallback_factory: Callable[[str, str], T],
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        response_format: Optional[str] = None,
    ) -> T:
        if not self.api_key:
            return fallback_factory("openai", "OPENAI_API_KEY is not set")
        token_budget = _bounded_token_budget(max_tokens or self.structured_max_tokens)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": token_budget,
        }
        selected_response_format = _openai_response_format(response_model, response_format)
        if selected_response_format:
            payload["response_format"] = selected_response_format
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout_seconds or self.timeout_seconds,
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
        stream_timeout_seconds: Optional[float] = None,
    ):
        self.base_url = base_url
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.structured_max_tokens = structured_max_tokens
        self.text_max_tokens = text_max_tokens
        self.stream_timeout_seconds = stream_timeout_seconds or timeout_seconds

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
        timeout_seconds: Optional[float] = None,
    ) -> Iterator[LLMTextResponse]:
        token_budget = min(max_tokens, self.text_max_tokens)
        read_timeout = timeout_seconds or self.stream_timeout_seconds
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
                timeout=self._stream_timeout(read_timeout),
            ) as response:
                response.raise_for_status()
                yielded = False
                repetition_guard = _StreamRepetitionGuard()
                for line in response.iter_lines():
                    if not line:
                        continue
                    payload = json.loads(line)
                    delta = payload.get("message", {}).get("content", "")
                    if delta:
                        if not repetition_guard.accept(delta):
                            break
                        yielded = True
                        yield LLMTextResponse(content=delta, used_live_provider=True, provider="ollama")
                    if payload.get("done"):
                        break
                if not yielded:
                    yield fallback_factory("ollama", "Ollama stream returned no content")
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            yield fallback_factory("ollama", f"Ollama stream failed: {exc}")

    def _stream_timeout(self, read_timeout: Optional[float] = None) -> httpx.Timeout:
        return httpx.Timeout(
            read_timeout or self.stream_timeout_seconds,
            connect=self.timeout_seconds,
            write=self.timeout_seconds,
            pool=self.timeout_seconds,
        )

    def complete_model(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str,
        fallback_factory: Callable[[str, str], T],
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        response_format: Optional[str] = None,
    ) -> T:
        token_budget = _bounded_token_budget(max_tokens or self.structured_max_tokens)
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
                    "options": {"num_predict": token_budget},
                },
                timeout=timeout_seconds or self.timeout_seconds,
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
    stream_timeout_seconds: Optional[float] = None,
) -> LLMClient:
    if provider == "openai":
        return OpenAIClient(
            openai_api_key,
            openai_model,
            openai_base_url,
            timeout_seconds,
            structured_max_tokens,
            text_max_tokens,
            stream_timeout_seconds,
        )
    if provider == "ollama":
        return OllamaClient(
            ollama_base_url,
            ollama_model,
            timeout_seconds,
            structured_max_tokens,
            text_max_tokens,
            stream_timeout_seconds,
        )
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


def _openai_response_format(response_model: type[BaseModel], response_format: Optional[str]) -> Optional[dict[str, object]]:
    selected = (response_format or "json_schema").strip().lower()
    if selected == "json_object":
        return {"type": "json_object"}
    if selected == "none":
        return None
    return _json_schema_response_format(response_model)


def _bounded_token_budget(max_tokens: int) -> int:
    return max(64, min(max_tokens, 2048))


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
