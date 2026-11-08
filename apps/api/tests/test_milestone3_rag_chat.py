"""Unit and Integration Tests for Milestone 3:
- Language detection (Bahasa Melayu vs English) & explicit override
- Cross-lingual RAG query (Malay query retrieving from an English PDF document and vice versa)
- Page-level citation verification (`citation_index`, `page_number`, `file_url` with `#page=N`)
- Hallucinated citation marker sanitization (`[9]` stripped when only 2 sources exist)
- Unanswerable query fallback (`is_grounded = False`, empty citations)
- SSE Streaming response (`stream=True`)
- Chat session history, multi-turn persistence, user isolation (403 on other user's session), and feedback
- Direct semantic search endpoint (`POST /api/v1/search/semantic`)
"""

from __future__ import annotations

import json
from pathlib import Path
import uuid

import httpx
import pymupdf as fitz
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.security import create_supabase_jwt
from app.main import create_app
from app.repositories.chat_repo import ChatRepository, get_chat_repository
from app.repositories.chroma_repo import ChromaVectorRepository, get_chroma_repository
from app.repositories.document_repo import DocumentRepository, get_document_repository
from app.repositories.profile_repo import ProfileRepository, get_profile_repository
from app.repositories.storage_repo import StorageRepository, get_storage_repository
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.ingestion_service import IngestionService, get_ingestion_service
from app.services.pdf_processor import PdfProcessorService
from app.services.rag_service import RagService, get_rag_service


