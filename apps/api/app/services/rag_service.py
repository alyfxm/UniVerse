"""Multilingual RAG Engine with Page-Level Citations, Guardrails, and Bilingual Support."""

from __future__ import annotations

import json
import re
import time
from typing import Any, AsyncGenerator

from fastapi import Depends

from app.core.config import Settings, get_settings
from app.models.chat import (
    CategoryFilter,
    ChatQueryResponse,
    Citation,
    DetectedLanguage,
    QueryLanguagePreference,
)
from app.repositories.chat_repo import ChatRepository, get_chat_repository
from app.repositories.chroma_repo import (
    ChromaVectorRepository,
    RetrievedChunkRecord,
    get_chroma_repository,
)
from app.services.embedding_service import (
    BILINGUAL_CONCEPT_SYNONYMS,
    EmbeddingService,
    get_embedding_service,
)

# High-signal Bahasa Melayu vocabulary markers for fast, accurate language detection
MALAY_MARKERS: set[str] = {
    "apakah",
    "bagaimanakah",
    "bagaimana",
    "bilakah",
    "bila",
    "dimanakah",
    "mana",
    "siapakah",
    "kenapa",
    "mengapa",
    "adakah",
    "boleh",
    "untuk",
    "dalam",
    "dengan",
    "kepada",
    "daripada",
    "pada",
    "yang",
    "dan",
    "atau",
    "tetapi",
    "kerana",
    "jika",
    "pelajar",
    "pengajian",
    "penangguhan",
    "permohonan",
    "memohon",
    "perpustakaan",
    "yuran",
    "biasiswa",
    "asrama",
    "kolej",
    "kediaman",
    "peperiksaan",
    "kursus",
    "subjek",
    "tambah",
    "gugur",
    "minggu",
    "tarikh",
    "waktu",
    "operasi",
    "kesihatan",
    "perubatan",
    "sijil",
    "universiti",
    "kampus",
}

UNANSWERABLE_FALLBACK_EN = (
    "I could not find verified information about that in the official university documents. "
    "Please contact the Student Services Desk or check the official campus portal for assistance."
)

UNANSWERABLE_FALLBACK_MS = (
    "Maaf, saya tidak menemui maklumat yang disahkan mengenai perkara tersebut dalam dokumen rasmi universiti. "
    "Sila hubungi Kaunter Perkhidmatan Pelajar atau semak portal rasmi kampus untuk bantuan lanjut."
)

BILINGUAL_STOPWORDS: set[str] = {
    "the",
    "and",
    "for",
    "with",
    "what",
    "when",
    "where",
    "how",
    "who",
    "why",
    "can",
    "are",
    "from",
    "that",
    "this",
    "have",
    "has",
    "will",
    "there",
    "is",
    "in",
    "on",
    "to",
    "of",
    "at",
    "by",
    "an",
    "or",
    "be",
    "as",
    "do",
    "does",
    "apakah",
    "bagaimanakah",
    "bagaimana",
    "bilakah",
    "bila",
    "dimanakah",
    "mana",
    "siapakah",
    "kenapa",
    "mengapa",
    "adakah",
    "boleh",
    "untuk",
    "dalam",
    "dengan",
    "kepada",
    "daripada",
    "pada",
    "yang",
    "dan",
    "atau",
    "tetapi",
    "kerana",
    "jika",
    "di",
    "ke",
    "ini",
    "itu",
}

MIN_GROUNDING_RELEVANCE_SCORE = 0.56


