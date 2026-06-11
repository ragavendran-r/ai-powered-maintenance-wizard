from app.core.config import get_settings
from app.services.llm import LLMClient, build_llm_client


def configured_llm_client() -> LLMClient:
    settings = get_settings()
    return build_llm_client(
        settings.llm_provider,
        settings.openai_api_key,
        settings.ollama_base_url,
        settings.ollama_model,
        settings.openai_model,
        settings.openai_base_url,
        settings.llm_timeout_seconds,
    )
