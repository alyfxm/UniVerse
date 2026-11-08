"""Orchestrator service coordinating PDF ingestion, embedding, and two-store synchronization."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceNotFoundError
from app.models.documents import (
    DocumentCategory,
    DocumentLanguage,
    DocumentMetadata,
    IngestionJobStage,
    IngestionJobStatus,
    UpdateDocumentRequest,
)
from app.repositories.chroma_repo import ChromaVectorRepository, get_chroma_repository
from app.repositories.document_repo import DocumentRepository, get_document_repository
from app.repositories.storage_repo import StorageRepository, get_storage_repository
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.pdf_processor import PdfProcessorService


class IngestionService:
    """Coordinates PDF validation, storage, page chunking, embedding, and ChromaDB indexing."""

    _jobs: dict[str, IngestionJobStatus] = {}

    def __init__(
        self,
        settings: Settings,
        pdf_processor: PdfProcessorService,
        embedding_service: EmbeddingService,
        chroma_repo: ChromaVectorRepository,
        document_repo: DocumentRepository,
        storage_repo: StorageRepository,
    ) -> None:
        self.settings = settings
        self.pdf_processor = pdf_processor
        self.embedding_service = embedding_service
        self.chroma_repo = chroma_repo
        self.document_repo = document_repo
        self.storage_repo = storage_repo

    @classmethod
    def _record_job_stage(
        cls,
        job_id: str,
        document_id: str,
        title: str,
        stage: IngestionJobStage,
        progress_percent: int,
        page_count: int = 0,
        chunk_count: int = 0,
        error_message: str | None = None,
    ) -> IngestionJobStatus:
        status_obj = IngestionJobStatus(
            job_id=job_id,
            document_id=document_id,
            title=title,
            stage=stage,
            progress_percent=progress_percent,
            page_count=page_count,
            chunk_count=chunk_count,
            error_message=error_message,
            updated_at=datetime.now(timezone.utc),
        )
        cls._jobs[job_id] = status_obj
        cls._jobs[document_id] = status_obj
        return status_obj

    @classmethod
    def get_job_status(cls, job_or_doc_id: str) -> IngestionJobStatus:
        if job_or_doc_id not in cls._jobs:
            raise ResourceNotFoundError("IngestionJob", job_or_doc_id)
        return cls._jobs[job_or_doc_id]

    def ingest_pdf(
        self,
        file_bytes: bytes,
        filename: str,
        title: str,
        category: DocumentCategory,
        language: DocumentLanguage,
        uploaded_by: str | None = None,
    ) -> DocumentMetadata:
        """Validate, extract, chunk, embed, and persist a PDF document."""
        # 1. Validate PDF magic bytes & size
        self.pdf_processor.validate_pdf_bytes(
            file_bytes=file_bytes,
            max_size_bytes=self.settings.max_upload_size_bytes,
        )

        # 2. Check SHA-256 deduplication before expensive parsing
        file_hash = self.pdf_processor.compute_sha256(file_bytes)
        existing = self.document_repo.find_by_hash(file_hash)
        if existing is not None:
            # Delegate to create_document to raise standardized ConflictError
            self.document_repo.create_document(
                doc_id=str(uuid.uuid4()),
                title=title,
                filename=filename,
                file_hash=file_hash,
                storage_path=existing.storage_path,
                category=category,
                language=language,
                file_size_bytes=len(file_bytes),
                uploaded_by=uploaded_by,
            )

        # 3. Extract pages (including Markdown tables) and verify text presence
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        doc_id = str(uuid.uuid4())
        self._record_job_stage(
            job_id=job_id,
            document_id=doc_id,
            title=title,
            stage="extracting_pages_and_tables",
            progress_percent=25,
        )
        total_pages, extracted_pages = self.pdf_processor.extract_pages(file_bytes)

        # 4. Save binary file & create initial document row
        safe_filename = self.storage_repo.sanitize_filename(filename)
        storage_path = self.storage_repo.save_pdf(doc_id, safe_filename, file_bytes)

        self.document_repo.create_document(
            doc_id=doc_id,
            title=title,
            filename=safe_filename,
            file_hash=file_hash,
            storage_path=storage_path,
            category=category,
            language=language,
            file_size_bytes=len(file_bytes),
            uploaded_by=uploaded_by,
            status="processing",
            page_count=total_pages,
        )

        try:
            # 5. Chunk pages preserving 1-based page numbers
            self._record_job_stage(
                job_id=job_id,
                document_id=doc_id,
                title=title,
                stage="chunking",
                progress_percent=55,
                page_count=total_pages,
            )
            chunks = self.pdf_processor.chunk_pages(
                document_id=doc_id,
                document_title=title.strip(),
                category=category,
                language=language,
                pages=extracted_pages,
                is_active=True,
            )

            # 6. Compute embeddings on contextual text and upsert to ChromaDB
            self._record_job_stage(
                job_id=job_id,
                document_id=doc_id,
                title=title,
                stage="embedding_and_indexing",
                progress_percent=85,
                page_count=total_pages,
                chunk_count=len(chunks),
            )
            contextual_texts = [c.contextual_text for c in chunks]
            embeddings = self.embedding_service.embed_documents(contextual_texts)
            self.chroma_repo.upsert_chunks(chunks=chunks, embeddings=embeddings)

            # 7. Mark document as indexed
            indexed_doc = self.document_repo.mark_indexed(
                doc_id=doc_id,
                page_count=total_pages,
                chunk_count=len(chunks),
            )
            self._record_job_stage(
                job_id=job_id,
                document_id=doc_id,
                title=title,
                stage="completed",
                progress_percent=100,
                page_count=total_pages,
                chunk_count=len(chunks),
            )
            return indexed_doc
        except Exception as exc:
            self._record_job_stage(
                job_id=job_id,
                document_id=doc_id,
                title=title,
                stage="failed",
                progress_percent=100,
                page_count=total_pages,
                error_message=str(exc),
            )
            self.document_repo.mark_failed(doc_id=doc_id, error_message=str(exc))
            raise

    def update_document(
        self,
        doc_id: str,
        update_req: UpdateDocumentRequest,
    ) -> DocumentMetadata:
        """Update document in PostgreSQL and synchronize metadata across ChromaDB chunks."""
        updated_doc = self.document_repo.update_document(doc_id, update_req)
        self.chroma_repo.update_document_metadata(
            document_id=doc_id,
            title=updated_doc.title,
            category=updated_doc.category,
            language=updated_doc.language,
            is_active=updated_doc.is_active,
        )
        return updated_doc

    def delete_document(self, doc_id: str) -> DocumentMetadata:
        """Delete document from PostgreSQL, ChromaDB vectors, and file storage."""
        deleted_doc = self.document_repo.delete_document(doc_id)
        self.chroma_repo.delete_document_chunks(doc_id)
        self.storage_repo.delete_pdf(deleted_doc.storage_path)
        return deleted_doc


def get_ingestion_service(
    settings: Settings = Depends(get_settings),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    chroma_repo: ChromaVectorRepository = Depends(get_chroma_repository),
    document_repo: DocumentRepository = Depends(get_document_repository),
    storage_repo: StorageRepository = Depends(get_storage_repository),
) -> IngestionService:
    """FastAPI dependency returning IngestionService."""
    return IngestionService(
        settings=settings,
        pdf_processor=PdfProcessorService(),
        embedding_service=embedding_service,
        chroma_repo=chroma_repo,
        document_repo=document_repo,
        storage_repo=storage_repo,
    )

