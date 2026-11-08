"""ChromaDB Vector Store Repository for indexing, metadata filtering, and lifecycle sync."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.core.config import Settings, get_settings
from app.models.documents import DocumentChunk


@dataclass
class RetrievedChunkRecord:
    """Represents a single vector search hit with metadata and similarity score."""

    chunk_id: str
    document_id: str
    document_title: str
    category: str
    language: str
    page_number: int
    chunk_index: int
    text: str
    relevance_score: float


class ChromaVectorRepository:
    """Data access layer wrapping ChromaDB collection operations."""

    def __init__(
        self,
        settings: Settings | None = None,
        ephemeral: bool = False,
        collection_name: str | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        target_collection = collection_name or self.settings.CHROMA_COLLECTION_NAME

        if ephemeral:
            self._client = chromadb.EphemeralClient(
                settings=ChromaSettings(anonymized_telemetry=False)
            )
        else:
            self.settings.ensure_directories()
            self._client = chromadb.PersistentClient(
                path=self.settings.CHROMA_PERSIST_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )

        self._collection = self._client.get_or_create_collection(
            name=target_collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> int:
        """Insert or update document chunks and their vector embeddings in ChromaDB."""
        if not chunks:
            return 0

        ids = [c.chunk_id for c in chunks]
        documents = [c.text for c in chunks]
        metadatas: list[dict[str, str | int | float | bool]] = [
            {
                "document_id": c.document_id,
                "document_title": c.document_title,
                "category": c.category,
                "language": c.language,
                "page_number": c.page_number,
                "chunk_index": c.chunk_index,
                "char_start": c.char_start,
                "char_end": c.char_end,
                "is_active": c.is_active,
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        return len(chunks)

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        category_filter: str | None = None,
        document_id_filter: str | None = None,
        active_only: bool = True,
    ) -> list[RetrievedChunkRecord]:
        """Search ChromaDB for top_k chunks matching metadata filters."""
        total_count = self._collection.count()
        if total_count == 0:
            return []

        conditions: list[dict[str, Any]] = []
        if active_only:
            conditions.append({"is_active": True})
        if category_filter and category_filter != "all":
            conditions.append({"category": category_filter})
        if document_id_filter:
            conditions.append({"document_id": document_id_filter})

        where_clause: dict[str, Any] | None = None
        if len(conditions) == 1:
            where_clause = conditions[0]
        elif len(conditions) > 1:
            where_clause = {"$and": conditions}

        n_results = min(top_k, total_count)
        query_kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_clause is not None:
            query_kwargs["where"] = where_clause

        try:
            result = self._collection.query(**query_kwargs)
        except Exception:
            return []

        ids_list = (result.get("ids") or [[]])[0]
        docs_list = (result.get("documents") or [[]])[0]
        metas_list = (result.get("metadatas") or [[]])[0]
        dists_list = (result.get("distances") or [[]])[0]

        records: list[RetrievedChunkRecord] = []
        for chunk_id, doc_text, meta, distance in zip(
            ids_list, docs_list, metas_list, dists_list
        ):
            if meta is None or doc_text is None:
                continue
            # Cosine distance in Chroma is in [0, 2]; convert to similarity in [0, 1]
            similarity = max(0.0, min(1.0, 1.0 - (float(distance) / 2.0)))
            records.append(
                RetrievedChunkRecord(
                    chunk_id=str(chunk_id),
                    document_id=str(meta.get("document_id", "")),
                    document_title=str(meta.get("document_title", "Untitled Document")),
                    category=str(meta.get("category", "general")),
                    language=str(meta.get("language", "en")),
                    page_number=int(meta.get("page_number", 1)),
                    chunk_index=int(meta.get("chunk_index", 0)),
                    text=str(doc_text),
                    relevance_score=round(similarity, 4),
                )
            )

        return records

    def query_hybrid_rrf(
        self,
        query_text: str,
        query_embedding: list[float],
        top_k: int = 5,
        category_filter: str | None = None,
        document_id_filter: str | None = None,
        active_only: bool = True,
        rrf_k: int = 60,
    ) -> list[RetrievedChunkRecord]:
        """Hybrid Search combining Dense Vector similarity + Okapi BM25 Lexical Search via Reciprocal Rank Fusion (RRF)."""
        total_count = self._collection.count()
        if total_count == 0:
            return []

        # 1. Dense Candidate Pool
        dense_pool_size = min(max(top_k * 4, 15), total_count)
        dense_hits = self.query_similar(
            query_embedding=query_embedding,
            top_k=dense_pool_size,
            category_filter=category_filter,
            document_id_filter=document_id_filter,
            active_only=active_only,
        )

        # 2. Fetch filtered corpus for BM25 lexical scoring
        conditions: list[dict[str, Any]] = []
        if active_only:
            conditions.append({"is_active": True})
        if category_filter and category_filter != "all":
            conditions.append({"category": category_filter})
        if document_id_filter:
            conditions.append({"document_id": document_id_filter})

        where_clause: dict[str, Any] | None = None
        if len(conditions) == 1:
            where_clause = conditions[0]
        elif len(conditions) > 1:
            where_clause = {"$and": conditions}

        get_kwargs: dict[str, Any] = {"include": ["documents", "metadatas"]}
        if where_clause is not None:
            get_kwargs["where"] = where_clause

        try:
            all_docs_res = self._collection.get(**get_kwargs)
        except Exception:
            return dense_hits[:top_k]

        all_ids = all_docs_res.get("ids") or []
        all_texts = all_docs_res.get("documents") or []
        all_metas = all_docs_res.get("metadatas") or []

        if not all_ids:
            return dense_hits[:top_k]

        # 3. Compute Okapi BM25 lexical scores (including exact course code / identifier boost)
        query_tokens = re.findall(r"[a-z0-9]{2,}", query_text.lower())
        exact_codes = [
            tok for tok in query_tokens if any(ch.isdigit() for ch in tok) and len(tok) >= 3
        ]

        doc_tokens_list: list[list[str]] = [
            re.findall(r"[a-z0-9]{2,}", str(t or "").lower()) for t in all_texts
        ]
        n_docs = len(doc_tokens_list)
        avgdl = sum(len(dt) for dt in doc_tokens_list) / max(1, n_docs)

        # Document frequencies
        df: dict[str, int] = {}
        for q_tok in set(query_tokens):
            df[q_tok] = sum(1 for dt in doc_tokens_list if q_tok in dt)

        k1 = 1.5
        b = 0.75
        bm25_scored: list[tuple[int, float]] = []
        for idx, dt in enumerate(doc_tokens_list):
            if not dt:
                continue
            dl = len(dt)
            score = 0.0
            for q_tok in query_tokens:
                tf = dt.count(q_tok)
                if tf == 0:
                    continue
                doc_freq = df.get(q_tok, 0)
                idf = math.log(1.0 + ((n_docs - doc_freq + 0.5) / (doc_freq + 0.5)))
                denom = tf + k1 * (1.0 - b + b * (dl / max(1.0, avgdl)))
                score += idf * ((tf * (k1 + 1.0)) / denom)

            # Exact alphanumeric code boost (e.g., CSC3100, DK-B, Week 4)
            dt_set = set(dt)
            for code in exact_codes:
                if code in dt_set:
                    score += 4.0

            if score > 0:
                bm25_scored.append((idx, score))

        bm25_scored.sort(key=lambda item: item[1], reverse=True)
        max_bm25 = bm25_scored[0][1] if bm25_scored else 1.0

        # 4. Reciprocal Rank Fusion (RRF) of Dense Rank and BM25 Rank
        dense_rank_map: dict[str, int] = {
            hit.chunk_id: rank for rank, hit in enumerate(dense_hits, start=1)
        }
        dense_record_map: dict[str, RetrievedChunkRecord] = {
            hit.chunk_id: hit for hit in dense_hits
        }

        bm25_rank_map: dict[str, int] = {}
        bm25_norm_map: dict[str, float] = {}
        bm25_record_map: dict[str, RetrievedChunkRecord] = {}
        for rank, (doc_idx, raw_bm25) in enumerate(bm25_scored[:dense_pool_size], start=1):
            cid = str(all_ids[doc_idx])
            meta = all_metas[doc_idx] or {}
            text_val = str(all_texts[doc_idx] or "")
            norm_bm25 = min(1.0, raw_bm25 / max(1.0, max_bm25))
            bm25_rank_map[cid] = rank
            bm25_norm_map[cid] = norm_bm25
            bm25_record_map[cid] = RetrievedChunkRecord(
                chunk_id=cid,
                document_id=str(meta.get("document_id", "")),
                document_title=str(meta.get("document_title", "Untitled Document")),
                category=str(meta.get("category", "general")),
                language=str(meta.get("language", "en")),
                page_number=int(meta.get("page_number", 1)),
                chunk_index=int(meta.get("chunk_index", 0)),
                text=text_val,
                relevance_score=round(0.60 + 0.38 * norm_bm25, 4),
            )

        candidate_ids = list(set(dense_rank_map.keys()) | set(bm25_rank_map.keys()))
        fused_results: list[tuple[float, RetrievedChunkRecord]] = []

        for cid in candidate_ids:
            d_rank = dense_rank_map.get(cid, dense_pool_size + 50)
            b_rank = bm25_rank_map.get(cid, dense_pool_size + 50)
            rrf_score = (1.0 / (rrf_k + d_rank)) + (1.0 / (rrf_k + b_rank))

            base_record = dense_record_map.get(cid) or bm25_record_map[cid]
            dense_sim = dense_record_map[cid].relevance_score if cid in dense_record_map else 0.50
            bm25_sim = bm25_norm_map.get(cid, 0.0)

            # Calibrated hybrid relevance score combining dense similarity and BM25 lexical match
            hybrid_relevance = min(
                0.99,
                max(dense_sim, round((0.65 * dense_sim) + (0.35 * bm25_sim) + (rrf_score * 2.5), 4)),
            )
            fused_record = RetrievedChunkRecord(
                chunk_id=base_record.chunk_id,
                document_id=base_record.document_id,
                document_title=base_record.document_title,
                category=base_record.category,
                language=base_record.language,
                page_number=base_record.page_number,
                chunk_index=base_record.chunk_index,
                text=base_record.text,
                relevance_score=hybrid_relevance,
            )
            fused_results.append((rrf_score, fused_record))

        fused_results.sort(
            key=lambda item: (item[0], item[1].relevance_score),
            reverse=True,
        )
        return [rec for _, rec in fused_results[:top_k]]

    def update_document_metadata(
        self,
        document_id: str,
        title: str | None = None,
        category: str | None = None,
        language: str | None = None,
        is_active: bool | None = None,
    ) -> int:
        """Synchronize updated document attributes (`is_active`, `title`, etc.) across all chunks."""
        existing = self._collection.get(
            where={"document_id": document_id},
            include=["metadatas"],
        )
        ids = existing.get("ids") or []
        metadatas = existing.get("metadatas") or []
        if not ids:
            return 0

        updated_metadatas: list[dict[str, Any]] = []
        for meta in metadatas:
            new_meta = dict(meta or {})
            if title is not None:
                new_meta["document_title"] = title
            if category is not None:
                new_meta["category"] = category
            if language is not None:
                new_meta["language"] = language
            if is_active is not None:
                new_meta["is_active"] = is_active
            updated_metadatas.append(new_meta)

        self._collection.update(ids=ids, metadatas=updated_metadatas)
        return len(ids)

    def delete_document_chunks(self, document_id: str) -> int:
        """Delete all vector chunks belonging to `document_id`."""
        existing = self._collection.get(
            where={"document_id": document_id},
            include=[],
        )
        ids = existing.get("ids") or []
        if ids:
            self._collection.delete(ids=ids)
        return len(ids)

    def count_chunks(self, document_id: str | None = None) -> int:
        """Return total chunk count or count for a specific document."""
        if document_id is None:
            return self._collection.count()
        existing = self._collection.get(
            where={"document_id": document_id},
            include=[],
        )
        return len(existing.get("ids") or [])


_chroma_repo_instance: ChromaVectorRepository | None = None


def get_chroma_repository() -> ChromaVectorRepository:
    """FastAPI dependency returning singleton ChromaVectorRepository."""
    global _chroma_repo_instance
    if _chroma_repo_instance is None:
        _chroma_repo_instance = ChromaVectorRepository()
    return _chroma_repo_instance

