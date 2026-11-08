"""Pydantic models for Chat Sessions, Messages, Page Citations, and Semantic Search."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

CategoryFilter = Literal["academic", "facilities", "events", "financial", "general", "all"]
QueryLanguagePreference = Literal["auto", "en", "ms"]
DetectedLanguage = Literal["en", "ms"]
MessageRole = Literal["user", "assistant"]


class Citation(BaseModel):
    """Structured page-level reference to an original PDF document."""

    citation_index: int = Field(..., ge=1, description="1-based inline marker index [1], [2]")
    document_id: str
    document_title: str
    category: str = "general"
    page_number: int = Field(..., ge=1, description="1-based page number in source PDF")
    snippet: str = Field(..., description="Relevant excerpt from the source page")
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    file_url: str = Field(..., description="API URL with #page=N anchor")


class ChatQueryRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/query`."""

    session_id: str | None = Field(
        default=None,
        description="Optional existing session UUID; creates a new session if omitted",
    )
    query: str = Field(..., min_length=1, max_length=2000)
    language: QueryLanguagePreference = Field(default="auto")
    category_filter: CategoryFilter = Field(default="all")
    stream: bool = Field(default=False)


class ChatQueryResponse(BaseModel):
    """Response payload for `POST /api/v1/chat/query`."""

    message_id: str
    session_id: str
    answer: str
    detected_language: DetectedLanguage
    citations: list[Citation] = Field(default_factory=list)
    is_grounded: bool = True
    latency_ms: int = Field(..., ge=0)


class ChatMessage(BaseModel):
    """Represents a stored message in `public.messages`."""

    id: str
    session_id: str
    role: MessageRole
    content: str
    detected_language: DetectedLanguage = "en"
    citations: list[Citation] = Field(default_factory=list)
    feedback_rating: Literal[-1, 1] | None = None
    feedback_comment: str | None = None
    latency_ms: int | None = None
    created_at: datetime


class ChatSessionSummary(BaseModel):
    """Represents a stored chat session in `public.chat_sessions`."""

    id: str
    user_id: str
    title: str
    language: DetectedLanguage = "en"
    category_filter: CategoryFilter = "all"
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime


class ChatSessionDetail(BaseModel):
    """Full chat session with ordered message history."""

    session: ChatSessionSummary
    messages: list[ChatMessage]


class ChatSessionListResponse(BaseModel):
    """Paginated list of user chat sessions."""

    sessions: list[ChatSessionSummary]
    total: int


class MessageFeedbackRequest(BaseModel):
    """Request payload for `POST /api/v1/chat/messages/{message_id}/feedback`."""

    rating: Literal[-1, 1] = Field(..., description="1 for thumbs up, -1 for thumbs down")
    comment: str | None = Field(default=None, max_length=1000)


class SemanticSearchRequest(BaseModel):
    """Request payload for `POST /api/v1/search/semantic`."""

    query: str = Field(..., min_length=1, max_length=1000)
    category_filter: CategoryFilter = Field(default="all")
    top_k: int = Field(default=5, ge=1, le=20)


class SemanticSearchResponse(BaseModel):
    """Response payload for `POST /api/v1/search/semantic`."""

    query: str
    detected_language: DetectedLanguage
    results: list[Citation]
    total: int

