"""Chat Query (JSON + SSE stream), Session History, and Feedback endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.security import get_current_user
from app.models.auth import UserProfile
from app.models.chat import (
    ChatMessage,
    ChatQueryRequest,
    ChatQueryResponse,
    ChatSessionDetail,
    ChatSessionListResponse,
    ChatSessionSummary,
    MessageFeedbackRequest,
)
from app.repositories.chat_repo import ChatRepository, get_chat_repository
from app.services.rag_service import RagService, get_rag_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/query", response_model=ChatQueryResponse)
async def chat_query(
    payload: ChatQueryRequest,
    current_user: UserProfile = Depends(get_current_user),
    rag_service: RagService = Depends(get_rag_service),
):
    """Answer a student question using RAG (returns JSON or SSE stream when `stream=True`)."""
    if payload.stream:
        event_generator = rag_service.stream_query(
            user_id=current_user.id,
            query=payload.query,
            session_id=payload.session_id,
            language_pref=payload.language,
            category_filter=payload.category_filter,
        )
        return StreamingResponse(
            event_generator,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return rag_service.answer_query(
        user_id=current_user.id,
        query=payload.query,
        session_id=payload.session_id,
        language_pref=payload.language,
        category_filter=payload.category_filter,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_chat_sessions(
    current_user: UserProfile = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(get_chat_repository),
) -> ChatSessionListResponse:
    """List the authenticated user's chat sessions ordered by most recent."""
    sessions = chat_repo.list_user_sessions(user_id=current_user.id)
    return ChatSessionListResponse(sessions=sessions, total=len(sessions))


@router.get("/sessions/{session_id}", response_model=ChatSessionDetail)
async def get_chat_session_detail(
    session_id: str,
    current_user: UserProfile = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(get_chat_repository),
) -> ChatSessionDetail:
    """Retrieve full message history and page citations for a chat session."""
    return chat_repo.get_session_detail(session_id=session_id, user_id=current_user.id)


@router.delete("/sessions/{session_id}", response_model=ChatSessionSummary)
async def delete_chat_session(
    session_id: str,
    current_user: UserProfile = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(get_chat_repository),
) -> ChatSessionSummary:
    """Delete a chat session owned by the authenticated user."""
    return chat_repo.delete_session(session_id=session_id, user_id=current_user.id)


@router.post("/messages/{message_id}/feedback", response_model=ChatMessage)
async def submit_message_feedback(
    message_id: str,
    payload: MessageFeedbackRequest,
    current_user: UserProfile = Depends(get_current_user),
    chat_repo: ChatRepository = Depends(get_chat_repository),
) -> ChatMessage:
    """Submit thumbs-up (`1`) or thumbs-down (`-1`) feedback on a chat message."""
    return chat_repo.update_message_feedback(
        message_id=message_id,
        user_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
    )

