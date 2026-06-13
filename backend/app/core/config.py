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
    llm_timeout_seconds: float = Field(default=15.0, ge=1.0, alias="LLM_TIMEOUT_SECONDS")
    llm_stream_timeout_seconds: float = Field(default=60.0, ge=1.0, alias="LLM_STREAM_TIMEOUT_SECONDS")
    llm_structured_max_tokens: int = Field(default=300, ge=64, le=2048, alias="LLM_STRUCTURED_MAX_TOKENS")
    llm_text_max_tokens: int = Field(default=600, ge=64, le=2048, alias="LLM_TEXT_MAX_TOKENS")
    llm_use_active_learning_model: bool = Field(default=True, alias="LLM_USE_ACTIVE_LEARNING_MODEL")
    auth_enabled: bool = Field(default=True, alias="AUTH_ENABLED")
    jwt_secret_key: str = Field(
        default="maintenance-wizard-local-dev-secret-change-me",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=480, ge=1, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    auth_seed_demo_users: bool = Field(default=True, alias="AUTH_SEED_DEMO_USERS")
    cors_allow_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="CORS_ALLOW_ORIGINS",
    )
    streaming_enabled: bool = Field(default=False, alias="STREAMING_ENABLED")
    nats_url: str = Field(default="nats://localhost:4222", alias="NATS_URL")
    nats_stream: str = Field(default="MW_IOT", alias="NATS_STREAM")
    nats_consumer: str = Field(default="maintenance-wizard-ingestor", alias="NATS_CONSUMER")
    nats_subject_prefix: str = Field(default="steelplant.iot", alias="NATS_SUBJECT_PREFIX")
    nats_dlq_subject: str = Field(default="steelplant.iot.dlq", alias="NATS_DLQ_SUBJECT")
    nats_auth_token: Optional[str] = Field(default=None, alias="NATS_AUTH_TOKEN")
    nats_credentials_path: Optional[Path] = Field(default=None, alias="NATS_CREDENTIALS_PATH")
    nats_tls_enabled: bool = Field(default=False, alias="NATS_TLS_ENABLED")
    nats_batch_size: int = Field(default=20, ge=1, le=500, alias="NATS_BATCH_SIZE")
    nats_ack_wait_seconds: int = Field(default=30, ge=1, alias="NATS_ACK_WAIT_SECONDS")
    nats_max_deliver: int = Field(default=3, ge=1, alias="NATS_MAX_DELIVER")
    nats_reconnect_time_wait_seconds: float = Field(default=2.0, ge=0.1, alias="NATS_RECONNECT_TIME_WAIT_SECONDS")
    nats_max_reconnect_attempts: int = Field(default=60, ge=0, alias="NATS_MAX_RECONNECT_ATTEMPTS")
    learning_async_enabled: bool = Field(default=True, alias="LEARNING_ASYNC_ENABLED")
    learning_nats_stream: str = Field(default="MW_LEARNING", alias="LEARNING_NATS_STREAM")
    learning_nats_consumer: str = Field(default="maintenance-wizard-learning-worker", alias="LEARNING_NATS_CONSUMER")
    learning_nats_subject_prefix: str = Field(default="maintenance.learning", alias="LEARNING_NATS_SUBJECT_PREFIX")
    learning_nats_dlq_subject: str = Field(default="maintenance.learning.dlq", alias="LEARNING_NATS_DLQ_SUBJECT")
    learning_artifact_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "learning_artifacts",
        alias="LEARNING_ARTIFACT_DIR",
    )
    learning_artifact_store: str = Field(default="filesystem", alias="LEARNING_ARTIFACT_STORE")
    learning_artifact_s3_bucket: Optional[str] = Field(default=None, alias="LEARNING_ARTIFACT_S3_BUCKET")
    learning_artifact_s3_prefix: str = Field(default="maintenance-wizard/learning", alias="LEARNING_ARTIFACT_S3_PREFIX")
    learning_artifact_s3_endpoint_url: Optional[str] = Field(default=None, alias="LEARNING_ARTIFACT_S3_ENDPOINT_URL")
    learning_artifact_s3_region: str = Field(default="us-east-1", alias="LEARNING_ARTIFACT_S3_REGION")
    learning_artifact_retention_days: int = Field(default=0, ge=0, alias="LEARNING_ARTIFACT_RETENTION_DAYS")
    learning_artifact_cleanup_enabled: bool = Field(default=False, alias="LEARNING_ARTIFACT_CLEANUP_ENABLED")
    learning_peft_trainer_command: Optional[str] = Field(default=None, alias="LEARNING_PEFT_TRAINER_COMMAND")
    learning_peft_trainer_timeout_seconds: int = Field(default=900, ge=1, alias="LEARNING_PEFT_TRAINER_TIMEOUT_SECONDS")
    learning_peft_output_dir: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "learning_adapters",
        alias="LEARNING_PEFT_OUTPUT_DIR",
    )
    learning_runtime_deployment_required: bool = Field(default=True, alias="LEARNING_RUNTIME_DEPLOYMENT_REQUIRED")
    learning_runtime_deployer_default: str = Field(default="manual", alias="LEARNING_RUNTIME_DEPLOYER_DEFAULT")
    learning_runtime_deployment_timeout_seconds: float = Field(default=15.0, ge=1.0, alias="LEARNING_RUNTIME_DEPLOYMENT_TIMEOUT_SECONDS")
    rag_vector_store: str = Field(default="qdrant", alias="RAG_VECTOR_STORE")
    rag_qdrant_url: str = Field(default="http://localhost:6333", alias="RAG_QDRANT_URL")
    rag_qdrant_collection: str = Field(default="maintenance_wizard_documents", alias="RAG_QDRANT_COLLECTION")
    rag_qdrant_collection_alias: Optional[str] = Field(default=None, alias="RAG_QDRANT_COLLECTION_ALIAS")
    rag_qdrant_api_key: Optional[str] = Field(default=None, alias="RAG_QDRANT_API_KEY")
    rag_vector_timeout_seconds: float = Field(default=2.0, ge=0.1, alias="RAG_VECTOR_TIMEOUT_SECONDS")
    rag_embedding_provider: str = Field(default="deterministic_hash", alias="RAG_EMBEDDING_PROVIDER")
    rag_embedding_model: str = Field(default="maintenance-hash-v1", alias="RAG_EMBEDDING_MODEL")
    rag_embedding_version: str = Field(default="1", alias="RAG_EMBEDDING_VERSION")
    rag_embedding_dimensions: int = Field(default=64, ge=1, alias="RAG_EMBEDDING_DIMENSIONS")
    rag_embedding_distance: str = Field(default="Cosine", alias="RAG_EMBEDDING_DISTANCE")
    rag_embedding_base_url: Optional[str] = Field(default=None, alias="RAG_EMBEDDING_BASE_URL")
    rag_embedding_api_key: Optional[str] = Field(default=None, alias="RAG_EMBEDDING_API_KEY")
    rag_embedding_timeout_seconds: float = Field(default=10.0, ge=0.1, alias="RAG_EMBEDDING_TIMEOUT_SECONDS")
    rag_embedding_batch_size: int = Field(default=32, ge=1, le=512, alias="RAG_EMBEDDING_BATCH_SIZE")
    data_dir: Path = Field(
        default=Path(__file__).resolve().parents[3] / "assets" / "sample_data",
        alias="DATA_DIR",
    )
    database_path: Path = Field(
        default=Path(__file__).resolve().parents[2] / "data" / "maintenance_wizard.db",
        alias="DATABASE_PATH",
    )

    model_config = {
        "env_file": (
            Path(__file__).resolve().parents[3] / ".env",
            ".env",
        ),
        "extra": "ignore",
    }

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
