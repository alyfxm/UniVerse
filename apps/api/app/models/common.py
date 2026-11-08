"""Common Pydantic schemas for health checks and standardized error envelopes."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(..., description="Request correlation ID")


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class DependencyStatus(BaseModel):
    supabase: Literal["connected", "local_fallback", "error"]
    chromadb: Literal["connected", "local_fallback", "error"]
    gemini: Literal["configured", "local_fallback", "error"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    dependencies: DependencyStatus

