"""Unit and Integration Tests for Enterprise Evolution Phases 1-5:
- Phase 1: Hybrid Search (BM25 + Dense Vector RRF) exact course code lookup (`CSC3100`, `DK-B`), table extraction, and ingestion job tracking
- Phase 2: Visual PDF Page Citation Highlighter (`GET /api/v1/documents/{doc_id}/pages/{page}/preview` returning PNG data URI + normalized highlight bounding boxes)
- Phase 3: Omnichannel WhatsApp & Telegram Bot Gateway (`POST /api/v1/integrations/omnichannel/webhook`)
- Phase 4: Student SIS Personalization & Agentic Workflows (`GET /api/v1/student/sis-profile`, Advisor Booking, Pre-filled Deferment PDF generation, `.ics` Academic Calendar export)
- Phase 5: Institutional Analytics & Knowledge Gap Detection (`GET /api/v1/admin/analytics/summary`)
"""

from __future__ import annotations

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
from app.services.enterprise_service import (
    EnterpriseCampusService,
    get_enterprise_service,
)
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
def enterprise_env(tmp_path: Path):
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
        collection_name=f"ent_col_{uuid.uuid4().hex[:8]}",
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
    enterprise_service = EnterpriseCampusService(
        rag_service=rag_service,
        chat_repo=chat_repo,
    )

    # Seed a 2-page PDF containing exact alphanumeric course codes (CSC3100, DK-B) & deferment rules
    handbook_pdf = build_pdf(
        [
            "Page 1: General Elective Directory. Introductory computing classes are held every Monday.",
            "Page 2: Advanced Course Schedule. The course CSC3100 Distributed Systems is conducted in Lecture Hall DK-B every Wednesday at 10:00 AM. Deferment of study applications must be submitted by Week 4.",
        ]
    )
    seeded_doc = ingestion_service.ingest_pdf(
        file_bytes=handbook_pdf,
        filename="Course_Schedule_2026.pdf",
        title="Faculty Course Schedule & Policy 2026",
        category="academic",
        language="bilingual",
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
    app.dependency_overrides[get_enterprise_service] = lambda: enterprise_service

    return {"app": app, "seeded_doc": seeded_doc}


@pytest.fixture
async def client(enterprise_env) -> httpx.AsyncClient:
    app: FastAPI = enterprise_env["app"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def student_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        email="aiman@student.universe.edu.my",
        role="student",
        display_name="Aiman Hakim",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="99999999-9999-9999-9999-999999999999",
        email="admin@universe.edu.my",
        role="admin",
        display_name="Campus Admin",
    )
    return {"Authorization": f"Bearer {token}"}


async def test_phase1_and_2_hybrid_search_job_tracker_and_visual_highlight_preview(
    client: httpx.AsyncClient,
    student_headers: dict[str, str],
    admin_headers: dict[str, str],
    enterprise_env: dict,
) -> None:
    """Verify Hybrid RRF exact code retrieval (`CSC3100`), job progress tracker, and visual bounding-box highlight PNG preview."""
    seeded_doc = enterprise_env["seeded_doc"]

    # 1. Check ingestion job stage tracking for seeded_doc
    job_res = await client.get(
        f"/api/v1/admin/documents/jobs/{seeded_doc.id}",
        headers=admin_headers,
    )
    assert job_res.status_code == 200
    job_data = job_res.json()
    assert job_data["stage"] == "completed"
    assert job_data["progress_percent"] == 100

    # 2. Hybrid Search (BM25 + Dense RRF) finds exact course code `CSC3100` on Page 2
    chat_res = await client.post(
        "/api/v1/chat/query",
        headers=student_headers,
        json={
            "query": "Where is CSC3100 conducted?",
            "language": "en",
            "category_filter": "academic",
        },
    )
    assert chat_res.status_code == 200
    chat_data = chat_res.json()
    assert chat_data["is_grounded"] is True
    assert chat_data["citations"][0]["page_number"] == 2
    assert "DK-B" in chat_data["citations"][0]["snippet"]

    # 3. Phase 2: Request visual bounding-box highlight preview for Page 2
    preview_res = await client.get(
        f"/api/v1/documents/{seeded_doc.id}/pages/2/preview",
        params={"highlight": "CSC3100 Distributed Systems is conducted in Lecture Hall DK-B"},
        headers=student_headers,
    )
    assert preview_res.status_code == 200
    preview = preview_res.json()
    assert preview["page_number"] == 2
    assert preview["image_data_url"].startswith("data:image/png;base64,")
    assert len(preview["highlight_boxes"]) >= 1


async def test_phase3_omnichannel_whatsapp_and_telegram_gateway(
    client: httpx.AsyncClient,
) -> None:
    """Verify WhatsApp & Telegram webhook gateway processes student messages and appends mobile citations."""
    wa_res = await client.post(
        "/api/v1/integrations/omnichannel/webhook",
        json={
            "channel": "whatsapp",
            "external_user_id": "+60123456789",
            "student_name": "Aiman",
            "text": "Bilakah tarikh akhir permohonan penangguhan pengajian?",
        },
    )
    assert wa_res.status_code == 200
    wa_data = wa_res.json()
    assert wa_data["channel"] == "whatsapp"
    assert wa_data["detected_language"] == "ms"
    assert wa_data["is_grounded"] is True
    assert "Rujukan Rasmi" in wa_data["reply_text"]
    assert "(p.2)" in wa_data["reply_text"]


async def test_phase4_sis_profile_and_agentic_workflows(
    client: httpx.AsyncClient,
    student_headers: dict[str, str],
) -> None:
    """Verify SIS academic profile, Advisor Booking tool, Auto-Filled Deferment PDF tool, and .ics Calendar export."""
    # 1. SIS Profile
    sis_res = await client.get("/api/v1/student/sis-profile", headers=student_headers)
    assert sis_res.status_code == 200
    sis = sis_res.json()
    assert sis["matric_number"] == "U20251048"
    assert sis["cgpa"] == 3.74

    # 2. Book Academic Advisor Appointment
    book_res = await client.post(
        "/api/v1/student/agent/book-advisor",
        headers=student_headers,
        json={
            "topic": "Elective Registration for CSC3201 Machine Learning",
            "preferred_slot": "Friday, 10:00 - 10:30 MYT",
        },
    )
    assert book_res.status_code == 201
    apt = book_res.json()
    assert apt["status"] == "confirmed"
    assert apt["matric_number"] == "U20251048"

    # 3. Generate Pre-Filled Deferment Application PDF
    pdf_res = await client.post(
        "/api/v1/student/agent/deferment-form/pdf",
        headers=student_headers,
        json={
            "reason_category": "medical",
            "supporting_details": "Hospital Kuala Lumpur medical certificate attached.",
        },
    )
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")

    # 4. Export Academic Deadlines (.ics)
    ics_res = await client.get(
        "/api/v1/student/agent/deadlines.ics",
        headers=student_headers,
    )
    assert ics_res.status_code == 200
    assert "BEGIN:VCALENDAR" in ics_res.text
    assert "Deferment of Study Application Deadline" in ics_res.text


async def test_phase5_institutional_analytics_and_knowledge_gap_detection(
    client: httpx.AsyncClient,
    student_headers: dict[str, str],
    admin_headers: dict[str, str],
) -> None:
    """Verify Institutional Analytics computes grounding rate, ticket deflection ROI, and clusters unanswered queries."""
    # 1. Ask one answerable question and one unanswerable question
    await client.post(
        "/api/v1/chat/query",
        headers=student_headers,
        json={"query": "Where is CSC3100 conducted?", "language": "en"},
    )
    await client.post(
        "/api/v1/chat/query",
        headers=student_headers,
        json={"query": "Is there an overnight submarine ferry to Borneo campus?", "language": "en"},
    )

    # 2. Fetch Admin Institutional Analytics Summary
    analytics_res = await client.get(
        "/api/v1/admin/analytics/summary",
        headers=admin_headers,
    )
    assert analytics_res.status_code == 200
    summary = analytics_res.json()
    assert summary["total_student_queries"] >= 2
    assert summary["grounded_answers_count"] >= 1
    assert summary["unanswered_queries_count"] >= 1
    assert summary["estimated_tickets_deflected"] >= 1
    assert any(
        "submarine ferry" in gap["query"].lower()
        for gap in summary["knowledge_gaps"]
    )

