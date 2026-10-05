import re
import uuid
from ast import literal_eval
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.retrieval.embeddings import EmbeddingService

logger = structlog.get_logger("retrieval.hybrid")
settings = get_settings()
_faiss_index: Any = None
_faiss_chunk_ids: list[uuid.UUID] = []
_faiss_signature: tuple[int, str | None] | None = None


def _use_mock_model() -> bool:
    import os

    return (
        os.getenv("TESTING") == "1"
        or settings.ENVIRONMENT == "test"
        or not settings.GROQ_API_KEY
        or settings.GROQ_API_KEY.startswith("dummy_")
    )


def _fts_query(query: str, operator: str = "OR") -> str:
    stop_words = {
        "a",
        "an",
        "and",
        "are",
        "available",
        "how",
        "is",
        "the",
        "to",
        "what",
        "which",
        "where",
        "who",
    }
    terms = [
        term
        for term in re.findall(r"[A-Za-z0-9]+", query)
        if len(term) > 2 and term.lower() not in stop_words
    ]
    if operator == "AND":
        return " ".join(terms) or query
    phrases = [f'"{left} {right}"' for left, right in zip(terms, terms[1:], strict=False)]
    return " OR ".join([*phrases, *terms]) or query


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    content: str
    page: int | None = None
    source_path: str = ""
    vector_rank: int | None = None
    text_rank: int | None = None
    rrf_score: float = 0.0
    meta_info: dict[str, Any] = field(default_factory=dict)


class HybridSearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _faiss_ranks(
        self,
        query_vector: list[float],
        limit: int,
    ) -> dict[uuid.UUID, int]:
        global _faiss_chunk_ids, _faiss_index, _faiss_signature

        signature_result = await self.db.execute(
            text("""
                SELECT count(*) AS chunk_count, max(created_at)::text AS newest_chunk
                FROM document_chunks
                WHERE embedding IS NOT NULL
            """)
        )
        signature_row = signature_result.one()
        signature = (int(signature_row.chunk_count), signature_row.newest_chunk)

        if _faiss_index is None or _faiss_signature != signature:
            vector_rows = await self.db.execute(
                text("""
                    SELECT id, embedding
                    FROM document_chunks
                    WHERE embedding IS NOT NULL
                    ORDER BY id
                """)
            )
            vector_records: list[tuple[uuid.UUID, list[float]]] = []
            for row in vector_rows:
                embedding = (
                    literal_eval(row.embedding) if isinstance(row.embedding, str) else row.embedding
                )
                vector_records.append((row.id, [float(value) for value in embedding]))

            if not vector_records:
                _faiss_index = None
                _faiss_chunk_ids = []
                _faiss_signature = signature
                return {}

            import faiss
            import numpy as np

            embeddings = np.asarray([embedding for _, embedding in vector_records], dtype="float32")
            faiss.normalize_L2(embeddings)
            _faiss_index = faiss.IndexFlatIP(embeddings.shape[1])
            _faiss_index.add(embeddings)
            _faiss_chunk_ids = [chunk_id for chunk_id, _ in vector_records]
            _faiss_signature = signature
            logger.info("faiss_index_built", vectors=len(_faiss_chunk_ids))

        import faiss
        import numpy as np

        query_array = np.asarray([query_vector], dtype="float32")
        faiss.normalize_L2(query_array)
        _, positions = _faiss_index.search(query_array, min(limit, len(_faiss_chunk_ids)))
        return {
            _faiss_chunk_ids[int(position)]: rank
            for rank, position in enumerate(positions[0], start=1)
            if position >= 0
        }

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        rrf_k: int = 60,
    ) -> list[RetrievedChunk]:
        """Perform FAISS vector search and Postgres full-text search with RRF."""
        limit = top_k or settings.RETRIEVAL_TOP_K
        if not query.strip():
            return []

        # 1. Embed query asynchronously
        query_vector = await EmbeddingService.embed_query(query)
        document_ids = await self._select_documents(query, query_vector)
        if not document_ids:
            return []

        vec_ranks = await self._faiss_ranks(query_vector, limit * 5)
        vector_chunk_ids = set(vec_ranks)
        if vector_chunk_ids:
            vector_doc_rows = await self.db.execute(
                text(
                    "SELECT id, document_id FROM document_chunks "
                    "WHERE id = ANY(:ids) AND title NOT ILIKE '%quick navigation%'"
                ),
                {"ids": list(vector_chunk_ids)},
            )
            allowed_docs = set(document_ids)
            vec_ranks = {
                row.id: rank
                for row in vector_doc_rows
                if row.document_id in allowed_docs
                for rank in [vec_ranks[row.id]]
            }

        # 3. Full-text search (GIN tsvector index)
        fts_sql = text("""
            SELECT id, ts_rank_cd(to_tsvector('english', content), websearch_to_tsquery('english', :query)) AS rank_score
            FROM document_chunks
            WHERE document_id = ANY(:document_ids)
              AND title NOT ILIKE '%quick navigation%'
              AND to_tsvector('english', content) @@ websearch_to_tsquery('english', :query)
            ORDER BY rank_score DESC
            LIMIT :limit
        """)
        try:
            fts_result = await self.db.execute(
                fts_sql,
                {
                    "query": _fts_query(query),
                    "document_ids": list(document_ids),
                    "limit": limit,
                },
            )
            fts_ranks: dict[uuid.UUID, int] = {}
            for rank, row in enumerate(fts_result, start=1):
                fts_ranks[row.id] = rank
        except Exception as exc:
            # Fallback for complex queries or syntax
            logger.warning("fts_search_fallback", query=query, error=str(exc))
            fts_ranks = {}

        # 4. Reciprocal Rank Fusion (RRF)
        all_chunk_ids = set(vec_ranks.keys()) | set(fts_ranks.keys())
        if not all_chunk_ids:
            return []

        scores: dict[uuid.UUID, float] = {}
        for cid in all_chunk_ids:
            score = 0.0
            if cid in vec_ranks:
                score += settings.RETRIEVAL_FAISS_WEIGHT / (rrf_k + vec_ranks[cid])
            if cid in fts_ranks:
                score += settings.RETRIEVAL_TEXT_WEIGHT / (rrf_k + fts_ranks[cid])
            scores[cid] = score

        # Top K chunk IDs sorted by RRF score descending
        sorted_cids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)[:limit]

        # 5. Fetch full chunk and document details
        fetch_sql = text("""
            SELECT
                c.id AS chunk_id,
                c.document_id,
                c.content,
                c.title AS chunk_title,
                c.page,
                c.meta_info AS chunk_meta,
                d.title AS doc_title,
                d.source_path
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.id = ANY(:cids)
        """)
        details_res = await self.db.execute(fetch_sql, {"cids": sorted_cids})
        details_by_id = {row.chunk_id: row for row in details_res}

        candidates: list[RetrievedChunk] = []
        for cid in sorted_cids:
            chunk_row = details_by_id.get(cid)
            if chunk_row is not None:
                title = chunk_row.chunk_title or chunk_row.doc_title or "BRAC University Document"
                candidates.append(
                    RetrievedChunk(
                        chunk_id=chunk_row.chunk_id,
                        document_id=chunk_row.document_id,
                        title=title,
                        content=chunk_row.content,
                        page=chunk_row.page,
                        source_path=chunk_row.source_path or "",
                        vector_rank=vec_ranks.get(cid),
                        text_rank=fts_ranks.get(cid),
                        rrf_score=round(scores[cid], 6),
                        meta_info=chunk_row.chunk_meta or {},
                    )
                )

        logger.info(
            "hybrid_search_completed",
            query=query,
            total_candidates=len(candidates),
            top_score=candidates[0].rrf_score if candidates else 0.0,
        )
        return candidates

    async def _select_documents(
        self,
        query: str,
        query_vector: list[float],
    ) -> set[uuid.UUID]:
        """Route a question to at most three documents before chunk retrieval."""
        document_limit = settings.RETRIEVAL_DOCUMENT_LIMIT
        lexical_result = await self.db.execute(
            text("""
                SELECT c.document_id, d.source_path, max(ts_rank_cd(
                    to_tsvector('english', c.content),
                    websearch_to_tsquery('english', :query)
                )) AS score
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE to_tsvector('english', c.content)
                    @@ websearch_to_tsquery('english', :query)
                GROUP BY c.document_id, d.source_path
                ORDER BY score DESC
                LIMIT :limit
            """),
            {"query": _fts_query(query, operator="AND"), "limit": document_limit},
        )
        lexical_rows = list(lexical_result)
        if not lexical_rows:
            lexical_result = await self.db.execute(
                text("""
                    SELECT c.document_id, d.source_path, max(ts_rank_cd(
                        to_tsvector('english', c.content),
                        websearch_to_tsquery('english', :query)
                    )) AS score
                    FROM document_chunks c
                    JOIN documents d ON d.id = c.document_id
                    WHERE to_tsvector('english', c.content)
                        @@ websearch_to_tsquery('english', :query)
                    GROUP BY c.document_id, d.source_path
                    ORDER BY score DESC
                    LIMIT :limit
                """),
                {"query": _fts_query(query), "limit": document_limit},
            )
            lexical_rows = list(lexical_result)
        query_lower = query.lower()
        preferred_tokens: tuple[str, ...] = ()
        if any(term in query_lower for term in ("admission", "residential", "postgraduate")):
            preferred_tokens = ("admission", "faq", "residential")
        elif any(term in query_lower for term in ("cse", "algorithm", "course")):
            preferred_tokens = ("cse", "course")
        elif any(term in query_lower for term in ("tuition", "fee", "scholarship", "waiver")):
            preferred_tokens = ("tuition", "fee", "scholarship")

        lexical_rows.sort(
            key=lambda row: (
                any(token in (row.source_path or "").lower() for token in preferred_tokens),
                float(row.score or 0.0),
            ),
            reverse=True,
        )
        preferred_selected = [
            row.document_id
            for row in lexical_rows
            if any(token in (row.source_path or "").lower() for token in preferred_tokens)
        ]
        selected = (
            preferred_selected[:document_limit]
            if preferred_selected
            else [row.document_id for row in lexical_rows]
        )

        if len(selected) < document_limit and not preferred_selected:
            vector_ranks = await self._faiss_ranks(query_vector, settings.RETRIEVAL_TOP_K * 5)
            if vector_ranks:
                chunk_rows = await self.db.execute(
                    text("""
                        SELECT id, document_id
                        FROM document_chunks
                        WHERE id = ANY(:ids)
                          AND title NOT ILIKE '%quick navigation%'
                    """),
                    {"ids": list(vector_ranks)},
                )
                for row in sorted(chunk_rows, key=lambda item: vector_ranks[item.id]):
                    if row.document_id not in selected:
                        selected.append(row.document_id)
                    if len(selected) >= document_limit:
                        break

        chosen = set(selected[:document_limit])
        logger.info(
            "document_routing_completed",
            query=query,
            selected_document_count=len(chosen),
            selected_document_ids=[str(document_id) for document_id in chosen],
        )
        return chosen
