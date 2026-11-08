"""Pydantic models for knowledge base documents and semantic chunks."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

DocumentCategory = Literal["academic", "facilities", "events", "financial", "general"]
DocumentLanguage = Literal["en", "ms", "bilingual"]
DocumentStatus = Literal["queued", "processing", "indexed", "failed"]


class DocumentMetadata(BaseModel):
    """Represents a row in `public.documents`."""

    id: str = Field(..., description="Document UUID")
    title: str = Field(..., min_length=1, max_length=250)
    filename: str
    file_hash: str = Field(..., description="SHA-256 hex digest of PDF content")
    storage_path: str
    category: DocumentCategory
    language: DocumentLanguage = "en"
    status: DocumentStatus = "queued"
    error_message: str | None = None
    page_count: int = Field(default=0, ge=0)
    chunk_count: int = Field(default=0, ge=0)
    file_size_bytes: int = Field(..., gt=0)
    uploaded_by: str | None = None
    is_active: bool = True
    created_at: datetime
    updated_at: datetime


class DocumentChunk(BaseModel):
    """A page-aware semantic chunk extracted from a PDF document."""

    chunk_id: str = Field(..., description="Deterministic ID: {doc_id}_p{page}_c{idx}")
    document_id: str
    document_title: str
    category: DocumentCategory
    language: DocumentLanguage
    page_number: int = Field(..., ge=1, description="1-based original PDF page number")
    chunk_index: int = Field(..., ge=0)
    text: str = Field(..., min_length=1, description="Raw cleaned chunk text")
    contextual_text: str = Field(
        ...,
        description="Text prefixed with document title and page number for embedding",
    )
    char_start: int = Field(..., ge=0)
    char_end: int = Field(..., ge=0)
    is_active: bool = True


class UpdateDocumentRequest(BaseModel):
    """Request payload for `PATCH /api/v1/admin/documents/{doc_id}`."""

    title: str | None = Field(default=None, min_length=1, max_length=250)
    category: DocumentCategory | None = None
    language: DocumentLanguage | None = None
    is_active: bool | None = None


class DocumentListResponse(BaseModel):
    """Response payload for `GET /api/v1/admin/documents`."""

    documents: list[DocumentMetadata]
    total: int


IngestionJobStage = Literal[
    "queued",
    "validating",
    "extracting_pages_and_tables",
    "chunking",
    "embedding_and_indexing",
    "completed",
    "failed",
]


class IngestionJobStatus(BaseModel):
    """Tracks asynchronous/staged PDF ingestion pipeline progress."""

    job_id: str
    document_id: str
    title: str
    stage: IngestionJobStage
    progress_percent: int = Field(..., ge=0, le=100)
    page_count: int = 0
    chunk_count: int = 0
    error_message: str | None = None
    updated_at: datetime


class HighlightRect(BaseModel):
    """Normalized [0..1] bounding box coordinates of a cited snippet on a PDF page."""

    x0: float
    y0: float
    x1: float
    y1: float


class PagePreviewResponse(BaseModel):
    """Rendered PNG page image (base64 data URI) + bounding-box coordinates for visual citation highlighting."""

    document_id: str
    document_title: str
    page_number: int
    total_pages: int
    page_text: str
    image_data_url: str = Field(..., description="data:image/png;base64,... with highlighted snippet")
    highlight_boxes: list[HighlightRect] = Field(default_factory=list)

