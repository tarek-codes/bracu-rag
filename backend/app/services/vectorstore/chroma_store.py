"""Chroma Cloud mirror of the knowledge base.

PostgreSQL stays the source of truth. Every chunk written to Postgres is also upserted
here so the vectors are reachable from the cloud. Failures are logged and never raised,
so a Chroma outage cannot break ingestion or chat. `sync-chroma` repairs any drift.
"""

import asyncio
import os
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import get_settings

logger = structlog.get_logger("vectorstore.chroma")
settings = get_settings()

_BATCH_SIZE = 100
_collection: Any = None


@dataclass(frozen=True)
class ChromaChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    content: str
    embedding: Sequence[float]
    title: str | None
    source_path: str
    page: int | None
    chunk_index: int


def _metadata(chunk: ChromaChunk) -> dict[str, str | int]:
    meta: dict[str, str | int] = {
        "document_id": str(chunk.document_id),
        "source_path": chunk.source_path,
        "chunk_index": chunk.chunk_index,
    }
    if chunk.title:
        meta["title"] = chunk.title
    if chunk.page is not None:
        meta["page"] = chunk.page
    return meta


def _get_collection() -> Any:
    global _collection
    if _collection is None:
        import chromadb

        client = chromadb.CloudClient(
            tenant=settings.CHROMA_TENANT,
            database=settings.CHROMA_DATABASE,
            api_key=settings.CHROMA_API_KEY,
            cloud_host=settings.CHROMA_HOST,
        )
        _collection = client.get_or_create_collection(name=settings.CHROMA_COLLECTION_NAME)
        logger.info("chroma_collection_ready", collection=settings.CHROMA_COLLECTION_NAME)
    return _collection


class ChromaStore:
    @staticmethod
    def enabled() -> bool:
        if os.getenv("TESTING") == "1" or settings.ENVIRONMENT == "test":
            return False
        return bool(settings.CHROMA_API_KEY and settings.CHROMA_TENANT)

    @classmethod
    def _upsert_sync(cls, chunks: Sequence[ChromaChunk]) -> None:
        collection = _get_collection()
        for start in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[start : start + _BATCH_SIZE]
            collection.upsert(
                ids=[str(c.chunk_id) for c in batch],
                embeddings=[list(c.embedding) for c in batch],
                documents=[c.content for c in batch],
                metadatas=[_metadata(c) for c in batch],
            )

    @classmethod
    def _delete_sync(cls, ids: Sequence[uuid.UUID]) -> None:
        collection = _get_collection()
        for start in range(0, len(ids), _BATCH_SIZE):
            collection.delete(ids=[str(i) for i in ids[start : start + _BATCH_SIZE]])

    @classmethod
    async def upsert_chunks(cls, chunks: Sequence[ChromaChunk]) -> bool:
        if not chunks or not cls.enabled():
            return False
        try:
            await asyncio.to_thread(cls._upsert_sync, chunks)
            logger.info("chroma_upserted", count=len(chunks))
            return True
        except Exception as exc:
            logger.warning("chroma_upsert_failed", count=len(chunks), error=str(exc))
            return False

    @classmethod
    async def delete_chunks(cls, chunk_ids: Sequence[uuid.UUID]) -> bool:
        if not chunk_ids or not cls.enabled():
            return False
        try:
            await asyncio.to_thread(cls._delete_sync, chunk_ids)
            logger.info("chroma_deleted", count=len(chunk_ids))
            return True
        except Exception as exc:
            logger.warning("chroma_delete_failed", count=len(chunk_ids), error=str(exc))
            return False

    @classmethod
    async def delete_document(cls, document_id: uuid.UUID) -> bool:
        if not cls.enabled():
            return False
        try:
            collection = await asyncio.to_thread(_get_collection)
            await asyncio.to_thread(collection.delete, where={"document_id": str(document_id)})
            logger.info("chroma_document_deleted", document_id=str(document_id))
            return True
        except Exception as exc:
            logger.warning("chroma_document_delete_failed", error=str(exc))
            return False

    @classmethod
    def count_sync(cls) -> int:
        return int(_get_collection().count())
