"""Repository for storing and retrieving PDF files (Supabase Storage + local volume fallback)."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from app.core.config import Settings, get_settings
from app.core.exceptions import ResourceNotFoundError


class StorageRepository:
    """Manages binary PDF storage in Supabase Storage bucket or local filesystem."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.upload_dir = Path(self.settings.UPLOAD_DIR)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._supabase_client: Any = None
        if self.settings.is_supabase_configured and not self.settings.USE_LOCAL_STORAGE_FALLBACK:
            try:
                from supabase import create_client

                self._supabase_client = create_client(
                    self.settings.SUPABASE_URL,
                    self.settings.SUPABASE_SERVICE_ROLE_KEY,
                )
            except Exception:
                self._supabase_client = None

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Sanitize filename to prevent path traversal or invalid characters."""
        base = Path(filename).name
        sanitized = re.sub(r"[^a-zA-Z0-9._-]", "_", base)
        if not sanitized.lower().endswith(".pdf"):
            sanitized = f"{sanitized}.pdf"
        return sanitized

    def save_pdf(self, document_id: str, filename: str, file_bytes: bytes) -> str:
        """Save PDF bytes and return canonical storage path."""
        safe_name = self.sanitize_filename(filename)
        storage_key = f"{document_id}/{safe_name}"

        if self._supabase_client is not None:
            try:
                bucket = self._supabase_client.storage.from_(
                    self.settings.SUPABASE_STORAGE_BUCKET
                )
                bucket.upload(
                    path=storage_key,
                    file=file_bytes,
                    file_options={"content-type": "application/pdf", "upsert": "true"},
                )
                return storage_key
            except Exception:
                pass

        # Local filesystem storage
        target_dir = self.upload_dir / document_id
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / safe_name
        target_file.write_bytes(file_bytes)
        return storage_key

    def read_pdf(self, storage_path: str) -> bytes:
        """Read PDF bytes from storage."""
        if self._supabase_client is not None:
            try:
                bucket = self._supabase_client.storage.from_(
                    self.settings.SUPABASE_STORAGE_BUCKET
                )
                data = bucket.download(storage_path)
                if data:
                    return bytes(data)
            except Exception:
                pass

        local_file = (self.upload_dir / storage_path).resolve()
        if not local_file.exists() or not local_file.is_file():
            raise ResourceNotFoundError("DocumentFile", storage_path)
        return local_file.read_bytes()

    def delete_pdf(self, storage_path: str) -> None:
        """Delete PDF file from storage."""
        if self._supabase_client is not None:
            try:
                bucket = self._supabase_client.storage.from_(
                    self.settings.SUPABASE_STORAGE_BUCKET
                )
                bucket.remove([storage_path])
            except Exception:
                pass

        local_file = self.upload_dir / storage_path
        if local_file.exists():
            local_file.unlink(missing_ok=True)
            parent = local_file.parent
            if parent != self.upload_dir and parent.exists() and not any(parent.iterdir()):
                parent.rmdir()


_storage_repo_instance: StorageRepository | None = None


def get_storage_repository() -> StorageRepository:
    """FastAPI dependency returning singleton StorageRepository."""
    global _storage_repo_instance
    if _storage_repo_instance is None:
        _storage_repo_instance = StorageRepository()
    return _storage_repo_instance

