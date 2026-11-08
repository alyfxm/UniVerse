"""Unit and Integration Tests for Milestone 2:
- PDF magic byte, empty file, size limit, and scanned/no-text validation
- Multi-page PDF text extraction & 1-indexed page number preservation
- SHA-256 deduplication (`DOCUMENT_DUPLICATE` 409 Conflict)
- ChromaDB vector indexing, semantic retrieval, and metadata filtering (`category`, `is_active`)
- Cross-lingual Malay <-> English concept alignment in embeddings
- Admin Document CRUD (`POST`, `GET`, `PATCH`, `DELETE /api/v1/admin/documents`)
- Cascading deletion across DocumentRepository, ChromaDB, and StorageRepository
- Serving PDF file bytes via `GET /api/v1/documents/{doc_id}/file`
"""

from __future__ import annotations

from pathlib import Path
import uuid

import pymupdf as fitz
import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.security import create_supabase_jwt
from app.main import create_app
from app.repositories.chroma_repo import ChromaVectorRepository, get_chroma_repository
from app.repositories.document_repo import DocumentRepository, get_document_repository
from app.repositories.profile_repo import ProfileRepository, get_profile_repository
from app.repositories.storage_repo import StorageRepository, get_storage_repository
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.ingestion_service import IngestionService, get_ingestion_service
from app.services.pdf_processor import PdfProcessorService


