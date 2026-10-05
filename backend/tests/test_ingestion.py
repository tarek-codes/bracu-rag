import uuid

import pytest
from sqlalchemy import select

from app.models.document import DocumentChunk
from app.services.ingestion.pipeline import IngestionPipeline, IngestionStats


@pytest.mark.asyncio
async def test_incremental_ingestion_lifecycle(setup_db_override: None) -> None:
    from tests.conftest import test_session_factory

    async with test_session_factory() as db:
        pipeline = IngestionPipeline(db)
        stats = IngestionStats()

        doc_path = f"policies/grading_{uuid.uuid4().hex[:6]}.md"
        v1_content = (
            b"# Grading Policy\n\n"
            b"Undergraduate grading scale at BRAC University is based on a 4.0 GPA scale.\n\n"
            b"## Pass Marks\n\n"
            b"Minimum passing grade is D (1.0)."
        )

        # 1. Ingest initial document
        doc1 = await pipeline.ingest_file(
            file_path=doc_path,
            content_bytes=v1_content,
            title="Grading Policy",
            stats=stats,
        )
        assert doc1 is not None
        assert stats.files_added == 1
        assert stats.files_skipped == 0
        assert stats.chunks_added >= 1

        chunks_after_v1 = await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc1.id)
        )
        v1_chunk_count = len(chunks_after_v1.scalars().all())
        assert v1_chunk_count >= 1

        # 2. Re-ingest exact same content -> Must skip completely (no new embeddings)
        stats2 = IngestionStats()
        doc2 = await pipeline.ingest_file(
            file_path=doc_path,
            content_bytes=v1_content,
            title="Grading Policy",
            stats=stats2,
        )
        assert doc2 is not None
        assert stats2.files_skipped == 1
        assert stats2.files_added == 0
        assert stats2.chunks_added == 0

        # 3. Modify document with an added section -> Must only embed the new section
        v2_content = (
            b"# Grading Policy\n\n"
            b"Undergraduate grading scale at BRAC University is based on a 4.0 GPA scale.\n\n"
            b"## Pass Marks\n\n"
            b"Minimum passing grade is D (1.0).\n\n"
            b"## Academic Probation\n\n"
            b"A student with CGPA below 2.00 will be placed on academic probation."
        )

        stats3 = IngestionStats()
        doc3 = await pipeline.ingest_file(
            file_path=doc_path,
            content_bytes=v2_content,
            title="Grading Policy",
            stats=stats3,
        )
        assert doc3 is not None
        assert stats3.files_updated == 1
        assert stats3.chunks_added >= 1  # only new chunk added
        assert stats3.chunks_reused >= 1  # prior chunks reused

        # 4. Deleting document removes its chunks
        await db.delete(doc3)
        await db.commit()

        remaining_chunks = await db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc3.id)
        )
        assert len(remaining_chunks.scalars().all()) == 0
