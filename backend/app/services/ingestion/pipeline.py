import os
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentChunk
from app.services.ingestion.chunker import (
    ChunkItem,
    MarkdownChunker,
    compute_file_hash,
)
from app.services.ingestion.parsers import (
    parse_docx,
    parse_pdf,
    parse_text_or_markdown,
    parse_url,
)
from app.services.retrieval.embeddings import EmbeddingService
from app.services.vectorstore.chroma_store import ChromaChunk, ChromaStore

logger = structlog.get_logger("ingestion.pipeline")


class IngestionStats:
    def __init__(self) -> None:
        self.files_skipped: int = 0
        self.files_added: int = 0
        self.files_updated: int = 0
        self.files_failed: int = 0
        self.chunks_added: int = 0
        self.chunks_removed: int = 0
        self.chunks_reused: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "files_skipped": self.files_skipped,
            "files_added": self.files_added,
            "files_updated": self.files_updated,
            "files_failed": self.files_failed,
            "chunks_added": self.chunks_added,
            "chunks_removed": self.chunks_removed,
            "chunks_reused": self.chunks_reused,
        }


class IngestionPipeline:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.chunker = MarkdownChunker()

    async def ingest_file(
        self,
        file_path: str,
        content_bytes: bytes,
        title: str | None = None,
        source_type: str = "file",
        stats: IngestionStats | None = None,
        force: bool = False,
    ) -> Document | None:
        """Ingest one file. `force` re-chunks even when the file hash is unchanged."""
        if stats is None:
            stats = IngestionStats()

        file_hash = compute_file_hash(content_bytes)
        file_size = len(content_bytes)
        ext = os.path.splitext(file_path)[1].lower()

        # 1. File-level check: Check if path already exists
        result = await self.db.execute(select(Document).where(Document.source_path == file_path))
        existing_doc = result.scalar_one_or_none()

        if existing_doc and existing_doc.file_hash == file_hash and not force:
            chunk_count_res = await self.db.execute(
                select(func.count(DocumentChunk.id)).where(
                    DocumentChunk.document_id == existing_doc.id
                )
            )
            if (chunk_count_res.scalar() or 0) > 0:
                logger.info("file_skipped_hash_match", path=file_path, file_hash=file_hash)
                stats.files_skipped += 1
                return existing_doc

        # Check if identical file_hash exists at another path (moved / renamed)
        result_hash = await self.db.execute(select(Document).where(Document.file_hash == file_hash))
        moved_doc = result_hash.scalar_one_or_none()
        if moved_doc and not existing_doc:
            logger.info(
                "file_renamed_updating_path", old_path=moved_doc.source_path, new_path=file_path
            )
            moved_doc.source_path = file_path
            moved_doc.updated_at = datetime.now(UTC)
            await self.db.commit()
            stats.files_skipped += 1
            return moved_doc

        # 2. Parse content based on format
        try:
            if ext in (".md", ".markdown", ".txt"):
                parsed = parse_text_or_markdown(content_bytes, file_path)
            elif ext == ".pdf":
                parsed = parse_pdf(content_bytes, file_path)
            elif ext in (".docx", ".doc"):
                parsed = parse_docx(content_bytes, file_path)
            else:
                parsed = parse_text_or_markdown(content_bytes, file_path)
        except Exception as exc:
            logger.error("file_parsing_failed", path=file_path, error=str(exc))
            stats.files_failed += 1
            return None

        # PostgreSQL stores document and section titles in bounded metadata columns.
        doc_title = (title or parsed.title or file_path).strip()[:255]

        is_update = existing_doc is not None
        if existing_doc:
            doc = existing_doc
            doc.title = doc_title
            doc.file_hash = file_hash
            doc.file_size = file_size
            doc.mime_type = parsed.mime_type
            doc.meta_info = parsed.meta_info
            doc.updated_at = datetime.now(UTC)
        else:
            doc = Document(
                title=doc_title,
                source=source_type,
                source_path=file_path,
                file_hash=file_hash,
                file_size=file_size,
                mime_type=parsed.mime_type,
                meta_info=parsed.meta_info,
            )
            self.db.add(doc)

        await self.db.flush()

        # 3. Chunk-level incremental ingestion
        new_chunks = self.chunker.chunk_document(parsed.text, doc_title)
        new_chunk_hashes = {c.chunk_hash for c in new_chunks}

        existing_chunks_query = await self.db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        )
        existing_chunks = existing_chunks_query.scalars().all()
        existing_chunks_by_hash = {c.chunk_hash: c for c in existing_chunks}

        removed_chunk_ids: list[uuid.UUID] = []
        added_chunks: list[tuple[DocumentChunk, Any]] = []

        # Determine chunks to delete (no longer present)
        for old_hash, old_chunk in existing_chunks_by_hash.items():
            if old_hash not in new_chunk_hashes:
                removed_chunk_ids.append(old_chunk.id)
                await self.db.delete(old_chunk)
                stats.chunks_removed += 1

        # Determine new chunks to insert or unchanged chunks to reuse
        chunks_to_embed: list[tuple[ChunkItem, str]] = []  # (chunk_item, text)

        for chunk_item in new_chunks:
            if chunk_item.chunk_hash in existing_chunks_by_hash:
                # Existing chunk is untouched
                stats.chunks_reused += 1
                continue

            # Check if vector for this chunk_hash exists anywhere in document_chunks
            existing_vector_query = await self.db.execute(
                select(DocumentChunk.embedding)
                .where(
                    DocumentChunk.chunk_hash == chunk_item.chunk_hash,
                    DocumentChunk.embedding.is_not(None),
                )
                .limit(1)
            )
            reused_vector = existing_vector_query.scalar_one_or_none()

            if reused_vector is not None:
                # Reuse vector without calling embedding model
                new_chunk_model = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=chunk_item.chunk_index,
                    chunk_hash=chunk_item.chunk_hash,
                    content=chunk_item.content,
                    title=chunk_item.title[:255] if chunk_item.title else None,
                    page=chunk_item.page,
                    meta_info=chunk_item.meta_info,
                    embedding=reused_vector,
                )
                self.db.add(new_chunk_model)
                added_chunks.append((new_chunk_model, reused_vector))
                stats.chunks_added += 1
                stats.chunks_reused += 1
            else:
                chunks_to_embed.append((chunk_item, chunk_item.content))

        # Embed and insert truly new chunks
        if chunks_to_embed:
            logger.info("embedding_chunks_start", file=file_path, count=len(chunks_to_embed))
            texts = [c[1] for c in chunks_to_embed]
            vectors = await EmbeddingService.embed_documents(texts)
            logger.info("embedding_chunks_complete", file=file_path, count=len(chunks_to_embed))

            for (chunk_item, _), vector in zip(chunks_to_embed, vectors, strict=True):
                new_chunk_model = DocumentChunk(
                    document_id=doc.id,
                    chunk_index=chunk_item.chunk_index,
                    chunk_hash=chunk_item.chunk_hash,
                    content=chunk_item.content,
                    title=chunk_item.title[:255] if chunk_item.title else None,
                    page=chunk_item.page,
                    meta_info=chunk_item.meta_info,
                    embedding=vector,
                )
                self.db.add(new_chunk_model)
                added_chunks.append((new_chunk_model, vector))
                stats.chunks_added += 1

        await self.db.flush()
        mirror_rows = [
            ChromaChunk(
                chunk_id=model.id,
                document_id=doc.id,
                content=model.content,
                embedding=[float(x) for x in vector],
                title=model.title,
                source_path=file_path,
                page=model.page,
                chunk_index=model.chunk_index,
            )
            for model, vector in added_chunks
        ]
        await self.db.commit()

        # Postgres is committed first and stays the source of truth; Chroma is a best-effort mirror.
        await ChromaStore.delete_chunks(removed_chunk_ids)
        await ChromaStore.upsert_chunks(mirror_rows)

        if is_update:
            stats.files_updated += 1
        else:
            stats.files_added += 1

        logger.info(
            "file_ingested",
            path=file_path,
            title=doc.title,
            chunks_count=len(new_chunks),
        )
        return doc

    async def ingest_url(
        self,
        url: str,
        stats: IngestionStats | None = None,
    ) -> Document | None:
        if stats is None:
            stats = IngestionStats()

        try:
            parsed = await parse_url(url)
        except Exception as exc:
            logger.error("url_parsing_failed", url=url, error=str(exc))
            stats.files_failed += 1
            raise

        content_bytes = parsed.text.encode("utf-8")
        return await self.ingest_file(
            file_path=url,
            content_bytes=content_bytes,
            title=parsed.title,
            source_type="url",
            stats=stats,
        )
