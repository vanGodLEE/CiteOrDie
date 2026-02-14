"""
Application settings.

All values are loaded from environment variables (or a ``.env`` file)
via *pydantic-settings*.  The singleton :data:`settings` is ready for
import throughout the application.
"""

from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field


class Settings(BaseSettings):
    """Typed, validated application settings backed by env vars / .env."""

    # ------------------------------------------------------------------
    # LLM – any OpenAI-compatible provider
    # ------------------------------------------------------------------

    llm_api_key: str = Field(
        default="",
        description="LLM API key (OpenAI-compatible)",
    )
    llm_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="LLM API base URL (OpenAI-compatible)",
    )

    # ------------------------------------------------------------------
    # Model assignments (one per workflow node / role)
    # ------------------------------------------------------------------

    structurizer_llm_name: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("STRUCTURIZER_LLM_NAME", "STRUCTURIZER_MODEL"),
        description="Model for PageIndex document structuring",
    )
    text_filler_llm_name: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("TEXT_FILLER_LLM_NAME", "TEXT_FILLER_MODEL"),
        description="Model for original-text filling",
    )
    summarizer_llm_name: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("SUMMARIZER_LLM_NAME", "SUMMARY_MODEL"),
        description="Model for summary generation",
    )
    extractor_llm_name: str = Field(
        default="gpt-4o",
        validation_alias=AliasChoices("EXTRACTOR_LLM_NAME", "EXTRACTOR_MODEL"),
        description="Model for clause extraction",
    )

    # Comma-separated fallback model list for 429 rate-limit retry.
    # Example: gpt-4o,gpt-4o-mini,gpt-3.5-turbo
    fallback_llm_names: str = Field(
        default="",
        validation_alias=AliasChoices("FALLBACK_LLM_NAMES", "FALLBACK_MODELS"),
        description="Fallback models on 429 (comma-separated, priority order)",
    )

    img_handler_model: str = Field(
        default="openai:gpt-4o",
        validation_alias=AliasChoices("IMG_HANDLER_MODEL", "VISION_MODEL"),
        description="Vision model for image/table analysis (format: provider:model)",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    app_env: str = Field(
        default="development",
        description="Environment: development / production",
    )
    log_level: str = Field(
        default="INFO",
        description="Log level: DEBUG / INFO / WARNING / ERROR",
    )
    temp_dir: str = Field(
        default="./temp",
        description="Temporary file directory",
    )

    # ------------------------------------------------------------------
    # FastAPI
    # ------------------------------------------------------------------

    api_host: str = Field(
        default="0.0.0.0",
        description="API server bind address",
    )
    api_port: int = Field(
        default=8000,
        description="API server port",
    )
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8080"],
        description="Allowed CORS origins",
    )

    # ------------------------------------------------------------------
    # MinIO (S3-compatible object storage)
    # ------------------------------------------------------------------

    minio_endpoint: str = Field(
        default="localhost:9000",
        description="MinIO endpoint (S3 API port, typically 9000)",
    )
    minio_access_key: str = Field(
        default="minioadmin",
        description="MinIO access key",
    )
    minio_secret_key: str = Field(
        default="minioadmin",
        description="MinIO secret key",
    )
    minio_bucket: str = Field(
        default="document-pdf",
        description="MinIO bucket name",
    )
    minio_secure: bool = Field(
        default=False,
        description="Use HTTPS for MinIO connections",
    )

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    max_parallel_workers: int = Field(
        default=5,
        description="Max parallel workers (LangGraph concurrency)",
    )
    pipeline_thread_pool_size: int = Field(
        default=3,
        description="Thread pool size for concurrent analysis pipelines",
    )
    vision_max_workers: int = Field(
        default=4,
        description="Max parallel threads for vision model image extraction",
    )
    confidence_threshold: float = Field(
        default=0.5,
        description="Minimum confidence for clause extraction",
    )
    similarity_threshold: float = Field(
        default=0.85,
        description="Similarity threshold for deduplication",
    )

    # ------------------------------------------------------------------
    # Pydantic v2 meta
    # ------------------------------------------------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global singleton – import as ``from app.domain.settings import settings``
settings = Settings()
