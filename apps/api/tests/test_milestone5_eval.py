"""Unit and Integration Tests for Milestone 5:
- Golden Dataset validation (`eval/golden_dataset.json`)
- RAG Evaluation Engine metrics (`faithfulness`, `answer_relevance`, `context_recall`, `citation_accuracy`)
- Admin Evaluation endpoints (`POST /api/v1/admin/eval/run`, `GET /api/v1/admin/eval/runs`)
- RBAC protection (students cannot trigger evaluation runs)
- Demo token issuer (`POST /api/v1/auth/demo-token`)
"""

from __future__ import annotations

from pathlib import Path
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.core.security import create_supabase_jwt
from app.main import create_app
from app.repositories.chat_repo import ChatRepository, get_chat_repository
from app.repositories.chroma_repo import ChromaVectorRepository, get_chroma_repository
from app.repositories.document_repo import DocumentRepository, get_document_repository
from app.repositories.eval_repo import EvalRepository, get_eval_repository
from app.repositories.profile_repo import ProfileRepository, get_profile_repository
from app.repositories.storage_repo import StorageRepository, get_storage_repository
from app.services.embedding_service import EmbeddingService, get_embedding_service
from app.services.eval_service import RagEvaluationService, get_eval_service
from app.services.ingestion_service import IngestionService, get_ingestion_service
from app.services.pdf_processor import PdfProcessorService
from app.services.rag_service import RagService, get_rag_service


@pytest.fixture
def eval_env(tmp_path: Path):
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
    eval_repo = EvalRepository(settings=settings)
    chroma_repo = ChromaVectorRepository(
        settings=settings,
        ephemeral=True,
        collection_name=f"eval_col_{uuid.uuid4().hex[:8]}",
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
    eval_service = RagEvaluationService(
        rag_service=rag_service,
        ingestion_service=ingestion_service,
        eval_repo=eval_repo,
    )

    app = create_app()
    app.dependency_overrides[get_profile_repository] = lambda: profile_repo
    app.dependency_overrides[get_document_repository] = lambda: doc_repo
    app.dependency_overrides[get_storage_repository] = lambda: storage_repo
    app.dependency_overrides[get_chat_repository] = lambda: chat_repo
    app.dependency_overrides[get_eval_repository] = lambda: eval_repo
    app.dependency_overrides[get_chroma_repository] = lambda: chroma_repo
    app.dependency_overrides[get_embedding_service] = lambda: emb_service
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion_service
    app.dependency_overrides[get_rag_service] = lambda: rag_service
    app.dependency_overrides[get_eval_service] = lambda: eval_service

    return {"app": app, "eval_service": eval_service}


@pytest.fixture
async def client(eval_env) -> httpx.AsyncClient:
    app: FastAPI = eval_env["app"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def admin_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="99999999-9999-9999-9999-999999999999",
        email="admin@universe.edu.my",
        role="admin",
        display_name="Campus Admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_headers() -> dict[str, str]:
    token = create_supabase_jwt(
        user_id="11111111-1111-1111-1111-111111111111",
        email="student@universe.edu.my",
        role="student",
        display_name="Student",
    )
    return {"Authorization": f"Bearer {token}"}


async def test_student_cannot_run_or_view_evaluations(
    client: httpx.AsyncClient,
    student_headers: dict[str, str],
) -> None:
    """Verify student role receives 403 Forbidden on `/api/v1/admin/eval/*`."""
    res_run = await client.post("/api/v1/admin/eval/run", headers=student_headers)
    assert res_run.status_code == 403

    res_list = await client.get("/api/v1/admin/eval/runs", headers=student_headers)
    assert res_list.status_code == 403


async def test_full_bilingual_rag_evaluation_benchmark(
    client: httpx.AsyncClient,
    admin_headers: dict[str, str],
) -> None:
    """Verify running the RAG evaluation suite achieves high faithfulness, recall, and page citation accuracy."""
    run_res = await client.post("/api/v1/admin/eval/run", headers=admin_headers)
    assert run_res.status_code == 201
    summary = run_res.json()

    assert summary["total_questions"] == 5
    assert summary["avg_faithfulness"] >= 0.85
    assert summary["avg_context_recall"] >= 0.80
    assert summary["avg_citation_accuracy"] >= 0.85
    assert all(c["passed"] is True for c in summary["case_results"])

    # Verify history endpoint returns the stored evaluation run
    list_res = await client.get("/api/v1/admin/eval/runs", headers=admin_headers)
    assert list_res.status_code == 200
    runs_data = list_res.json()
    assert runs_data["total"] == 1
    assert runs_data["runs"][0]["id"] == summary["id"]


async def test_demo_token_issuer_endpoint(client: httpx.AsyncClient) -> None:
    """Verify `/api/v1/auth/demo-token` issues valid JWTs for local Student and Admin testing."""
    res = await client.post(
        "/api/v1/auth/demo-token",
        json={"role": "admin", "preferred_language": "ms"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user"]["role"] == "admin"
    assert body["user"]["preferred_language"] == "ms"
    assert len(body["access_token"]) > 20

