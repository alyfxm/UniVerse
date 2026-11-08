"""Direct Semantic Search endpoint (`/api/v1/search/semantic`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.auth import UserProfile
from app.models.chat import SemanticSearchRequest, SemanticSearchResponse
from app.services.rag_service import RagService, get_rag_service

router = APIRouter(prefix="/search", tags=["Semantic Search"])


@router.post("/semantic", response_model=SemanticSearchResponse)
async def semantic_search(
    payload: SemanticSearchRequest,
    _current_user: UserProfile = Depends(get_current_user),
    rag_service: RagService = Depends(get_rag_service),
) -> SemanticSearchResponse:
    """Retrieve top-k relevant document chunks with page numbers and scores."""
    detected_lang = rag_service.detect_language(payload.query, preference="auto")
    citations = rag_service.retrieve_citations(
        query=payload.query,
        category_filter=payload.category_filter,
        top_k=payload.top_k,
    )
    return SemanticSearchResponse(
        query=payload.query,
        detected_language=detected_lang,
        results=citations,
        total=len(citations),
    )

