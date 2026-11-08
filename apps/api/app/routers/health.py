"""Health and readiness probe endpoints."""

from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.models.common import DependencyStatus, HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse)
async def get_health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    """Return service liveness and dependency readiness statuses."""
    supabase_status = "connected" if settings.is_supabase_configured else "local_fallback"
    gemini_status = "configured" if settings.is_gemini_configured else "local_fallback"

    chroma_path = Path(settings.CHROMA_PERSIST_DIR)
    chromadb_status = "connected" if chroma_path.exists() else "local_fallback"

    return HealthResponse(
        status="ok",
        service=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.APP_ENV,
        dependencies=DependencyStatus(
            supabase=supabase_status,
            chromadb=chromadb_status,
            gemini=gemini_status,
        ),
    )

