"""Admin RAG Evaluation endpoints (`/api/v1/admin/eval`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.security import require_admin
from app.models.auth import UserProfile
from app.models.eval import EvalRunListResponse, EvalRunSummary
from app.repositories.eval_repo import EvalRepository, get_eval_repository
from app.services.eval_service import RagEvaluationService, get_eval_service

router = APIRouter(prefix="/admin/eval", tags=["Admin Evaluation"])


@router.post("/run", response_model=EvalRunSummary, status_code=status.HTTP_201_CREATED)
async def trigger_rag_evaluation(
    admin_user: UserProfile = Depends(require_admin),
    eval_service: RagEvaluationService = Depends(get_eval_service),
) -> EvalRunSummary:
    """Execute the bilingual RAG evaluation suite and persist metrics to `public.eval_runs`."""
    return eval_service.run_evaluation(triggered_by=admin_user.id)


@router.get("/runs", response_model=EvalRunListResponse)
async def list_rag_evaluation_runs(
    _admin_user: UserProfile = Depends(require_admin),
    eval_repo: EvalRepository = Depends(get_eval_repository),
) -> EvalRunListResponse:
    """List historical RAG evaluation runs and per-question breakdowns."""
    runs = eval_repo.list_eval_runs()
    return EvalRunListResponse(runs=runs, total=len(runs))