class RagService:
    """Orchestrates multilingual query expansion, vector retrieval, grounded answer generation, and citation verification."""

    def __init__(
        self,
        settings: Settings,
        embedding_service: EmbeddingService,
        chroma_repo: ChromaVectorRepository,
        chat_repo: ChatRepository,
    ) -> None:
        self.settings = settings
        self.embedding_service = embedding_service
        self.chroma_repo = chroma_repo
        self.chat_repo = chat_repo
        self._genai_client: Any = None
        if self.settings.is_gemini_configured:
            try:
                from google import genai

                self._genai_client = genai.Client(api_key=self.settings.GEMINI_API_KEY)
            except Exception:
                self._genai_client = None

    @staticmethod
    def detect_language(
        query: str,
        preference: QueryLanguagePreference = "auto",
    ) -> DetectedLanguage:
        """Detect whether a student query is in Bahasa Melayu (`ms`) or English (`en`)."""
        if preference in ("en", "ms"):
            return preference

        tokens = re.findall(r"[a-z]+", query.lower())
        if not tokens:
            return "en"

        malay_hits = sum(1 for tok in tokens if tok in MALAY_MARKERS)
        if malay_hits >= 1 and (malay_hits / max(len(tokens), 1) >= 0.15 or malay_hits >= 2):
            return "ms"
        return "en"

    @staticmethod
    def expand_bilingual_query(query: str) -> str:
        """Expand query with cross-lingual MS <-> EN academic/campus equivalents."""
        tokens = set(re.findall(r"[a-z0-9]+", query.lower()))
        expansion_terms: list[str] = []
        for synonyms, _tag in BILINGUAL_CONCEPT_SYNONYMS:
            if tokens.intersection(synonyms):
                expansion_terms.extend(sorted(synonyms))
        if not expansion_terms:
            return query
        return f"{query} {' '.join(expansion_terms)}"

    def retrieve_citations(
        self,
        query: str,
        category_filter: CategoryFilter = "all",
        top_k: int = 4,
    ) -> list[Citation]:
        """Perform bilingual Hybrid Search (Dense + BM25 RRF) and build verified Citation objects."""
        expanded_query = self.expand_bilingual_query(query)
        query_embedding = self.embedding_service.embed_query(expanded_query)

        raw_hits: list[RetrievedChunkRecord] = self.chroma_repo.query_hybrid_rrf(
            query_text=expanded_query,
            query_embedding=query_embedding,
            top_k=top_k,
            category_filter=category_filter,
            active_only=True,
        )

        # Filter out low-relevance noise or chunks with zero meaningful content-word overlap
        query_tokens = {
            tok
            for tok in re.findall(r"[a-z0-9]{2,}", expanded_query.lower())
            if tok not in BILINGUAL_STOPWORDS
        }
        verified_hits: list[RetrievedChunkRecord] = []
        for hit in raw_hits:
            chunk_tokens = {
                tok
                for tok in re.findall(r"[a-z0-9]{2,}", hit.text.lower())
                if tok not in BILINGUAL_STOPWORDS
            }
            lexical_overlap = len(query_tokens.intersection(chunk_tokens))
            if hit.relevance_score >= MIN_GROUNDING_RELEVANCE_SCORE and lexical_overlap >= 1:
                verified_hits.append(hit)

        citations: list[Citation] = []
        for idx, hit in enumerate(verified_hits, start=1):
            file_url = (
                f"{self.settings.API_V1_PREFIX}/documents/{hit.document_id}/file"
                f"#page={hit.page_number}"
            )
            citations.append(
                Citation(
                    citation_index=idx,
                    document_id=hit.document_id,
                    document_title=hit.document_title,
                    category=hit.category,
                    page_number=hit.page_number,
                    snippet=hit.text[:450],
                    relevance_score=hit.relevance_score,
                    file_url=file_url,
                )
            )
        return citations

    @staticmethod
    def sanitize_citation_markers(
        answer_text: str,
        max_valid_index: int,
    ) -> str:
        """Strip any hallucinated `[n]` citation markers where `n < 1` or `n > max_valid_index`."""
        if max_valid_index <= 0:
            return re.sub(r"\s*\[\d+\]", "", answer_text).strip()

        def _replace_marker(match: re.Match[str]) -> str:
            idx = int(match.group(1))
            if 1 <= idx <= max_valid_index:
                return f"[{idx}]"
            return ""

        cleaned = re.sub(r"\[(\d+)\]", _replace_marker, answer_text)
        return re.sub(r" {2,}", " ", cleaned).strip()

    def _synthesize_grounded_answer(
        self,
        query: str,
        target_language: DetectedLanguage,
        citations: list[Citation],
    ) -> tuple[str, bool]:
        """Generate grounded answer with inline [1], [2] citations in target_language."""
        if not citations:
            fallback = (
                UNANSWERABLE_FALLBACK_MS
                if target_language == "ms"
                else UNANSWERABLE_FALLBACK_EN
            )
            return fallback, False

        lang_instruction = (
            "Respond strictly in Bahasa Melayu (Malay)."
            if target_language == "ms"
            else "Respond strictly in English."
        )
        context_blocks = "\n\n".join(
            f"[{c.citation_index}] (Document: {c.document_title}, Page {c.page_number}):\n{c.snippet}"
            for c in citations
        )
        system_prompt = (
            "You are UniVerse, an official university AI campus assistant.\n"
            "RULES:\n"
            "1. Answer the student's question ONLY using the provided context excerpts.\n"
            "2. Cite every factual claim using inline bracket numbers matching the source, e.g. [1] or [2].\n"
            "3. Never invent citation numbers beyond the provided sources.\n"
            "4. If the provided context does not contain the answer, state clearly that the information is not available in the official university documents.\n"
            f"5. {lang_instruction}"
        )
        user_prompt = f"CONTEXT SOURCES:\n{context_blocks}\n\nSTUDENT QUESTION:\n{query}"

        if self._genai_client is not None:
            try:
                response = self._genai_client.models.generate_content(
                    model=self.settings.GEMINI_GENERATION_MODEL,
                    contents=f"{system_prompt}\n\n{user_prompt}",
                )
                raw_answer = (getattr(response, "text", None) or "").strip()
                if raw_answer:
                    sanitized = self.sanitize_citation_markers(raw_answer, len(citations))
                    return sanitized, True
            except Exception:
                pass

        # Deterministic Grounded Synthesis (Offline / Local Test Mode)
        top_citations = citations[:2]
        if target_language == "ms":
            parts = [
                f"Berdasarkan dokumen rasmi universiti ({top_citations[0].document_title}, Halaman {top_citations[0].page_number}):"
            ]
            for c in top_citations:
                parts.append(f"{c.snippet} [{c.citation_index}]")
            synthesized = " ".join(parts)
        else:
            parts = [
                f"According to official university documentation ({top_citations[0].document_title}, Page {top_citations[0].page_number}):"
            ]
            for c in top_citations:
                parts.append(f"{c.snippet} [{c.citation_index}]")
            synthesized = " ".join(parts)

        return self.sanitize_citation_markers(synthesized, len(citations)), True

    def answer_query(
        self,
        user_id: str,
        query: str,
        session_id: str | None = None,
        language_pref: QueryLanguagePreference = "auto",
        category_filter: CategoryFilter = "all",
    ) -> ChatQueryResponse:
        """Process a chat query end-to-end, persist messages, and return cited response."""
        start_time = time.perf_counter()

        detected_lang = self.detect_language(query, preference=language_pref)
        session = self.chat_repo.get_or_create_session(
            session_id=session_id,
            user_id=user_id,
            first_query=query,
            language=detected_lang,
            category_filter=category_filter,
        )

        # Save user message
        self.chat_repo.add_message(
            session_id=session.id,
            role="user",
            content=query,
            detected_language=detected_lang,
            citations=[],
        )

        # Retrieve citations & synthesize answer
        citations = self.retrieve_citations(
            query=query,
            category_filter=category_filter,
            top_k=4,
        )
        answer_text, is_grounded = self._synthesize_grounded_answer(
            query=query,
            target_language=detected_lang,
            citations=citations,
        )
        if not is_grounded:
            citations = []

        latency_ms = max(1, int((time.perf_counter() - start_time) * 1000))

        # Save assistant message with citations
        assistant_msg = self.chat_repo.add_message(
            session_id=session.id,
            role="assistant",
            content=answer_text,
            detected_language=detected_lang,
            citations=citations,
            latency_ms=latency_ms,
        )

        return ChatQueryResponse(
            message_id=assistant_msg.id,
            session_id=session.id,
            answer=answer_text,
            detected_language=detected_lang,
            citations=citations,
            is_grounded=is_grounded,
            latency_ms=latency_ms,
        )

    async def stream_query(
        self,
        user_id: str,
        query: str,
        session_id: str | None = None,
        language_pref: QueryLanguagePreference = "auto",
        category_filter: CategoryFilter = "all",
    ) -> AsyncGenerator[str, None]:
        """Yield Server-Sent Events (SSE) with token chunks followed by final cited payload."""
        result = self.answer_query(
            user_id=user_id,
            query=query,
            session_id=session_id,
            language_pref=language_pref,
            category_filter=category_filter,
        )

        # Stream answer tokens in readable word groups
        words = result.answer.split(" ")
        step = 4
        for idx in range(0, len(words), step):
            chunk_text = " ".join(words[idx : idx + step])
            if idx + step < len(words):
                chunk_text += " "
            delta_event = json.dumps({"type": "delta", "content": chunk_text}, ensure_ascii=False)
            yield f"data: {delta_event}\n\n"

        final_payload = {
            "type": "done",
            **result.model_dump(),
        }
        yield f"data: {json.dumps(final_payload, ensure_ascii=False)}\n\n"


def get_rag_service(
    settings: Settings = Depends(get_settings),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    chroma_repo: ChromaVectorRepository = Depends(get_chroma_repository),
    chat_repo: ChatRepository = Depends(get_chat_repository),
) -> RagService:
    """FastAPI dependency returning RagService."""
    return RagService(
        settings=settings,
        embedding_service=embedding_service,
        chroma_repo=chroma_repo,
        chat_repo=chat_repo,
    )
