"""Repository for managing `public.documents` metadata in Supabase PostgreSQL (with local fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import ConflictError, ResourceNotFoundError
from app.models.documents import (
    DocumentCategory,
    DocumentLanguage,
    DocumentMetadata,
    DocumentStatus,
    UpdateDocumentRequest,
)


class DocumentRepository:
    """Data access layer for `public.documents`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._local_docs: dict[str, DocumentMetadata] = {}
        self._supabase_client: Any = None
        if self.settings.is_supabase_configured:
            try:
                from supabase import create_client

                self._supabase_client = create_client(
                    self.settings.SUPABASE_URL,
                    self.settings.SUPABASE_SERVICE_ROLE_KEY,
                )
            except Exception:
                self._supabase_client = None

    def find_by_hash(self, file_hash: str) -> DocumentMetadata | None:
        """Check if a document with the given SHA-256 hash already exists."""
        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("documents")
                .select("*")
                .eq("file_hash", file_hash)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                return self._row_to_model(rows[0])
            return None

        for doc in self._local_docs.values():
            if doc.file_hash == file_hash:
                return doc
        return None

    def create_document(
        self,
        doc_id: str,
        title: str,
        filename: str,
        file_hash: str,
        storage_path: str,
        category: DocumentCategory,
        language: DocumentLanguage,
        file_size_bytes: int,
        uploaded_by: str | None,
        status: DocumentStatus = "processing",
        page_count: int = 0,
        chunk_count: int = 0,
    ) -> DocumentMetadata:
        """Create a new document record, raising ConflictError if SHA-256 already exists."""
        existing = self.find_by_hash(file_hash)
        if existing is not None:
            raise ConflictError(
                code="DOCUMENT_DUPLICATE",
                message=f"Document '{existing.title}' with identical content has already been uploaded.",
                details={"existing_document_id": existing.id, "file_hash": file_hash},
            )

        now = datetime.now(timezone.utc)
        doc = DocumentMetadata(
            id=doc_id,
            title=title.strip(),
            filename=filename,
            file_hash=file_hash,
            storage_path=storage_path,
            category=category,
            language=language,
            status=status,
            error_message=None,
            page_count=page_count,
            chunk_count=chunk_count,
            file_size_bytes=file_size_bytes,
            uploaded_by=uploaded_by,
            is_active=True,
            created_at=now,
            updated_at=now,
        )

        if self._supabase_client is not None:
            payload = {
                "id": doc.id,
                "title": doc.title,
                "filename": doc.filename,
                "file_hash": doc.file_hash,
                "storage_path": doc.storage_path,
                "category": doc.category,
                "language": doc.language,
                "status": doc.status,
                "error_message": doc.error_message,
                "page_count": doc.page_count,
                "chunk_count": doc.chunk_count,
                "file_size_bytes": doc.file_size_bytes,
                "uploaded_by": doc.uploaded_by,
                "is_active": doc.is_active,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
            res = self._supabase_client.table("documents").insert(payload).execute()
            rows = res.data or [payload]
            return self._row_to_model(rows[0])

        self._local_docs[doc.id] = doc
        return doc

    def mark_indexed(
        self,
        doc_id: str,
        page_count: int,
        chunk_count: int,
    ) -> DocumentMetadata:
        """Update document status to `indexed` with page and chunk counts."""
        doc = self.get_document(doc_id)
        now = datetime.now(timezone.utc)

        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("documents")
                .update(
                    {
                        "status": "indexed",
                        "page_count": page_count,
                        "chunk_count": chunk_count,
                        "error_message": None,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", doc_id)
                .execute()
            )
            rows = res.data or []
            if rows:
                return self._row_to_model(rows[0])

        updated = doc.model_copy(
            update={
                "status": "indexed",
                "page_count": page_count,
                "chunk_count": chunk_count,
                "error_message": None,
                "updated_at": now,
            }
        )
        self._local_docs[doc_id] = updated
        return updated

    def mark_failed(self, doc_id: str, error_message: str) -> DocumentMetadata:
        """Update document status to `failed` with diagnostic error message."""
        doc = self.get_document(doc_id)
        now = datetime.now(timezone.utc)

        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("documents")
                .update(
                    {
                        "status": "failed",
                        "error_message": error_message,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", doc_id)
                .execute()
            )
            rows = res.data or []
            if rows:
                return self._row_to_model(rows[0])

        updated = doc.model_copy(
            update={
                "status": "failed",
                "error_message": error_message,
                "updated_at": now,
            }
        )
        self._local_docs[doc_id] = updated
        return updated

    def get_document(self, doc_id: str) -> DocumentMetadata:
        """Retrieve a single document by ID or raise ResourceNotFoundError."""
        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("documents")
                .select("*")
                .eq("id", doc_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if not rows:
                raise ResourceNotFoundError("Document", doc_id)
            return self._row_to_model(rows[0])

        if doc_id not in self._local_docs:
            raise ResourceNotFoundError("Document", doc_id)
        return self._local_docs[doc_id]

    def list_documents(
        self,
        category: str | None = None,
        active_only: bool = False,
    ) -> list[DocumentMetadata]:
        """List documents ordered by `created_at DESC`."""
        if self._supabase_client is not None:
            query = self._supabase_client.table("documents").select("*")
            if category and category != "all":
                query = query.eq("category", category)
            if active_only:
                query = query.eq("is_active", True).eq("status", "indexed")
            res = query.order("created_at", desc=True).execute()
            return [self._row_to_model(r) for r in (res.data or [])]

        docs = list(self._local_docs.values())
        if category and category != "all":
            docs = [d for d in docs if d.category == category]
        if active_only:
            docs = [d for d in docs if d.is_active and d.status == "indexed"]
        docs.sort(key=lambda d: d.created_at, reverse=True)
        return docs

    def update_document(
        self,
        doc_id: str,
        update_req: UpdateDocumentRequest,
    ) -> DocumentMetadata:
        """Update document metadata (`title`, `category`, `language`, `is_active`)."""
        doc = self.get_document(doc_id)
        now = datetime.now(timezone.utc)

        new_title = update_req.title.strip() if update_req.title is not None else doc.title
        new_cat = update_req.category if update_req.category is not None else doc.category
        new_lang = update_req.language if update_req.language is not None else doc.language
        new_active = update_req.is_active if update_req.is_active is not None else doc.is_active

        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("documents")
                .update(
                    {
                        "title": new_title,
                        "category": new_cat,
                        "language": new_lang,
                        "is_active": new_active,
                        "updated_at": now.isoformat(),
                    }
                )
                .eq("id", doc_id)
                .execute()
            )
            rows = res.data or []
            if rows:
                return self._row_to_model(rows[0])

        updated = doc.model_copy(
            update={
                "title": new_title,
                "category": new_cat,
                "language": new_lang,
                "is_active": new_active,
                "updated_at": now,
            }
        )
        self._local_docs[doc_id] = updated
        return updated

    def delete_document(self, doc_id: str) -> DocumentMetadata:
        """Delete document record from database and return the deleted metadata."""
        doc = self.get_document(doc_id)
        if self._supabase_client is not None:
            self._supabase_client.table("documents").delete().eq("id", doc_id).execute()
            return doc

        self._local_docs.pop(doc_id, None)
        return doc

    @staticmethod
    def _row_to_model(row: dict[str, Any]) -> DocumentMetadata:
        return DocumentMetadata(
            id=str(row["id"]),
            title=row["title"],
            filename=row["filename"],
            file_hash=row["file_hash"],
            storage_path=row["storage_path"],
            category=row["category"],
            language=row.get("language", "en"),
            status=row.get("status", "indexed"),
            error_message=row.get("error_message"),
            page_count=int(row.get("page_count", 0)),
            chunk_count=int(row.get("chunk_count", 0)),
            file_size_bytes=int(row["file_size_bytes"]),
            uploaded_by=str(row["uploaded_by"]) if row.get("uploaded_by") else None,
            is_active=bool(row.get("is_active", True)),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


_document_repo_instance: DocumentRepository | None = None


def get_document_repository() -> DocumentRepository:
    """FastAPI dependency returning singleton DocumentRepository."""
    global _document_repo_instance
    if _document_repo_instance is None:
        _document_repo_instance = DocumentRepository()
    return _document_repo_instance

