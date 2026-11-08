"""Application configuration loaded and validated via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized, strongly-typed configuration for the UniVerse API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Metadata
    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_NAME: str = "UniVerse API"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # CORS Configuration
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Supabase Configuration
    SUPABASE_URL: str = Field(default="")
    SUPABASE_PUBLISHABLE_KEY: str = Field(default="")
    SUPABASE_SERVICE_ROLE_KEY: str = Field(default="")
    SUPABASE_JWT_SECRET: str = Field(default="universe-local-dev-jwt-secret-key-at-least-32-bytes")
    SUPABASE_STORAGE_BUCKET: str = Field(default="documents")

    # Google Gemini Configuration
    GEMINI_API_KEY: str = Field(default="")
    GEMINI_GENERATION_MODEL: str = Field(default="gemini-2.5-flash")
    GEMINI_EMBEDDING_MODEL: str = Field(default="gemini-embedding-001")

    # Vector Store & File Storage Configuration
    CHROMA_PERSIST_DIR: str = Field(default="./data/chroma")
    CHROMA_COLLECTION_NAME: str = Field(default="universe_knowledge_v1")
    UPLOAD_DIR: str = Field(default="./data/uploads")
    MAX_UPLOAD_SIZE_MB: int = Field(default=25, ge=1, le=100)

    # Local Fallback / Test Adapter Flag
    USE_LOCAL_STORAGE_FALLBACK: bool = Field(default=True)

    @field_validator("API_V1_PREFIX")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        return value.rstrip("/")

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_supabase_configured(self) -> bool:
        return bool(
            self.SUPABASE_URL
            and not self.SUPABASE_URL.startswith("https://your-project-ref")
            and self.SUPABASE_SERVICE_ROLE_KEY
            and not self.SUPABASE_SERVICE_ROLE_KEY.startswith("your-")
        )

    @property
    def is_gemini_configured(self) -> bool:
        return bool(
            self.GEMINI_API_KEY
            and not self.GEMINI_API_KEY.startswith("your-")
        )

    def ensure_directories(self) -> None:
        """Ensure local persistence directories exist."""
        Path(self.CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    settings = Settings()
    settings.ensure_directories()
    return settings

