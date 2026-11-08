"""RAG Evaluation Framework measuring Faithfulness, Answer Relevance, Context Recall, and Citation Accuracy."""

from __future__ import annotations

import json
from pathlib import Path
import re

from fastapi import Depends
import pymupdf as fitz

from app.models.chat import Citation
from app.models.eval import EvalCaseResult, EvalRunSummary, GoldenBenchmarkCase
from app.repositories.eval_repo import EvalRepository, get_eval_repository
from app.services.ingestion_service import IngestionService, get_ingestion_service
from app.services.rag_service import BILINGUAL_STOPWORDS, RagService, get_rag_service

DEFAULT_GOLDEN_DATASET_PATH = (
    Path(__file__).resolve().parents[2] / "eval" / "golden_dataset.json"
)


class RagEvaluationService:
    """Executes automated RAG quality benchmarks on the bilingual campus golden dataset."""

    def __init__(
        self,
        rag_service: RagService,
        ingestion_service: IngestionService,
        eval_repo: EvalRepository,
        dataset_path: Path | None = None,
    ) -> None:
        self.rag_service = rag_service
        self.ingestion_service = ingestion_service
        self.eval_repo = eval_repo
        self.dataset_path = dataset_path or DEFAULT_GOLDEN_DATASET_PATH

    def load_golden_dataset(self) -> list[GoldenBenchmarkCase]:
        """Load and validate the bilingual golden benchmark dataset."""
        raw_text = self.dataset_path.read_text(encoding="utf-8")
        raw_items = json.loads(raw_text)
        return [GoldenBenchmarkCase(**item) for item in raw_items]

    def ensure_sample_corpus_seeded(self, admin_user_id: str | None = None) -> None:
        """Seed official bilingual reference PDFs if the vector store is currently empty."""
        if self.ingestion_service.chroma_repo.count_chunks() > 0:
            return

        academic_pdf = self._build_pdf(
            [
                "Undergraduate Academic Regulations 2026 - Page 1: Course Registration. "
                "Students may add or drop courses (tambah dan gugur kursus) during the first two (2) weeks of the semester.",
                "Undergraduate Academic Regulations 2026 - Page 2: Deferment of Study Policy (Penangguhan Pengajian). "
                "Applications for deferment of study must be submitted by week four (4) of the semester via the student portal. "
                "Medical deferment requires an official hospital medical certificate (sijil perubatan rasmi).",
            ]
        )
        facilities_pdf = self._build_pdf(
            [
                "Panduan Kemudahan Kampus 2026 - Halaman 1: Waktu Operasi Perpustakaan Utama (Main Library Operating Hours). "
                "Perpustakaan dibuka setiap hari Isnin hingga Jumaat dari jam 8:00 pagi hingga 10:00 malam.",
                "Panduan Kemudahan Kampus 2026 - Halaman 2: Kemudahan Kolej Kediaman dan Asrama (Hostel Accommodation). "
                "Permohonan bilik kolej kediaman asrama dibuka kepada semua pelajar tahun pertama (first-year undergraduate students).",
            ]
        )

        for filename, title, cat, lang, pdf_bytes in [
            (
                "Academic_Regulations_2026.pdf",
                "Undergraduate Academic Regulations 2026",
                "academic",
                "bilingual",
                academic_pdf,
            ),
            (
                "Panduan_Kemudahan_Kampus_2026.pdf",
                "Panduan Kemudahan Kampus 2026",
                "facilities",
                "bilingual",
                facilities_pdf,
            ),
        ]:
            try:
                self.ingestion_service.ingest_pdf(
                    file_bytes=pdf_bytes,
                    filename=filename,
                    title=title,
                    category=cat,  # type: ignore[arg-type]
                    language=lang,  # type: ignore[arg-type]
                    uploaded_by=admin_user_id,
                )
            except Exception:
                pass

    @staticmethod
    def _build_pdf(pages_text: list[str]) -> bytes:
        doc = fitz.open()
        rect = fitz.Rect(72, 72, 520, 750)
        for page_content in pages_text:
            page = doc.new_page()
            page.insert_textbox(rect, page_content, fontsize=11)
        data = doc.tobytes()
        doc.close()
        return data

    @staticmethod
    def compute_faithfulness(answer: str, citations: list[Citation]) -> float:
        """Compute fraction of answer content tokens grounded in the retrieved context snippets."""
        if not citations or not answer.strip():
            return 0.0

        # Strip generic framing prefixes so we measure factual content overlap
        stripped_answer = re.sub(
            r"^(According to official university documentation.*?:|Berdasarkan dokumen rasmi universiti.*?:)\s*",
            "",
            answer,
            flags=re.IGNORECASE,
        )
        answer_tokens = [
            tok
            for tok in re.findall(r"[a-z0-9]{3,}", stripped_answer.lower())
            if tok not in BILINGUAL_STOPWORDS
        ]
        if not answer_tokens:
            return 1.0

        context_corpus = " ".join(
            f"{c.document_title} {c.snippet}" for c in citations
        ).lower()
        context_tokens = set(re.findall(r"[a-z0-9]{3,}", context_corpus))

        grounded_count = sum(1 for tok in answer_tokens if tok in context_tokens)
        return round(min(1.0, grounded_count / len(answer_tokens)), 4)

    @staticmethod
    def compute_context_recall(
        expected_keywords: list[str],
        citations: list[Citation],
    ) -> float:
        """Compute fraction of expected benchmark concepts/keywords present in retrieved chunks."""
        if not expected_keywords:
            return 1.0
        if not citations:
            return 0.0

        combined_context = " ".join(c.snippet for c in citations).lower()
        hits = sum(
            1 for kw in expected_keywords if kw.lower() in combined_context
        )
        # In bilingual tests, matching at least half of the bilingual keyword set indicates full concept recall
        target_hits = max(1, (len(expected_keywords) + 1) // 2)
        return round(min(1.0, hits / target_hits), 4)

    @staticmethod
    def compute_answer_relevance(
        question: str,
        reference_facts: str,
        answer: str,
        expected_keywords: list[str],
    ) -> float:
        """Evaluate whether the synthesized answer directly addresses the question and reference facts."""
        if not answer.strip():
            return 0.0

        lowered_answer = answer.lower()
        kw_hits = sum(1 for kw in expected_keywords if kw.lower() in lowered_answer)
        kw_score = min(1.0, kw_hits / max(1, (len(expected_keywords) + 1) // 2))

        ref_tokens = {
            tok
            for tok in re.findall(r"[a-z0-9]{3,}", f"{question} {reference_facts}".lower())
            if tok not in BILINGUAL_STOPWORDS
        }
        ans_tokens = {
            tok
            for tok in re.findall(r"[a-z0-9]{3,}", lowered_answer)
            if tok not in BILINGUAL_STOPWORDS
        }
        overlap_score = (
            min(1.0, len(ref_tokens.intersection(ans_tokens)) / max(1, len(ref_tokens) // 2))
            if ref_tokens
            else 1.0
        )
        return round((0.6 * kw_score) + (0.4 * overlap_score), 4)

    @staticmethod
    def compute_citation_accuracy(
        answer: str,
        citations: list[Citation],
        expected_page: int,
    ) -> float:
        """Verify inline `[n]` markers are valid AND retrieved citations point to `expected_page`."""
        if not citations:
            return 0.0

        inline_markers = [int(m) for m in re.findall(r"\[(\d+)\]", answer)]
        if not inline_markers:
            return 0.0

        valid_markers = all(1 <= idx <= len(citations) for idx in inline_markers)
        marker_score = 1.0 if valid_markers else 0.0

        retrieved_pages = [c.page_number for c in citations]
        if retrieved_pages[0] == expected_page:
            page_score = 1.0
        elif expected_page in retrieved_pages:
            page_score = 0.85
        else:
            page_score = 0.0

        return round((0.5 * marker_score) + (0.5 * page_score), 4)

    def run_evaluation(self, triggered_by: str | None = None) -> EvalRunSummary:
        """Execute all golden dataset questions through RAG and record evaluation metrics."""
        self.ensure_sample_corpus_seeded(admin_user_id=triggered_by)
        cases = self.load_golden_dataset()
        case_results: list[EvalCaseResult] = []

        for case in cases:
            citations = self.rag_service.retrieve_citations(
                query=case.question,
                category_filter=case.category,
                top_k=3,
            )
            answer, _is_grounded = self.rag_service._synthesize_grounded_answer(
                query=case.question,
                target_language=case.language,
                citations=citations,
            )

            faithfulness = self.compute_faithfulness(answer, citations)
            context_recall = self.compute_context_recall(case.expected_keywords, citations)
            answer_relevance = self.compute_answer_relevance(
                question=case.question,
                reference_facts=case.reference_facts,
                answer=answer,
                expected_keywords=case.expected_keywords,
            )
            citation_accuracy = self.compute_citation_accuracy(
                answer=answer,
                citations=citations,
                expected_page=case.expected_page,
            )

            passed = (
                faithfulness >= 0.75
                and context_recall >= 0.70
                and citation_accuracy >= 0.75
            )

            case_results.append(
                EvalCaseResult(
                    case_id=case.case_id,
                    language=case.language,
                    category=case.category,
                    question=case.question,
                    expected_page=case.expected_page,
                    retrieved_pages=[c.page_number for c in citations],
                    answer=answer,
                    faithfulness=faithfulness,
                    answer_relevance=answer_relevance,
                    context_recall=context_recall,
                    citation_accuracy=citation_accuracy,
                    passed=passed,
                )
            )

        total = len(case_results)
        avg_faith = sum(c.faithfulness for c in case_results) / max(1, total)
        avg_rel = sum(c.answer_relevance for c in case_results) / max(1, total)
        avg_rec = sum(c.context_recall for c in case_results) / max(1, total)
        avg_cit = sum(c.citation_accuracy for c in case_results) / max(1, total)

        return self.eval_repo.save_eval_run(
            triggered_by=triggered_by,
            total_questions=total,
            avg_faithfulness=avg_faith,
            avg_answer_relevance=avg_rel,
            avg_context_recall=avg_rec,
            avg_citation_accuracy=avg_cit,
            case_results=case_results,
        )


def get_eval_service(
    rag_service: RagService = Depends(get_rag_service),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
    eval_repo: EvalRepository = Depends(get_eval_repository),
) -> RagEvaluationService:
    """FastAPI dependency returning RagEvaluationService."""
    return RagEvaluationService(
        rag_service=rag_service,
        ingestion_service=ingestion_service,
        eval_repo=eval_repo,
    )
