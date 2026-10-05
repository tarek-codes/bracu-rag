import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import DocumentChunk
from app.services.ingestion.pipeline import IngestionPipeline, IngestionStats


@pytest.mark.asyncio
async def test_ingestion_bounds_document_and_section_titles(db_session: AsyncSession) -> None:
    pipeline = IngestionPipeline(db_session)
    long_heading = "#" + (" Very long section title" * 20)
    document = await pipeline.ingest_file(
        file_path=f"long-title-{uuid.uuid4().hex}.md",
        content_bytes=f"{long_heading}\n\nThis section contains enough content to index.".encode(),
        stats=IngestionStats(),
    )

    assert document is not None
    assert len(document.title) <= 255
    result = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    chunks = result.scalars().all()
    assert all(chunk.title is None or len(chunk.title) <= 255 for chunk in chunks)