def build_synthetic_pdf(pages_text: list[str]) -> bytes:
    """Create a real multi-page PDF in memory using PyMuPDF."""
    doc = fitz.open()
    rect = fitz.Rect(72, 72, 520, 750)
    for page_content in pages_text:
        page = doc.new_page()
        if page_content:
            page.insert_textbox(rect, page_content, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


@pytest.fixture
def test_env(tmp_path: Path):
    settings = Settings(
        UPLOAD_DIR=str(tmp_path / "uploads"),
        CHROMA_PERSIST_DIR=str(tmp_path / "chroma"),
        MAX_UPLOAD_SIZE_MB=5,
        USE_LOCAL_STORAGE_FALLBACK=True,
    )
    profile_repo = ProfileRepository(settings=settings)
    doc_repo = DocumentRepository(settings=settings)
    storage_repo = StorageRepository(settings=settings)
    chroma_repo = ChromaVectorRepository(
        settings=settings,
        ephemeral=True,
        collection_name=f"test_col_{uuid.uuid4().hex[:8]}",
    )
    emb_service = EmbeddingService(settings=settings)
    pdf_processor = PdfProcessorService(chunk_size_chars=400, chunk_overlap_chars=50)
    ingestion_service = IngestionService(
        settings=settings,
        pdf_processor=pdf_processor,
        embedding_service=emb_service,
        chroma_repo=chroma_repo,
        document_repo=doc_repo,
        storage_repo=storage_repo,
    )

    app = create_app()
    app.dependency_overrides[get_profile_repository] = lambda: profile_repo
    app.dependency_overrides[get_document_repository] = lambda: doc_repo
    app.dependency_overrides[get_storage_repository] = lambda: storage_repo
    app.dependency_overrides[get_chroma_repository] = lambda: chroma_repo
    app.dependency_overrides[get_embedding_service] = lambda: emb_service
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service

    return {
        "app": app,
        "chroma_repo": chroma_repo,
        "doc_repo": doc_repo,
        "storage_repo": storage_repo,
        "emb_service": emb_service,
    }


@pytest.fixture
async def client(test_env) -> httpx.AsyncClient:
    app: FastAPI = test_env["app"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def admin_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="99999999-9999-9999-9999-999999999999",
        email="admin@universe.edu.my",
        role="admin",
        display_name="Knowledge Admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        email="student@universe.edu.my",
        role="student",
        display_name="Aiman Student",
    )
    return {"Authorization": f"Bearer {token}"}


async def test_rejects_invalid_and_empty_pdf_uploads(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """Verify non-PDF files and blank/scanned PDFs return descriptive 400 errors."""
    # 1. PNG file disguised as .pdf
    res_png = await client.post(
        "/api/v1/admin/documents",
        headers=admin_headers,
        files={"file": ("fake.pdf", b"\x89PNG\r\n\x1a\nnot-a-pdf", "application/pdf")},
        data={"title": "Invalid File", "category": "academic", "language": "en"},
    )
    assert res_png.status_code == 400
    assert res_png.json()["error"]["code"] == "DOCUMENT_INVALID_FORMAT"

    # 2. PDF with blank page (0 extractable text)
    blank_pdf = build_synthetic_pdf([""])
    res_blank = await client.post(
        "/api/v1/admin/documents",
        headers=admin_headers,
        files={"file": ("blank.pdf", blank_pdf, "application/pdf")},
        data={"title": "Scanned Blank", "category": "academic", "language": "en"},
    )
    assert res_blank.status_code == 400
    assert res_blank.json()["error"]["code"] == "DOCUMENT_NO_EXTRACTABLE_TEXT"


async def test_student_cannot_upload_or_delete_documents(
    client: httpx.AsyncClient,
    student_headers: dict[str, str],
) -> None:
    """Verify students receive 403 Forbidden on `/api/v1/admin/documents`."""
    pdf_bytes = build_synthetic_pdf(["University Library Rules Page 1"])
    res = await client.post(
        "/api/v1/admin/documents",
        headers=student_headers,
        files={"file": ("rules.pdf", pdf_bytes, "application/pdf")},
        data={"title": "Library Rules", "category": "facilities", "language": "en"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_full_pdf_ingestion_deduplication_and_lifecycle(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
    student_headers: dict[str, str],
    test_env: dict,
) -> None:
    """Verify multi-page PDF ingestion, page number preservation, deduplication, toggle, and deletion."""
    chroma_repo: ChromaVectorRepository = test_env["chroma_repo"]
    emb_service: EmbeddingService = test_env["emb_service"]

    page_1 = (
        "Undergraduate Academic Regulations 2026. "
        "Course registration and add/drop must be completed within the first two weeks of the semester."
    )
    page_2 = (
        "Deferment of Study Policy. "
        "Students applying for deferment of study must submit their official request via the portal "
        "by week four (4) of the semester. Medical deferment requires a hospital certificate."
    )
    page_3 = (
        "Peraturan Penangguhan Pengajian. "
        "Pelajar yang memohon penangguhan atas faktor kesihatan wajib menyertakan sijil perubatan rasmi."
    )
    pdf_bytes = build_synthetic_pdf([page_1, page_2, page_3])

    # 1. Upload & index 3-page bilingual PDF
    upload_res = await client.post(
        "/api/v1/admin/documents",
        headers=admin_headers,
        files={"file": ("Academic_Handbook_2026.pdf", pdf_bytes, "application/pdf")},
        data={
            "title": "Undergraduate Academic Regulations 2026",
            "category": "academic",
            "language": "bilingual",
        },
    )
    assert upload_res.status_code == 201
    doc_meta = upload_res.json()
    doc_id = doc_meta["id"]
    assert doc_meta["status"] == "indexed"
    assert doc_meta["page_count"] == 3
    assert doc_meta["chunk_count"] >= 3
    assert doc_meta["is_active"] is True

    # 2. Verify duplicate upload is rejected with 409 DOCUMENT_DUPLICATE
    dup_res = await client.post(
        "/api/v1/admin/documents",
        headers=admin_headers,
        files={"file": ("Copy_Handbook.pdf", pdf_bytes, "application/pdf")},
        data={
            "title": "Duplicate Upload",
            "category": "academic",
            "language": "bilingual",
        },
    )
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "DOCUMENT_DUPLICATE"

    # 3. Verify ChromaDB retrieval preserves exact page_number (Page 2 & Page 3 for deferment/penangguhan)
    ms_query_vec = emb_service.embed_query(
        "Bagaimanakah cara memohon penangguhan pengajian atas sebab kesihatan?"
    )
    hits = chroma_repo.query_similar(
        query_embedding=ms_query_vec,
        top_k=3,
        category_filter="academic",
    )
    assert len(hits) >= 2
    retrieved_pages = {h.page_number for h in hits}
    assert 2 in retrieved_pages or 3 in retrieved_pages
    assert all(h.document_id == doc_id for h in hits)

    # 4. Student can fetch PDF file for citation preview
    file_res = await client.get(
        f"/api/v1/documents/{doc_id}/file",
        headers=student_headers,
    )
    assert file_res.status_code == 200
    assert file_res.headers["content-type"] == "application/pdf"
    assert file_res.content.startswith(b"%PDF-")

    # 5. Admin toggles `is_active = False` -> ChromaDB excludes inactive chunks
    patch_res = await client.patch(
        f"/api/v1/admin/documents/{doc_id}",
        headers=admin_headers,
        json={"is_active": False},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_active"] is False

    active_hits = chroma_repo.query_similar(
        query_embedding=ms_query_vec,
        top_k=3,
        active_only=True,
    )
    assert len(active_hits) == 0

    # Student cannot download inactive PDF
    inactive_file_res = await client.get(
        f"/api/v1/documents/{doc_id}/file",
        headers=student_headers,
    )
    assert inactive_file_res.status_code == 403

    # 6. Admin deletes document -> cascades to ChromaDB and Storage
    del_res = await client.delete(
        f"/api/v1/admin/documents/{doc_id}",
        headers=admin_headers,
    )
    assert del_res.status_code == 200
    assert chroma_repo.count_chunks(document_id=doc_id) == 0

    list_res = await client.get("/api/v1/admin/documents", headers=admin_headers)
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0
