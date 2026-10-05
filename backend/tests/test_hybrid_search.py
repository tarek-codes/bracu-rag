import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import Document, DocumentChunk
from app.services.retrieval.embeddings import EmbeddingService
from app.services.retrieval.hybrid_search import HybridSearchService


@pytest.mark.asyncio
async def test_hybrid_search_empty_query(db_session: AsyncSession) -> None:
    service = HybridSearchService(db_session)
    results = await service.search("")
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_with_documents(
    db_session: AsyncSession,
) -> None:
    kw = f"uniqueadvisor{uuid.uuid4().hex[:8]}"
    doc = Document(
        title="BRACU Advising Guide",
        source="upload",
        source_path=f"advising_{kw}.md",
        file_hash=f"dummy_hash_{kw}",
        file_size=1000,
        mime_type="text/markdown",
    )
    db_session.add(doc)
    await db_session.flush()

    query_text = f"{kw} advising"
    query_emb = await EmbeddingService.embed_query(query_text)

    chunk1 = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        chunk_hash=f"chunk_hash_1_{kw}",
        content=f"Advising for Spring 2026 begins on January 5th for undergraduate students {kw}.",
        title="Advising Dates",
        embedding=query_emb,
    )
    chunk2 = DocumentChunk(
        document_id=doc.id,
        chunk_index=1,
        chunk_hash=f"chunk_hash_2_{kw}",
        content=f"Tuition fees must be paid before course registration is confirmed {kw}.",
        title="Payment Policy",
        embedding=[-0.05] * get_settings().EMBEDDING_DIM,
    )
    db_session.add_all([chunk1, chunk2])
    await db_session.commit()

    service = HybridSearchService(db_session)
    results = await service.search(query_text, top_k=10)

    assert len(results) > 0
    matched = [r for r in results if r.document_id == doc.id]
    assert len(matched) > 0
    assert matched[0].rrf_score > 0.0
    matched_titles = [m.title for m in matched]
    assert any(t in ["Advising Dates", "Payment Policy"] for t in matched_titles)