def build_pdf(pages_text: list[str]) -> bytes:
    doc = fitz.open()
    rect = fitz.Rect(72, 72, 520, 750)
    for text in pages_text:
        page = doc.new_page()
        page.insert_textbox(rect, text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def rag_env(tmp_path: Path):
    settings = Settings(
        UPLOAD_DIR=str(tmp_path / "uploads"),
        CHROMA_PERSIST_DIR=str(tmp_path / "chroma"),
        MAX_UPLOAD_SIZE_MB=5,
        USE_LOCAL_STORAGE_FALLBACK=True,
    )
    profile_repo = ProfileRepository(settings=settings)
    doc_repo = DocumentRepository(settings=settings)
    storage_repo = StorageRepository(settings=settings)
    chat_repo = ChatRepository(settings=settings)
    chroma_repo = ChromaVectorRepository(
        settings=settings,
        ephemeral=True,
        collection_name=f"rag_col_{uuid.uuid4().hex[:8]}",
    )
    emb_service = EmbeddingService(settings=settings)
    pdf_processor = PdfProcessorService(chunk_size_chars=500, chunk_overlap_chars=60)
    ingestion_service = IngestionService(
        settings=settings,
        pdf_processor=pdf_processor,
        embedding_service=emb_service,
        chroma_repo=chroma_repo,
        document_repo=doc_repo,
        storage_repo=storage_repo,
    )
    rag_service = RagService(
        settings=settings,
        embedding_service=emb_service,
        chroma_repo=chroma_repo,
        chat_repo=chat_repo,
    )

    # Seed an English Academic Policy PDF (2 pages) & a Malay Facilities Guide PDF (2 pages)
    academic_pdf = build_pdf(
        [
            "Page 1: Course Registration. Students may add or drop courses during the first two weeks of the semester.",
            "Page 2: Deferment of Study Policy. Applications for deferment of study must be submitted by week four (4) of the semester with an official hospital medical certificate.",
        ]
    )
    facilities_pdf = build_pdf(
        [
            "Halaman 1: Waktu Operasi Perpustakaan Utama. Perpustakaan dibuka setiap hari Isnin hingga Jumaat dari jam 8:00 pagi hingga 10:00 malam.",
            "Halaman 2: Kemudahan Kolej Kediaman dan Asrama. Permohonan bilik asrama dibuka kepada semua pelajar tahun pertama.",
        ]
    )

    doc_acad = ingestion_service.ingest_pdf(
        file_bytes=academic_pdf,
        filename="Academic_Regulations_2026.pdf",
        title="Undergraduate Academic Regulations 2026",
        category="academic",
        language="en",
        uploaded_by="99999999-9999-9999-9999-999999999999",
    )
    doc_fac = ingestion_service.ingest_pdf(
        file_bytes=facilities_pdf,
        filename="Panduan_Kemudahan_Kampus.pdf",
        title="Panduan Kemudahan Kampus 2026",
        category="facilities",
        language="ms",
        uploaded_by="99999999-9999-9999-9999-999999999999",
    )

    app = create_app()
    app.dependency_overrides[get_profile_repository] = lambda: profile_repo
    app.dependency_overrides[get_document_repository] = lambda: doc_repo
    app.dependency_overrides[get_storage_repository] = lambda: storage_repo
    app.dependency_overrides[get_chat_repository] = lambda: chat_repo
    app.dependency_overrides[get_chroma_repository] = lambda: chroma_repo
    app.dependency_overrides[get_embedding_service] = lambda: emb_service
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service
    app.dependency_overrides[get_rag_service] = lambda: rag_service

    return {
        "app": app,
        "doc_acad": doc_acad,
        "doc_fac": doc_fac,
        "rag_service": rag_service,
    }


@pytest.fixture
async def client(rag_env) -> httpx.AsyncClient:
    app: FastAPI = rag_env["app"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def student_a_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        email="aiman@universe.edu.my",
        role="student",
        display_name="Aiman",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_b_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="22222222-2222-2222-2222-222222222222",
        email="sarah@universe.edu.my",
        role="student",
        display_name="Sarah",
    )
    return {"Authorization": f"Bearer {token}"}


def test_citation_sanitizer_strips_out_of_bounds_markers() -> None:
    """Verify out-of-range citation numbers like [5] or [0] are stripped cleanly."""
    raw = "Students must apply by week 4 [1] with a medical report [2] and form [9]."
    sanitized = RagService.sanitize_citation_markers(raw, max_valid_index=2)
    assert "[1]" in sanitized
    assert "[2]" in sanitized
    assert "[9]" not in sanitized


async def test_cross_lingual_malay_query_retrieves_english_policy_page(
    client: httpx.AsyncClient,
    student_a_headers: dict[str, str],
    rag_env: dict,
) -> None:
    """Verify a Malay question about deferment retrieves Page 2 of the English Academic PDF."""
    doc_acad = rag_env["doc_acad"]

    res = await client.post(
        "/api/v1/chat/query",
        headers=student_a_headers,
        json={
            "query": "Bagaimanakah cara memohon penangguhan pengajian atas sebab kesihatan?",
            "language": "auto",
            "category_filter": "academic",
            "stream": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "ms"
    assert data["is_grounded"] is True
    assert "[1]" in data["answer"]
    assert len(data["citations"]) >= 1

    top_citation = data["citations"][0]
    assert top_citation["document_id"] == doc_acad.id
    assert top_citation["page_number"] == 2
    assert f"/api/v1/documents/{doc_acad.id}/file#page=2" == top_citation["file_url"]


async def test_english_query_retrieves_malay_library_guide_page(
    client: httpx.AsyncClient,
    student_a_headers: dict[str, str],
    rag_env: dict,
) -> None:
    """Verify an English question about library operating hours retrieves Page 1 of the Malay Facilities PDF."""
    doc_fac = rag_env["doc_fac"]

    res = await client.post(
        "/api/v1/chat/query",
        headers=student_a_headers,
        json={
            "query": "What are the library operating hours?",
            "language": "auto",
            "category_filter": "facilities",
            "stream": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["detected_language"] == "en"
    assert data["is_grounded"] is True
    assert data["citations"][0]["document_id"] == doc_fac.id
    assert data["citations"][0]["page_number"] == 1


async def test_unanswerable_query_triggers_safe_fallback(
    client: httpx.AsyncClient,
    student_a_headers: dict[str, str],
) -> None:
    """Verify an unrelated question returns `is_grounded=False` and 0 citations instead of hallucinating."""
    res = await client.post(
        "/api/v1/chat/query",
        headers=student_a_headers,
        json={
            "query": "What is the recipe for baking a chocolate sourdough cake on Mars?",
            "language": "en",
            "category_filter": "all",
            "stream": False,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_grounded"] is False
    assert data["citations"] == []
    assert "could not find verified information" in data["answer"].lower()


async def test_sse_streaming_and_session_lifecycle_isolation(
    client: httpx.AsyncClient,
    student_a_headers: dict[str, str],
    student_b_headers: dict[str, str],
) -> None:
    """Verify SSE streaming, session persistence, feedback submission, and cross-user isolation."""
    # 1. Stream a query via SSE
    stream_res = await client.post(
        "/api/v1/chat/query",
        headers=student_a_headers,
        json={
            "query": "When can students add or drop courses?",
            "language": "en",
            "category_filter": "academic",
            "stream": True,
        },
    )
    assert stream_res.status_code == 200
    assert stream_res.headers["content-type"].startswith("text/event-stream")

    events = [
        json.loads(line.removeprefix("data: "))
        for line in stream_res.text.splitlines()
        if line.startswith("data: ")
    ]
    assert len(events) >= 2
    assert events[0]["type"] == "delta"
    done_event = events[-1]
    assert done_event["type"] == "done"
    session_id = done_event["session_id"]
    message_id = done_event["message_id"]

    # 2. Verify session list and detail history for Student A
    sessions_res = await client.get("/api/v1/chat/sessions", headers=student_a_headers)
    assert sessions_res.status_code == 200
    assert sessions_res.json()["total"] == 1

    detail_res = await client.get(
        f"/api/v1/chat/sessions/{session_id}",
        headers=student_a_headers,
    )
    assert detail_res.status_code == 200
    messages = detail_res.json()["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert len(messages[1]["citations"]) >= 1

    # 3. Student B cannot read or delete Student A's session (403 Forbidden)
    forbidden_res = await client.get(
        f"/api/v1/chat/sessions/{session_id}",
        headers=student_b_headers,
    )
    assert forbidden_res.status_code == 403

    # 4. Student A submits thumbs-up feedback on the assistant message
    fb_res = await client.post(
        f"/api/v1/chat/messages/{message_id}/feedback",
        headers=student_a_headers,
        json={"rating": 1, "comment": "Accurate page citation!"},
    )
    assert fb_res.status_code == 200
    assert fb_res.json()["feedback_rating"] == 1

    # 5. Direct semantic search endpoint
    search_res = await client.post(
        "/api/v1/search/semantic",
        headers=student_a_headers,
        json={"query": "kolej kediaman asrama", "category_filter": "facilities", "top_k": 3},
    )
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert search_data["detected_language"] == "ms"
    assert search_data["total"] >= 1
    assert search_data["results"][0]["page_number"] == 2

    # 6. Delete session
    del_res = await client.delete(
        f"/api/v1/chat/sessions/{session_id}",
        headers=student_a_headers,
    )
    assert del_res.status_code == 200
    sessions_after = await client.get("/api/v1/chat/sessions", headers=student_a_headers)
    assert sessions_after.json()["total"] == 0

