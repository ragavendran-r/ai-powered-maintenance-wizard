from dataclasses import asdict, dataclass
from typing import Any, Optional

from app.core.config import Settings, get_settings
from app.data import repository
from app.services.llm import LLMClient, build_llm_client


@dataclass(frozen=True)
class LLMServingConfig:
    provider: str
    openai_model: str
    ollama_model: str
    openai_base_url: str
    ollama_base_url: str
    source: str
    active_model_version_id: Optional[str] = None
    adapter_path: Optional[str] = None
    base_model: Optional[str] = None
    status: str = "env"
    warning: Optional[str] = None

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


def configured_llm_client() -> LLMClient:
    settings = get_settings()
    serving = active_llm_serving_config(settings)
    return build_llm_client(
        serving.provider,
        settings.openai_api_key,
        serving.ollama_base_url,
        serving.ollama_model,
        serving.openai_model,
        serving.openai_base_url,
        settings.llm_timeout_seconds,
        settings.llm_structured_max_tokens,
        settings.llm_text_max_tokens,
        settings.llm_stream_timeout_seconds,
    )


def active_llm_serving_config(settings: Optional[Settings] = None) -> LLMServingConfig:
    settings = settings or get_settings()
    default = LLMServingConfig(
        provider=settings.llm_provider,
        openai_model=settings.openai_model,
        ollama_model=settings.ollama_model,
        openai_base_url=settings.openai_base_url,
        ollama_base_url=settings.ollama_base_url,
        source="environment",
        status="env",
    )
    if not settings.llm_use_active_learning_model:
        return default
    if settings.llm_provider == "mock":
        return LLMServingConfig(
            **{**default.public_dict(), "warning": "active learning model resolution is disabled for mock provider"}
        )
    model = repository.get_active_learning_model_version()
    if not model:
        return LLMServingConfig(
            **{**default.public_dict(), "warning": "no active learning model version is registered"}
        )
    provider = str(model.get("provider") or settings.llm_provider)
    if provider not in {"openai", "ollama"}:
        return LLMServingConfig(
            **{
                **default.public_dict(),
                "warning": f"active model provider {provider} is not supported for serving",
            }
        )
    openai_model = settings.openai_model
    ollama_model = settings.ollama_model
    if provider == "openai":
        openai_model = str(model.get("model_name") or settings.openai_model)
    if provider == "ollama":
        ollama_model = str(model.get("model_name") or settings.ollama_model)
    return LLMServingConfig(
        provider=provider,
        openai_model=openai_model,
        ollama_model=ollama_model,
        openai_base_url=settings.openai_base_url,
        ollama_base_url=settings.ollama_base_url,
        source="learning_active_model",
        active_model_version_id=str(model["id"]),
        adapter_path=model.get("adapter_path"),
        base_model=model.get("base_model"),
        status=str(model.get("status") or "active"),
    )
