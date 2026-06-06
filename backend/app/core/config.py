from functools import lru_cache
from pathlib import Path
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Maintenance Wizard"
    llm_provider: str = Field(default="mock", alias="LLM_PROVIDER")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    llm_timeout_seconds: float = Field(default=20.0, alias="LLM_TIMEOUT_SECONDS")
    data_dir: Path = Field(
        default=Path(__file__).resolve().parents[3] / "assets" / "sample_data",
        alias="DATA_DIR",
    )
    database_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "maintenance_wizard.db",
        alias="DATABASE_PATH",
    )

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
