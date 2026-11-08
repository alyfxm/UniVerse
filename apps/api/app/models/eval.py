"""Pydantic models for RAG Evaluation runs and benchmark metrics."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from app.models.documents import DocumentCategory


class GoldenBenchmarkCase(BaseModel):
    """Represents a single test case in `eval/golden_dataset.json`."""

    case_id: str
    language: Literal["en", "ms"]
    category: DocumentCategory
    question: str
    expected_page: int = Field(..., ge=1)
    expected_keywords: list[str]
    reference_facts: str


class EvalCaseResult(BaseModel):
    """Evaluation scores for an individual benchmark question."""

    case_id: str
    language: Literal["en", "ms"]
    category: DocumentCategory
    question: str
    expected_page: int
    retrieved_pages: list[int]
    answer: str
    faithfulness: float = Field(..., ge=0.0, le=1.0)
    answer_relevance: float = Field(..., ge=0.0, le=1.0)
    context_recall: float = Field(..., ge=0.0, le=1.0)
    citation_accuracy: float = Field(..., ge=0.0, le=1.0)
    passed: bool


class EvalRunSummary(BaseModel):
    """Represents a completed evaluation run in `public.eval_runs`."""

    id: str
    triggered_by: str | None = None
    total_questions: int = Field(..., ge=0)
    avg_faithfulness: float = Field(..., ge=0.0, le=1.0)
    avg_answer_relevance: float = Field(..., ge=0.0, le=1.0)
    avg_context_recall: float = Field(..., ge=0.0, le=1.0)
    avg_citation_accuracy: float = Field(..., ge=0.0, le=1.0)
    case_results: list[EvalCaseResult] = Field(default_factory=list)
    created_at: datetime


class EvalRunListResponse(BaseModel):
    """Response payload for `GET /api/v1/admin/eval/runs`."""

    runs: list[EvalRunSummary]
    total: int

