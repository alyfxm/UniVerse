"""Repository for persisting RAG evaluation runs in `public.eval_runs` (with local fallback)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import uuid

from app.core.config import Settings, get_settings
from app.models.eval import EvalCaseResult, EvalRunSummary


class EvalRepository:
    """Data access layer for `public.eval_runs`."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._local_runs: dict[str, EvalRunSummary] = {}
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

    def save_eval_run(
        self,
        triggered_by: str | None,
        total_questions: int,
        avg_faithfulness: float,
        avg_answer_relevance: float,
        avg_context_recall: float,
        avg_citation_accuracy: float,
        case_results: list[EvalCaseResult],
    ) -> EvalRunSummary:
        """Persist a completed evaluation run."""
        run_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        run_summary = EvalRunSummary(
            id=run_id,
            triggered_by=triggered_by,
            total_questions=total_questions,
            avg_faithfulness=round(avg_faithfulness, 4),
            avg_answer_relevance=round(avg_answer_relevance, 4),
            avg_context_recall=round(avg_context_recall, 4),
            avg_citation_accuracy=round(avg_citation_accuracy, 4),
            case_results=case_results,
            created_at=now,
        )

        if self._supabase_client is not None:
            payload = {
                "id": run_summary.id,
                "triggered_by": run_summary.triggered_by,
                "total_questions": run_summary.total_questions,
                "avg_faithfulness": run_summary.avg_faithfulness,
                "avg_answer_relevance": run_summary.avg_answer_relevance,
                "avg_context_recall": run_summary.avg_context_recall,
                "avg_citation_accuracy": run_summary.avg_citation_accuracy,
                "case_results": [c.model_dump() for c in case_results],
                "created_at": now.isoformat(),
            }
            res = self._supabase_client.table("eval_runs").insert(payload).execute()
            rows = res.data or [payload]
            return self._row_to_model(rows[0])

        self._local_runs[run_id] = run_summary
        return run_summary

    def list_eval_runs(self, limit: int = 20) -> list[EvalRunSummary]:
        """List historical evaluation runs ordered by `created_at DESC`."""
        if self._supabase_client is not None:
            res = (
                self._supabase_client.table("eval_runs")
                .select("*")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return [self._row_to_model(r) for r in (res.data or [])]

        runs = list(self._local_runs.values())
        runs.sort(key=lambda r: r.created_at, reverse=True)
        return runs[:limit]

    @staticmethod
    def _row_to_model(row: dict[str, Any]) -> EvalRunSummary:
        raw_cases = row.get("case_results") or []
        cases = [
            EvalCaseResult(**c) if isinstance(c, dict) else c for c in raw_cases
        ]
        return EvalRunSummary(
            id=str(row["id"]),
            triggered_by=str(row["triggered_by"]) if row.get("triggered_by") else None,
            total_questions=int(row["total_questions"]),
            avg_faithfulness=float(row["avg_faithfulness"]),
            avg_answer_relevance=float(row["avg_answer_relevance"]),
            avg_context_recall=float(row["avg_context_recall"]),
            avg_citation_accuracy=float(row["avg_citation_accuracy"]),
            case_results=cases,
            created_at=row["created_at"],
        )


_eval_repo_instance: EvalRepository | None = None


def get_eval_repository() -> EvalRepository:
    """FastAPI dependency returning singleton EvalRepository."""
    global _eval_repo_instance
    if _eval_repo_instance is None:
        _eval_repo_instance = EvalRepository()
    return _eval_repo_instance

