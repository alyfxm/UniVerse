"""Admin Knowledge Management & Document File Serving endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status

from app.core.exceptions import AuthorizationError
from app.core.security import get_current_user, require_admin
from app.models.auth import UserProfile
from app.models.documents import (
    DocumentCategory,
    DocumentLanguage,
    DocumentListResponse,
    DocumentMetadata,
    IngestionJobStatus,
    PagePreviewResponse,
    UpdateDocumentRequest,
)
from app.repositories.document_repo import DocumentRepository, get_document_repository
from app.repositories.storage_repo import StorageRepository, get_storage_repository
from app.services.ingestion_service import IngestionService, get_ingestion_service
from app.services.pdf_processor import PdfProcessorService

admin_router = APIRouter(prefix="/admin/documents", tags=["Admin Documents"])
public_doc_router = APIRouter(prefix="/documents", tags=["Documents"])


@admin_router.post(
    "",
    response_model=DocumentMetadata,
    status_code=status.HTTP_201_CREATED,
)
async def upload_and_index_document(
    file: UploadFile = File(..., description="PDF file to upload and index"),
    title: str = Form(..., min_length=1, max_length=250),
    category: DocumentCategory = Form(...),
    language: DocumentLanguage = Form(default="en"),
    admin_user: UserProfile = Depends(require_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> DocumentMetadata:
    """Upload a PDF document, extract pages, embed chunks, and index in ChromaDB."""
    file_bytes = await file.read()
    filename = file.filename or "document.pdf"
    return ingestion_service.ingest_pdf(
        file_bytes=file_bytes,
        filename=filename,
        title=title,
        category=category,
        language=language,
        uploaded_by=admin_user.id,
    )


@admin_router.get("", response_model=DocumentListResponse)
async def list_all_documents(
    category: str | None = None,
    _admin_user: UserProfile = Depends(require_admin),
    document_repo: DocumentRepository = Depends(get_document_repository),
) -> DocumentListResponse:
    """List all knowledge base documents for the Admin Dashboard."""
    docs = document_repo.list_documents(category=category, active_only=False)
    return DocumentListResponse(documents=docs, total=len(docs))


@admin_router.patch("/{doc_id}", response_model=DocumentMetadata)
async def update_document_metadata(
    doc_id: str,
    payload: UpdateDocumentRequest,
    _admin_user: UserProfile = Depends(require_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> DocumentMetadata:
    """Toggle `is_active` or update metadata in both Supabase PostgreSQL and ChromaDB."""
    return ingestion_service.update_document(doc_id=doc_id, update_req=payload)


@admin_router.delete("/{doc_id}", response_model=DocumentMetadata)
async def delete_document(
    doc_id: str,
    _admin_user: UserProfile = Depends(require_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> DocumentMetadata:
    """Delete a document and cascade removal to ChromaDB vectors and file storage."""
    return ingestion_service.delete_document(doc_id=doc_id)


@admin_router.get("/jobs/{job_or_doc_id}", response_model=IngestionJobStatus)
async def get_ingestion_job_status(
    job_or_doc_id: str,
    _admin_user: UserProfile = Depends(require_admin),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
) -> IngestionJobStatus:
    """Poll stage-by-stage PDF ingestion progress (`extracting` -> `chunking` -> `embedding` -> `completed`)."""
    return ingestion_service.get_job_status(job_or_doc_id)


@public_doc_router.get("/{doc_id}/file")
async def serve_document_pdf(
    doc_id: str,
    current_user: UserProfile = Depends(get_current_user),
    document_repo: DocumentRepository = Depends(get_document_repository),
    storage_repo: StorageRepository = Depends(get_storage_repository),
) -> Response:
    """Serve PDF file bytes for inline citation page viewing (`#page=N`)."""
    doc = document_repo.get_document(doc_id)
    if not doc.is_active and current_user.role != "admin":
        raise AuthorizationError("This document is currently inactive.")

    pdf_bytes = storage_repo.read_pdf(doc.storage_path)
    headers = {
        "Content-Disposition": f'inline; filename="{doc.filename}"',
        "Cache-Control": "private, max-age=3600",
    }
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers=headers,
    )


@public_doc_router.get(
    "/{doc_id}/pages/{page_number}/preview",
    response_model=PagePreviewResponse,
)
async def preview_document_page_with_highlight(
    doc_id: str,
    page_number: int,
    highlight: str | None = None,
    current_user: UserProfile = Depends(get_current_user),
    document_repo: DocumentRepository = Depends(get_document_repository),
    storage_repo: StorageRepository = Depends(get_storage_repository),
) -> PagePreviewResponse:
    """Render a specific PDF page to PNG with visual yellow bounding-box highlight over the cited snippet."""
    doc = document_repo.get_document(doc_id)
    if not doc.is_active and current_user.role != "admin":
        raise AuthorizationError("This document is currently inactive.")

    pdf_bytes = storage_repo.read_pdf(doc.storage_path)
    return PdfProcessorService.render_page_with_highlight(
        file_bytes=pdf_bytes,
        document_id=doc.id,
        document_title=doc.title,
        page_number=page_number,
        highlight_snippet=highlight,
    )

