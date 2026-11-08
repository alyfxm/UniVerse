"""Multilingual Embedding Service (Gemini API + deterministic local cross-lingual fallback)."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Any

from app.core.config import Settings, get_settings

EMBEDDING_DIMENSION = 256

# Bilingual Campus Concept Equivalence Map (Bahasa Melayu <-> English)
# Enables cross-lingual semantic alignment even when running in offline/local mode.
BILINGUAL_CONCEPT_SYNONYMS: list[tuple[set[str], str]] = [
    (
        {"deferment", "defer", "postpone", "penangguhan", "tangguh", "pengajian", "semester"},
        "concept_deferment_study",
    ),
    (
        {"medical", "health", "hospital", "clinic", "kesihatan", "perubatan", "klinik", "sijil", "mc"},
        "concept_medical_certificate",
    ),
    (
        {"week", "fourth", "deadline", "minggu", "keempat", "tarikh", "akhir", "selewat"},
        "concept_week4_deadline",
    ),
    (
        {"library", "perpustakaan", "book", "buku", "borrow", "pinjam", "operating", "hours", "waktu", "operasi"},
        "concept_library_facility",
    ),
    (
        {"tuition", "fee", "fees", "scholarship", "bursary", "yuran", "biasiswa", "kewangan", "ptptn", "financial"},
        "concept_financial_aid",
    ),
    (
        {"hostel", "accommodation", "dormitory", "kolej", "kediaman", "asrama", "room", "bilik", "housing"},
        "concept_hostel_housing",
    ),
    (
        {"orientation", "convocation", "event", "festival", "orientasi", "konvokesyen", "acara", "program", "aktiviti"},
        "concept_campus_events",
    ),
    (
        {"registration", "course", "add", "drop", "credit", "pendaftaran", "kursus", "subjek", "tambah", "gugur", "kredit"},
        "concept_course_registration",
    ),
    (
        {"exam", "examination", "grade", "cgpa", "gpa", "peperiksaan", "gred", "pngk", "keputusan", "academic"},
        "concept_exam_grading",
    ),
    (
        {"shuttle", "bus", "transport", "parking", "bas", "pengangkutan", "parkir", "jadual"},
        "concept_campus_transport",
    ),
    (
        {"counseling", "counselling", "welfare", "kaunseling", "kebajikan", "mental", "student", "pelajar"},
        "concept_student_counseling",
    ),
]


class EmbeddingService:
    """Generates vector embeddings for documents and queries."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._genai_client: Any = None
        if self.settings.is_gemini_configured:
            try:
                from google import genai

                self._genai_client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
            except Exception:
                self._genai_client = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of document chunks."""
        if not texts:
            return []

        if self._genai_client is not None:
            try:
                response = self._genai_client.models.embed_content(
                    model=self.settings.GEMINI_EMBEDDING_MODEL,
                    contents=texts,
                )
                if response and getattr(response, "embeddings", None):
                    return [list(emb.values) for emb in response.embeddings]
            except Exception:
                pass

        return [self._compute_local_multilingual_embedding(t) for t in texts]

    def embed_query(self, query: str) -> list[float]:
        """Embed a user search query."""
        if self._genai_client is not None:
            try:
                response = self._genai_client.models.embed_content(
                    model=self.settings.GEMINI_EMBEDDING_MODEL,
                    contents=query,
                )
                if response and getattr(response, "embeddings", None):
                    return list(response.embeddings[0].values)
            except Exception:
                pass

        return self._compute_local_multilingual_embedding(query)

    @staticmethod
    def _compute_local_multilingual_embedding(text: str) -> list[float]:
        """Compute L2-normalized hashed feature + bilingual concept vector."""
        vec = [0.0] * EMBEDDING_DIMENSION
        lowered = text.lower()
        tokens = re.findall(r"[a-z0-9]+", lowered)

        if not tokens:
            vec[0] = 1.0
            return vec

        token_set = set(tokens)

        # 1. Inject canonical bilingual concept signals (high weight for cross-lingual alignment)
        for synonyms, concept_tag in BILINGUAL_CONCEPT_SYNONYMS:
            overlap = token_set.intersection(synonyms)
            if overlap:
                digest = hashlib.sha256(concept_tag.encode("utf-8")).digest()
                for i in range(4):
                    bucket = digest[i] % EMBEDDING_DIMENSION
                    sign = 1.0 if (digest[i + 4] % 2 == 0) else -1.0
                    vec[bucket] += sign * (3.5 + 0.5 * len(overlap))

        # 2. Inject unigram & character trigram hashed features
        features: list[tuple[str, float]] = [(tok, 1.5) for tok in tokens]
        for tok in tokens:
            if len(tok) >= 4:
                for idx in range(len(tok) - 2):
                    features.append((f"tri_{tok[idx:idx+3]}", 0.4))

        for feat, weight in features:
            digest = hashlib.md5(feat.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:2], "big") % EMBEDDING_DIMENSION
            sign = 1.0 if (digest[2] % 2 == 0) else -1.0
            vec[bucket] += sign * weight

        # 3. L2 normalize for cosine similarity
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 1e-9:
            vec = [v / norm for v in vec]
        else:
            vec[0] = 1.0
        return vec


_embedding_service_instance: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """FastAPI dependency returning singleton EmbeddingService."""
    global _embedding_service_instance
    if _embedding_service_instance is None:
        _embedding_service_instance = EmbeddingService()
    return _embedding_service_instance

