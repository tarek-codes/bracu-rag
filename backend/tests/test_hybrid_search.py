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


def test_fts_query_filters_domain_and_conversational_words() -> None:
    from app.services.retrieval.hybrid_search import _fts_query

    # Boilerplate institution names should not drown out specific names
    and_q = _fts_query("Who is Md. Tawhid Anwar at BRAC University?", operator="AND")
    assert "Tawhid" in and_q
    assert "Anwar" in and_q
    assert "BRAC" not in and_q
    assert "University" not in and_q

    # Query with only university words should fallback to university terms
    generic_q = _fts_query("What is BRAC University?", operator="AND")
    assert "BRAC" in generic_q
    assert "University" in generic_q


@pytest.mark.asyncio
async def test_hybrid_search_with_domain_boilerplate(
    db_session: AsyncSession,
) -> None:
    kw = f"person{uuid.uuid4().hex[:8]}"
    doc = Document(
        title="Faculty Profiles",
        source="upload",
        source_path=f"faculty_{kw}.md",
        file_hash=f"hash_fac_{kw}",
        file_size=1200,
        mime_type="text/markdown",
    )
    db_session.add(doc)
    await db_session.flush()

    query_text = f"Who is Professor {kw} at BRAC University?"
    query_emb = await EmbeddingService.embed_query(query_text)

    chunk = DocumentChunk(
        document_id=doc.id,
        chunk_index=0,
        chunk_hash=f"chunk_fac_{kw}",
        content=f"Professor {kw} is a distinguished faculty member at BRAC University in Computer Science.",
        title="Biography",
        embedding=query_emb,
    )
    db_session.add(chunk)
    await db_session.commit()

    service = HybridSearchService(db_session)
    results = await service.search(query_text, top_k=5)

    assert len(results) > 0
    matched = [r for r in results if r.chunk_id == chunk.id]
    assert len(matched) == 1
    assert matched[0].title == "Biography"
